from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status
import logging

from app.schemas import LanguageCode, TranscribeResponse
from app.services.gnani_stt import transcribe_audio_gnani

router = APIRouter(prefix="/api/v1/voice", tags=["Voice"])
logger = logging.getLogger("voxflow.voice")

MAX_FILE_SIZE = 15 * 1024 * 1024  # 15 MB limit
ALLOWED_MIME_TYPES = [
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/mpeg",
    "audio/mp3",
    "audio/m4a",
    "audio/x-m4a",
    "audio/ogg",
    "audio/webm",
    "application/octet-stream",
]


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_voice(
    file: UploadFile = File(...),
    language: LanguageCode = Form(LanguageCode.hinglish),
):
    """
    Accepts real audio file, validates MIME type and file size, and streams
    it directly to the Gnani Prisma Speech-to-Text API.
    Does NOT return hardcoded mock transcripts.
    """
    content_type = file.content_type or ""
    filename = file.filename or "audio.wav"
    ext = filename.split(".")[-1].lower() if "." in filename else ""

    # Correctly allow all standard audio containers
    if content_type not in ALLOWED_MIME_TYPES and ext not in ["wav", "mp3", "m4a", "ogg", "webm"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported audio format: '{content_type or ext}'. Please upload WAV, MP3, M4A, OGG, or WebM audio.",
        )

    # Read and check size
    audio_bytes = await file.read()
    if len(audio_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded audio file is empty (0 bytes).",
        )
    if len(audio_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Audio file exceeds max size limit of 15MB ({len(audio_bytes) / 1024 / 1024:.2f}MB).",
        )

    return await transcribe_audio_gnani(
        audio_bytes=audio_bytes,
        language=language,
        filename=filename,
        content_type=content_type,
    )
