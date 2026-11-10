import httpx
import logging
from typing import Optional
from app.config import settings

logger = logging.getLogger("voxflow.gnani_tts")


async def synthesize_speech_gnani(
    text: str,
    language: str = "hi",
    voice_gender: str = "female",
) -> Optional[bytes]:
    """
    Synthesize spoken confirmation using Gnani Timbre v2.5 TTS API.
    Returns audio bytes (WAV/MP3) or None if service is unconfigured.
    """
    if not settings.GNANI_API_KEY or not settings.GNANI_ACCESS_TOKEN:
        logger.info("Gnani Timbre TTS unconfigured. Spoken confirmation skipped.")
        return None

    try:
        headers = {
            "x-api-key": settings.GNANI_API_KEY,
            "Authorization": f"Bearer {settings.GNANI_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }
        payload = {
            "text": text,
            "language": language,
            "gender": voice_gender,
            "audio_format": "wav",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                settings.GNANI_TTS_URL,
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            return response.content
    except Exception as e:
        logger.error(f"Gnani Timbre TTS synthesis error: {e}")
        return None

