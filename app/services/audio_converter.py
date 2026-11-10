import shutil
import subprocess
import tempfile
import os
import logging
from typing import Tuple

logger = logging.getLogger("voxflow.audio_converter")


def convert_to_standard_wav(audio_bytes: bytes, original_filename: str) -> Tuple[bytes, str, str]:
    """
    Checks if ffmpeg is available on the host system.
    If ffmpeg is installed, converts arbitrary audio (WebM, OGG, M4A, Opus)
    into standard 16kHz mono 16-bit PCM WAV (which is universally accepted by all speech engines including Gnani).
    If ffmpeg is not installed or the input is already MP3 or WAV, returns the original audio.
    """
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        logger.warning("ffmpeg is not found on PATH. Proceeding with original audio payload.")
        return audio_bytes, original_filename, "audio/wav" if original_filename.endswith(".wav") else "audio/mpeg"

    suffix = os.path.splitext(original_filename)[1] or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as in_file:
        in_file.write(audio_bytes)
        in_path = in_file.name

    out_path = in_path + ".wav"
    try:
        # Convert to 16kHz, mono, PCM 16-bit WAV
        cmd = [
            ffmpeg_bin,
            "-y",
            "-i", in_path,
            "-ar", "16000",
            "-ac", "1",
            "-c:a", "pcm_s16le",
            out_path,
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        if result.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            with open(out_path, "rb") as f:
                converted_bytes = f.read()
            logger.info(f"Successfully converted {original_filename} ({len(audio_bytes)} bytes) to 16kHz PCM WAV ({len(converted_bytes)} bytes)")
            return converted_bytes, "voice_command.wav", "audio/wav"
        else:
            logger.warning(f"ffmpeg conversion returned non-zero code {result.returncode}: {result.stderr.decode('utf-8', errors='ignore')[:200]}")
            return audio_bytes, original_filename, "audio/webm"
    except Exception as e:
        logger.error(f"Error during audio conversion with ffmpeg: {e}")
        return audio_bytes, original_filename, "audio/webm"
    finally:
        for p in (in_path, out_path):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

