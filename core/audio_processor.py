import os
import subprocess
import numpy as np
import soundfile as sf
import torch

try:
    from faster_whisper import WhisperModel
    _whisper_available = True
except ImportError:
    _whisper_available = False

whisper_model = None

def get_whisper():
    global whisper_model
    if whisper_model is None and _whisper_available:
        # Use tiny or base for instant 1-second transcription
        whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
    return whisper_model

def convert_to_wav(input_path: str, output_path: str, sample_rate: int = 24000, denoise: bool = True) -> str:
    """
    Converts any input audio file to standard mono 16-bit PCM WAV at target sample rate.
    Optionally applies highpass filtering (cuts rumble < 80Hz) and adaptive FFT noise reduction.
    """
    cmd = ["ffmpeg", "-y", "-i", input_path]
    if denoise:
        cmd.extend(["-af", "highpass=f=80,afftdn=nf=-25"])
    cmd.extend([
        "-ar", str(sample_rate),
        "-ac", "1",
        "-c:a", "pcm_s16le",
        output_path
    ])
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return output_path

def auto_transcribe(audio_path: str) -> str:
    """Automatically transcribes reference audio using local Whisper."""
    model = get_whisper()
    if model is None:
        return ""
    try:
        segments, _ = model.transcribe(audio_path, beam_size=5)
        text = " ".join([seg.text.strip() for seg in segments]).strip()
        return text
    except Exception as e:
        print(f"Whisper transcription error: {e}")
        return ""

def prepare_reference_audio(input_path: str, output_path: str, max_duration: float = 11.0, sample_rate: int = 24000) -> dict:
    """
    Cleans, normalizes, and extracts the optimal 5-11 second speech window for F5-TTS cloning.
    F5-TTS DiT operates best on 5-11s references; inputs >12s cause attention degradation and static loops.
    Even if user records 1-2 minutes, this extracts the cleanest speech sentence and its exact transcript.
    """
    temp_clean = output_path + ".temp_clean.wav"
    try:
        convert_to_wav(input_path, temp_clean, sample_rate=sample_rate, denoise=True)
        info = sf.info(temp_clean)
        total_dur = info.duration

        model = get_whisper()
        segs = []
        if model is not None:
            try:
                segments, _ = model.transcribe(temp_clean, beam_size=5)
                segs = list(segments)
            except Exception as e:
                print(f"Whisper transcribe failed in prepare_reference_audio: {e}")

        # If no speech segments detected by Whisper, slice first 8 seconds
        if not segs:
            slice_dur = min(total_dur, 8.0)
            subprocess.run([
                "ffmpeg", "-y", "-i", temp_clean,
                "-t", str(slice_dur),
                "-ar", str(sample_rate), "-ac", "1", "-c:a", "pcm_s16le",
                output_path
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            return {"transcript": "", "duration": slice_dur}

        # If audio is already within optimal window (<= max_duration)
        if total_dur <= max_duration:
            os.replace(temp_clean, output_path)
            full_text = " ".join([s.text.strip() for s in segs]).strip()
            return {"transcript": full_text, "duration": total_dur}

        # Long audio (> max_duration): pick the highest-quality 5-11s sentence/sequence
        best_segs = []
        accum_dur = 0.0
        for s in segs:
            sdur = s.end - s.start
            if not best_segs:
                if 5.0 <= sdur <= max_duration:
                    best_segs = [s]
                    break
                elif sdur < 5.0:
                    best_segs.append(s)
                    accum_dur += sdur
            else:
                if accum_dur + sdur <= max_duration:
                    best_segs.append(s)
                    accum_dur += sdur
                else:
                    break

        if not best_segs:
            best_segs = [segs[0]]

        start_t = max(0.0, best_segs[0].start - 0.05)
        end_t = min(total_dur, best_segs[-1].end + 0.05)
        slice_dur = end_t - start_t
        slice_text = " ".join([s.text.strip() for s in best_segs]).strip()

        subprocess.run([
            "ffmpeg", "-y", "-ss", str(start_t), "-i", temp_clean,
            "-to", str(slice_dur),
            "-ar", str(sample_rate), "-ac", "1", "-c:a", "pcm_s16le",
            output_path
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        return {"transcript": slice_text, "duration": slice_dur}

    finally:
        if os.path.exists(temp_clean):
            try:
                os.remove(temp_clean)
            except OSError:
                pass


def apply_micro_fade(wave: np.ndarray, sr: int = 24000, fade_sec: float = 0.02) -> np.ndarray:
    """
    Applies a smooth cosine fade-in and fade-out to prevent clicks/pops
    at audio boundaries and silence transitions.
    """
    fade_len = int(fade_sec * sr)
    if len(wave) <= 2 * fade_len:
        return wave
    fade_in = 0.5 * (1.0 - np.cos(np.pi * np.linspace(0.0, 1.0, fade_len)))
    fade_out = 0.5 * (1.0 + np.cos(np.pi * np.linspace(0.0, 1.0, fade_len)))
    wave_copy = wave.copy()
    wave_copy[:fade_len] *= fade_in
    wave_copy[-fade_len:] *= fade_out
    return wave_copy

def create_silence(duration: float, out_path: str, sample_rate: int = 48000):
    """Creates exact duration silence at target sample rate."""
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi", "-i",
        f"anullsrc=r={sample_rate}:cl=mono",
        "-t", str(duration),
        "-c:a", "pcm_s16le",
        out_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
