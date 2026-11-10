import httpx
import logging
from fastapi import HTTPException, status
from typing import Optional, Dict, Any

from app.config import settings
from app.schemas import LanguageCode, TranscribeResponse
from app.services.audio_converter import convert_to_standard_wav

logger = logging.getLogger("voxflow.gnani_stt")

# Language code mapping for Gnani vachana STT v3
# Official codes: 'hi-IN' or 'hi' for Hindi, 'en-IN' or 'en' for English
GNANI_LANG_MAP = {
    LanguageCode.hi: "hi-IN",
    LanguageCode.hinglish: "hi-IN",
    LanguageCode.en: "en-IN",
}


async def transcribe_audio_gnani(
    audio_bytes: bytes,
    language: LanguageCode = LanguageCode.hinglish,
    filename: str = "voice_command.wav",
    content_type: str = "audio/wav",
) -> TranscribeResponse:
    """
    Sends actual uploaded audio to the official Gnani Prisma v2.5 Speech-to-Text API:
    - Endpoint: https://api.vachana.ai/stt/v3
    - Header: X-API-Key-ID: <GNANI_API_KEY>
    - Form data: audio_file (binary), language_code (string)
    - Default model is Prisma v2.5 when model is omitted.
    
    Does NOT return any hardcoded or mock transcripts.
    Does NOT require a separate GNANI_ACCESS_TOKEN.
    """
    # 1. Validate that GNANI_API_KEY is configured
    if not settings.GNANI_API_KEY or not settings.GNANI_API_KEY.strip():
        logger.error("GNANI_API_KEY is not configured in backend/.env")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Gnani Prisma STT service is not configured. "
                "Please configure GNANI_API_KEY in backend/.env to process live audio."
            ),
        )

    # Resolve official Gnani language code
    gnani_lang = GNANI_LANG_MAP.get(language, "hi-IN")

    # Convert browser audio (e.g. WebM/Opus) to standard PCM WAV if needed and ffmpeg is present
    if not filename.endswith(".mp3") and not filename.endswith(".wav"):
        audio_bytes, filename, mime = convert_to_standard_wav(audio_bytes, filename)
    else:
        mime = content_type or ("audio/mpeg" if filename.endswith(".mp3") else "audio/wav")

    # Official documented header: X-API-Key-ID
    headers = {
        "X-API-Key-ID": settings.GNANI_API_KEY.strip(),
        "User-Agent": "VoxFlow-Retail/1.0",
    }

    # Official documented multipart form fields:
    # 1. audio_file
    # 2. language_code
    files = {
        "audio_file": (filename, audio_bytes, mime),
    }
    data = {
        "language_code": gnani_lang,
    }

    logger.info(
        f"Calling Gnani STT endpoint: {settings.GNANI_STT_URL} "
        f"with language_code='{gnani_lang}', audio_file='{filename}' ({len(audio_bytes)} bytes, mime='{mime}')"
    )

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                settings.GNANI_STT_URL,
                headers=headers,
                files=files,
                data=data,
            )

        # Handle authentication failure
        if response.status_code in (401, 403):
            logger.error(f"Gnani authentication failed: HTTP {response.status_code} - {response.text}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication failed with Gnani STT API. Please verify that GNANI_API_KEY in backend/.env is valid and active.",
            )

        # Handle credit exhaustion / rate limit
        if response.status_code == 402:
            logger.error("Gnani account has insufficient credits (HTTP 402)")
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Insufficient credits on your Gnani AI account. Please recharge or check quota on the Gnani console.",
            )

        if response.status_code == 429:
            logger.error("Gnani rate limit exceeded (HTTP 429)")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Gnani STT API rate limit reached. Please wait a moment and try again.",
            )

        if not response.is_success:
            err_body = response.text
            logger.error(f"Gnani API returned error status {response.status_code}: {err_body}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Gnani STT API returned error (HTTP {response.status_code}): {err_body[:200]}",
            )

        result: Dict[str, Any] = response.json()
        logger.info(f"Gnani STT response received: keys={list(result.keys())}")

        # The official Gnani STT response structure:
        # e.g., {"transcript": "...", "confidence": 0.95} or {"data": {"transcript": "..."}, ...}
        transcript = None
        if isinstance(result, dict):
            transcript = (
                result.get("transcript")
                or result.get("transcription")
                or result.get("text")
                or result.get("asr_output")
                or (result.get("data", {}).get("transcript") if isinstance(result.get("data"), dict) else None)
                or (result.get("data", {}).get("text") if isinstance(result.get("data"), dict) else None)
                or (result.get("result", {}).get("transcript") if isinstance(result.get("result"), dict) else None)
            )

        if not transcript or not str(transcript).strip():
            logger.warning(f"Gnani returned no audible speech in response payload: {result}")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No clear speech could be transcribed from the uploaded audio file. Please speak clearly into the microphone and try again.",
            )

        # Extract confidence score if provided
        confidence = None
        raw_conf = (
            result.get("confidence")
            or result.get("confidence_score")
            or (result.get("data", {}).get("confidence") if isinstance(result.get("data"), dict) else None)
        )
        if raw_conf is not None:
            try:
                confidence = float(raw_conf)
                if confidence > 1.0:
                    confidence = confidence / 100.0
            except (ValueError, TypeError):
                confidence = None

        # Extract duration if provided
        duration = None
        raw_dur = (
            result.get("duration")
            or result.get("duration_seconds")
            or (result.get("data", {}).get("duration") if isinstance(result.get("data"), dict) else None)
        )
        if raw_dur is not None:
            try:
                duration = float(raw_dur)
            except (ValueError, TypeError):
                duration = None

        detected_lang = (
            result.get("detected_language")
            or result.get("language")
            or language.value
        )
        parsed_lang = LanguageCode(detected_lang) if detected_lang in LanguageCode.__members__ else language

        return TranscribeResponse(
            transcript=str(transcript).strip(),
            detectedLanguage=parsed_lang,
            confidenceScore=confidence,
            durationSeconds=duration,
        )

    except HTTPException:
        raise
    except httpx.ConnectError as ce:
        logger.error(f"Cannot connect to Gnani STT endpoint {settings.GNANI_STT_URL}: {ce}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unable to connect to Gnani STT endpoint at {settings.GNANI_STT_URL}. Please verify your network connection.",
        )
    except httpx.TimeoutException:
        logger.error("Gnani STT timed out after 45 seconds")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Gnani Prisma STT timed out waiting for audio processing.",
        )
    except Exception as e:
        logger.error(f"Unexpected error calling Gnani STT: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error processing audio with Gnani STT: {str(e)}",
        )
