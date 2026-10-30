import os
import re
import subprocess
import torch
import torchaudio
import soundfile as sf
import numpy as np
from cached_path import cached_path
from f5_tts.model import DiT
from f5_tts.infer.utils_infer import (
    load_model,
    load_vocoder,
    convert_char_to_pinyin,
    target_sample_rate,
    hop_length
)
from core.audio_processor import apply_micro_fade, create_silence

class VoiceCloneEngine:
    def __init__(self, device: str = None):
        if device is None:
            if torch.backends.mps.is_available():
                self.device = "mps"
            elif torch.cuda.is_available():
                self.device = "cuda"
            else:
                self.device = "cpu"
        else:
            self.device = device
            
        print(f"🚀 Initializing VoiceCloneEngine on device: {self.device}...")
        model_cls = DiT
        model_cfg = dict(dim=1024, depth=22, heads=16, ff_mult=2, text_dim=512, conv_layers=4)
        ckpt_file = str(cached_path("hf://SWivid/F5-TTS/F5TTS_v1_Base/model_1250000.safetensors"))
        vocab_file = str(cached_path("hf://SWivid/F5-TTS/F5TTS_v1_Base/vocab.txt"))

        self.model = load_model(model_cls, model_cfg, ckpt_file, vocab_file=vocab_file, device=self.device)
        self.vocoder = load_vocoder(is_local=False, device=self.device)
        print("✅ F5-TTS Neural Voice Engine loaded successfully!")

    def load_speaker_profile(self, ref_audio_path: str, ref_text: str):
        """Loads and conditions reference audio for instant zero-shot cloning."""
        audio, sr = torchaudio.load(ref_audio_path)
        if audio.shape[0] > 1:
            audio = torch.mean(audio, dim=0, keepdim=True)

        if sr != target_sample_rate:
            resampler = torchaudio.transforms.Resample(sr, target_sample_rate)
            audio = resampler(audio)

        # Enforce maximum reference duration (11.5s) to prevent F5-TTS attention blowout & hallucinations
        max_ref_samples = int(11.5 * target_sample_rate)
        if audio.shape[-1] > max_ref_samples:
            audio = audio[:, :max_ref_samples]

        # Normalize RMS volume without aggressively boosting mic preamp hiss
        target_rms = 0.08
        rms = torch.sqrt(torch.mean(torch.square(audio)))
        if rms > 1e-5:
            gain = min(target_rms / rms.item(), 2.5) # Max 2.5x boost
            if gain > 1.0:
                audio = audio * gain
            elif rms.item() > 0.15: # Prevent clipping if input was too loud
                audio = audio * (target_rms / rms.item())

        cond_audio = audio.to(self.device)
        ref_audio_len = cond_audio.shape[-1] // hop_length
        ref_text_len = len(ref_text.encode("utf-8"))

        return {
            "cond_audio": cond_audio,
            "ref_text": ref_text,
            "ref_audio_len": ref_audio_len,
            "ref_text_len": ref_text_len
        }

    def synthesize_chunk(self, profile: dict, text: str, speed: float = 1.40) -> np.ndarray:
        """Synthesize a single text chunk with speed adjustment."""
        text_list = [profile["ref_text"] + " " + text]
        final_text_list = convert_char_to_pinyin(text_list)
        gen_text_len = len(text.encode("utf-8"))
        
        gen_frames = int(profile["ref_audio_len"] / profile["ref_text_len"] * gen_text_len / speed)
        duration = profile["ref_audio_len"] + gen_frames

        with torch.inference_mode():
            generated, _ = self.model.sample(
                cond=profile["cond_audio"],
                text=final_text_list,
                duration=duration,
                steps=32,
                cfg_strength=2.0,
                sway_sampling_coef=-1.0,
            )
            generated = generated.to(torch.float32)
            generated = generated[:, profile["ref_audio_len"]:, :]
            generated = generated.permute(0, 2, 1)
            generated_wave = self.vocoder.decode(generated)
            wave = generated_wave.squeeze().cpu().numpy()
            
        # Apply anti-pop micro fade
        wave = apply_micro_fade(wave, target_sample_rate, fade_sec=0.02)
        return wave

    def parse_script(self, script_text: str):
        """
        Parses full script into items: (text, pause_after_sec).
        Supports '//' for 1.4s double-beat and '/' for 0.6s single-beat pauses.
        """
        major_blocks = script_text.split("//")
        items = []
        for b_idx, block in enumerate(major_blocks):
            sub_chunks = block.split("/")
            for c_idx, chunk in enumerate(sub_chunks):
                clean_text = chunk.strip()
                if not clean_text:
                    continue
                is_last_in_sub = (c_idx == len(sub_chunks) - 1)
                is_last_in_block = (b_idx == len(major_blocks) - 1)
                
                if is_last_in_sub:
                    pause = 0.5 if is_last_in_block else 1.4
                else:
                    pause = 0.6
                items.append((clean_text, pause))
        return items

    def generate_narration(self, ref_audio_path: str, ref_text: str, script_text: str,
                           output_dir: str, job_id: str, speed: float = 1.40, progress_callback=None):
        """
        Synthesizes the complete narration, adds pauses, and produces 48kHz WAV + MP3.
        """
        temp_dir = os.path.join(output_dir, f"temp_{job_id}")
        os.makedirs(temp_dir, exist_ok=True)
        
        profile = self.load_speaker_profile(ref_audio_path, ref_text)
        items = self.parse_script(script_text)
        total_items = len(items)
        chunk_files = []

        for idx, (chunk_text, pause_after) in enumerate(items):
            if progress_callback:
                progress_callback(idx + 1, total_items, f"Synthesizing sentence {idx+1}/{total_items}...")
                
            raw_wav = os.path.join(temp_dir, f"c{idx}_raw.wav")
            pcm48_wav = os.path.join(temp_dir, f"c{idx}_48k.wav")
            silence_wav = os.path.join(temp_dir, f"c{idx}_sil.wav")

            # 1. Synthesize
            wave_data = self.synthesize_chunk(profile, chunk_text, speed=speed)
            sf.write(raw_wav, wave_data, target_sample_rate)

            # 2. Resample to 48kHz mono 16-bit PCM
            subprocess.run([
                "ffmpeg", "-y", "-i", raw_wav,
                "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le",
                pcm48_wav
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            chunk_files.append(pcm48_wav)

            # 3. Add pause
            if pause_after > 0:
                create_silence(pause_after, silence_wav, sample_rate=48000)
                chunk_files.append(silence_wav)

        # 4. Concatenate chunks into final track
        concat_txt = os.path.join(temp_dir, "concat.txt")
        with open(concat_txt, "w") as f:
            for cp in chunk_files:
                f.write(f"file '{cp}'\n")

        final_wav = os.path.join(output_dir, f"{job_id}.wav")
        final_mp3 = os.path.join(output_dir, f"{job_id}.mp3")

        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_txt,
            "-c:a", "pcm_s16le", final_wav
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        subprocess.run([
            "ffmpeg", "-y", "-i", final_wav,
            "-b:a", "320k", "-ar", "48000", final_mp3
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        # Measure duration
        res = subprocess.run([
            "ffprobe", "-i", final_wav, "-show_entries", "format=duration",
            "-v", "quiet", "-of", "csv=p=0"
        ], capture_output=True, text=True)
        duration = float(res.stdout.strip()) if res.stdout.strip() else 0.0

        return {
            "wav_path": final_wav,
            "mp3_path": final_mp3,
            "duration": duration
        }
