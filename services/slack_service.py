from pathlib import Path

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from config.settings import settings
from utils.logger import get_logger


logger = get_logger(__name__)
slack_client = WebClient(token=settings.SLACK_BOT_TOKEN)


def send_main_message(text: str) -> str | None:
    try:
        response = slack_client.chat_postMessage(
            channel=settings.SLACK_CHANNEL_ID,
            text=text,
        )
        thread_ts = response.get("ts")
        if not thread_ts:
            logger.error("Slack main message sent but ts is missing.")
            return None

        logger.info("Slack main message sent successfully. ts=%s", thread_ts)
        return str(thread_ts)
    except SlackApiError as exc:
        logger.error("Failed to send Slack main message: %s", exc.response.get("error"))
        return None
    except Exception as exc:
        logger.error("Unexpected error while sending Slack main message: %s", exc)
        return None


def send_thread_reply_with_file(
    thread_ts: str,
    text: str,
    file_path: str | None = None,
) -> bool:
    if file_path:
        path = Path(file_path)
        if not path.is_file():
            logger.error("Slack thread file does not exist: %s", file_path)
            return False

        try:
            slack_client.files_upload_v2(
                channel=settings.SLACK_CHANNEL_ID,
                thread_ts=thread_ts,
                file=str(path),
                filename=path.name,
                initial_comment=text,
            )
            logger.info("Slack thread file upload succeeded. thread_ts=%s file=%s", thread_ts, path.name)
            return True
        except SlackApiError as exc:
            logger.error("Failed to upload file to Slack thread: %s", exc.response.get("error"))
            return False
        except Exception as exc:
            logger.error("Unexpected error while uploading Slack file: %s", exc)
            return False

    try:
        slack_client.chat_postMessage(
            channel=settings.SLACK_CHANNEL_ID,
            thread_ts=thread_ts,
            text=text,
        )
        logger.info("Slack thread text reply sent. thread_ts=%s", thread_ts)
        return True
    except SlackApiError as exc:
        logger.error("Failed to send Slack thread text reply: %s", exc.response.get("error"))
        return False
    except Exception as exc:
        logger.error("Unexpected error while sending Slack thread text reply: %s", exc)
        return False
