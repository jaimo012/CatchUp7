from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import BackgroundTasks, FastAPI

from services import (
    GoogleSheetsClient,
    cleanup_old_audios,
    collect_daily_news,
    build_audio_filename,
    filter_duplicate_articles,
    format_slack_messages,
    generate_agenda,
    generate_audio,
    prepare_final_data,
    send_main_message,
    send_thread_reply_with_file,
    write_script,
)
from utils import get_logger, merge_by_url


logger = get_logger(__name__)

APP_TIMEZONE = ZoneInfo("Asia/Seoul")
BRIEFING_ERROR_MESSAGE = "오늘은 브리핑할 뉴스가 없거나 시스템 에러가 발생했습니다."

scheduler = BackgroundScheduler(timezone=APP_TIMEZONE)


def _send_failure_message() -> None:
    try:
        send_main_message(BRIEFING_ERROR_MESSAGE)
    except Exception as exc:
        logger.error("Failed to send fallback Slack message: %s", exc)


def run_daily_briefing() -> None:
    logger.info("Daily briefing pipeline started.")

    try:
        all_articles, prompt_criteria = collect_daily_news()
        if not all_articles:
            logger.info("No collected articles. Send fallback message and stop.")
            _send_failure_message()
            return

        merged_articles = merge_by_url(all_articles)
        deduplicated_articles = filter_duplicate_articles(merged_articles)
        if not deduplicated_articles:
            logger.info("No deduplicated articles. Send fallback message and stop.")
            _send_failure_message()
            return

        deep_dive_articles, short_brief_articles = prepare_final_data(
            deduplicated_articles,
            prompt_criteria,
        )
        if not deep_dive_articles and not short_brief_articles:
            logger.info("No selected articles. Send fallback message and stop.")
            _send_failure_message()
            return

        try:
            final_selected_articles = deep_dive_articles + short_brief_articles
            GoogleSheetsClient().append_news_to_sheet(final_selected_articles)
        except Exception as exc:
            logger.error("Failed to append final selected articles into News sheet: %s", exc)

        agenda_json = generate_agenda(deep_dive_articles, short_brief_articles)
        final_script_dict = write_script(
            agenda_json=agenda_json,
            deep_dive_articles=deep_dive_articles,
            short_brief_articles=short_brief_articles,
        )
        slack_payload = format_slack_messages(
            final_script_dict=final_script_dict,
            deep_dive_articles=deep_dive_articles,
            short_brief_articles=short_brief_articles,
        )

        section_scripts = final_script_dict.get("sections", {})
        audio_paths: dict[str, str] = {}
        deep_dive_title_by_id = {
            str(article.get("id", "")): str(article.get("title", "")).strip()
            for article in deep_dive_articles
        }
        deep_dive_audio_key_by_id = {
            str(article.get("id", "")): f"deep_dive_{index}"
            for index, article in enumerate(deep_dive_articles, start=1)
        }
        section_title_fallback = {
            "opening": "오프닝",
            "short_brief": "단신 브리핑",
            "closing": "클로징",
        }

        if isinstance(section_scripts, dict):
            for section_key, section_text in section_scripts.items():
                if not isinstance(section_text, str) or not section_text.strip():
                    continue

                filename_title = section_title_fallback.get(section_key, section_key)
                if section_key.startswith("deep_dive_"):
                    matching_article_id = next(
                        (
                            article_id
                            for article_id, audio_key in deep_dive_audio_key_by_id.items()
                            if audio_key == section_key
                        ),
                        "",
                    )
                    if matching_article_id:
                        filename_title = deep_dive_title_by_id.get(matching_article_id, filename_title)

                audio_path = generate_audio(
                    text=section_text,
                    filename=build_audio_filename(filename_title, datetime.now(APP_TIMEZONE)),
                )
                if audio_path:
                    audio_paths[section_key] = audio_path

        slack_messages = slack_payload.get("slack_messages", [])
        if not isinstance(slack_messages, list) or not slack_messages:
            logger.error("Slack payload has no messages.")
            _send_failure_message()
            cleanup_old_audios()
            return

        main_text = BRIEFING_ERROR_MESSAGE
        for message in slack_messages:
            if isinstance(message, dict) and message.get("type") == "main":
                main_text = str(message.get("text", "")).strip() or BRIEFING_ERROR_MESSAGE
                break

        thread_ts = send_main_message(main_text)
        if not thread_ts:
            logger.error("Failed to send main Slack message. Stop thread replies.")
            cleanup_old_audios()
            return

        for message in slack_messages:
            if not isinstance(message, dict):
                continue

            message_type = str(message.get("type", "")).strip()
            if message_type == "main":
                continue

            text = str(message.get("text", "")).strip()
            file_path: str | None = None

            if message_type == "thread_deep_dive":
                article_id = str(message.get("article_id", "")).strip()
                audio_key = deep_dive_audio_key_by_id.get(article_id, "")
                file_path = audio_paths.get(audio_key)
            elif message_type == "thread_short_brief":
                file_path = audio_paths.get("short_brief")

            send_thread_reply_with_file(
                thread_ts=thread_ts,
                text=text,
                file_path=file_path,
            )

        cleanup_old_audios()
        logger.info("Daily briefing pipeline completed.")
    except Exception as exc:
        logger.error("Daily briefing pipeline failed: %s", exc)
        _send_failure_message()


@asynccontextmanager
async def lifespan(_: FastAPI):
    scheduler.add_job(
        run_daily_briefing,
        trigger=CronTrigger(hour=7, minute=0, timezone=APP_TIMEZONE),
        id="daily_briefing_job",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started: daily 07:00 Asia/Seoul")
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")


app = FastAPI(title="Catch-up 0700", lifespan=lifespan)


@app.get("/run")
def run_now(background_tasks: BackgroundTasks) -> dict[str, str]:
    background_tasks.add_task(run_daily_briefing)
    return {"message": "Daily briefing started in background."}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
