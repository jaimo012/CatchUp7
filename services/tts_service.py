import os
import re
import time
import json
from datetime import datetime
from pathlib import Path

import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from config.settings import settings
from utils.logger import get_logger


logger = get_logger(__name__)

AUDIO_OUTPUT_DIR = os.getenv("AUDIO_OUTPUT_DIR", "audio_output")
DEFAULT_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")
ELEVENLABS_API_URL_TEMPLATE = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
ELEVENLABS_MODEL_ID = "eleven_multilingual_v2"
REQUEST_TIMEOUT_SECONDS = 60
MAX_AUDIO_AGE_SECONDS = 24 * 60 * 60
GOOGLE_DRIVE_AUDIO_FOLDER_ID = os.getenv("GOOGLE_DRIVE_AUDIO_FOLDER_ID", "103dM-wvNb8cUNfsGuMYA0vIOUa3mgLn6")
GOOGLE_DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def _ensure_audio_output_dir() -> str:
    os.makedirs(AUDIO_OUTPUT_DIR, exist_ok=True)
    return AUDIO_OUTPUT_DIR


def _sanitize_filename_component(text: str) -> str:
    sanitized = re.sub(r"[\\/:*?\"<>|]+", " ", text)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    if not sanitized:
        return "audio"
    return sanitized[:80]


def build_audio_filename(article_title: str, created_at: datetime | None = None) -> str:
    current = created_at or datetime.now()
    date_prefix = current.strftime("%y%m%d")
    title_part = _sanitize_filename_component(article_title)
    return f"{date_prefix}_{title_part}"


def _upload_to_google_drive(local_file_path: Path) -> None:
    if not GOOGLE_DRIVE_AUDIO_FOLDER_ID:
        return

    try:
        credentials_info = json.loads(settings.GOOGLE_CREDENTIALS_JSON)
        credentials = service_account.Credentials.from_service_account_info(
            credentials_info,
            scopes=GOOGLE_DRIVE_SCOPES,
        )
        drive_service = build("drive", "v3", credentials=credentials)

        media = MediaFileUpload(str(local_file_path), mimetype="audio/mpeg", resumable=False)
        file_metadata = {
            "name": local_file_path.name,
            "parents": [GOOGLE_DRIVE_AUDIO_FOLDER_ID],
        }
        created = (
            drive_service.files()
            .create(
                body=file_metadata,
                media_body=media,
                fields="id,name,webViewLink",
            )
            .execute()
        )
        logger.info(
            "Uploaded audio to Google Drive folder. file_id=%s, name=%s",
            created.get("id"),
            created.get("name"),
        )
    except Exception as exc:
        logger.error("Google Drive upload failed for '%s': %s", local_file_path.name, exc)


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

    normalized_filename = _sanitize_filename_component(filename)
    normalized_filename = (
        normalized_filename if normalized_filename.endswith(".mp3") else f"{normalized_filename}.mp3"
    )
    output_path = Path(AUDIO_OUTPUT_DIR) / normalized_filename

    try:
        output_path.write_bytes(response.content)
    except OSError as exc:
        logger.error("Failed to save audio file '%s': %s", output_path, exc)
        return None

    _upload_to_google_drive(output_path)
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
