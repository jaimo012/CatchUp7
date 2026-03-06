import os
import time
from pathlib import Path

import requests

from config.settings import settings
from utils.logger import get_logger


logger = get_logger(__name__)

AUDIO_OUTPUT_DIR = "audio_output"
DEFAULT_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")
ELEVENLABS_API_URL_TEMPLATE = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
ELEVENLABS_MODEL_ID = "eleven_multilingual_v2"
REQUEST_TIMEOUT_SECONDS = 60
MAX_AUDIO_AGE_SECONDS = 24 * 60 * 60


def _ensure_audio_output_dir() -> str:
    os.makedirs(AUDIO_OUTPUT_DIR, exist_ok=True)
    return AUDIO_OUTPUT_DIR


def generate_audio(text: str, filename: str) -> str | None:
    if not text.strip():
        logger.error("Audio generation failed: empty text.")
        return None

    _ensure_audio_output_dir()

    voice_id = DEFAULT_VOICE_ID
    endpoint = ELEVENLABS_API_URL_TEMPLATE.format(voice_id=voice_id)
    headers = {
        "xi-api-key": settings.ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": text,
        "model_id": ELEVENLABS_MODEL_ID,
        "voice_settings": {
            "stability": 0.45,
            "similarity_boost": 0.8,
        },
    }

    try:
        response = requests.post(
            endpoint,
            headers=headers,
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.error("ElevenLabs API call failed for '%s': %s", filename, exc)
        return None

    normalized_filename = filename if filename.endswith(".mp3") else f"{filename}.mp3"
    output_path = Path(AUDIO_OUTPUT_DIR) / normalized_filename

    try:
        output_path.write_bytes(response.content)
    except OSError as exc:
        logger.error("Failed to save audio file '%s': %s", output_path, exc)
        return None

    logger.info("Audio generated successfully: %s", output_path)
    return str(output_path.resolve())


def cleanup_old_audios() -> None:
    _ensure_audio_output_dir()

    now_ts = time.time()
    deleted_count = 0

    for file_name in os.listdir(AUDIO_OUTPUT_DIR):
        if not file_name.lower().endswith(".mp3"):
            continue

        file_path = os.path.join(AUDIO_OUTPUT_DIR, file_name)
        if not os.path.isfile(file_path):
            continue

        file_age = now_ts - os.path.getmtime(file_path)
        if file_age <= MAX_AUDIO_AGE_SECONDS:
            continue

        try:
            os.remove(file_path)
            deleted_count += 1
        except OSError as exc:
            logger.error("Failed to remove old audio '%s': %s", file_path, exc)

    logger.info("Old audio cleanup completed. deleted=%d", deleted_count)
