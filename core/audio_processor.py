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

def convert_to_wav(input_path: str, output_path: str, sample_rate: int = 24000) -> str:
    """Converts any input audio file to standard mono 16-bit PCM WAV at target sample rate."""
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-ar", str(sample_rate),
        "-ac", "1",
        "-c:a", "pcm_s16le",
        output_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return output_path

def auto_transcribe(audio_path: str) -> str:
    """Automatically transcribes reference audio using local Whisper."""
    model = get_whisper()
    if model is None:
        return ""
    segments, _ = model.transcribe(audio_path, language="en")
    text = " ".join([seg.text.strip() for seg in segments]).strip()
    return text

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
