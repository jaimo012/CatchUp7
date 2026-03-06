import json
from datetime import datetime
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

from config.settings import settings
from utils.logger import get_logger


logger = get_logger(__name__)


class GoogleSheetsClient:
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

    def __init__(self, spreadsheet_id: str | None = None) -> None:
        self.spreadsheet_id = spreadsheet_id or settings.SPREADSHEET_ID
        self.service = self._build_service()

    def _build_service(self) -> Any:
        try:
            credentials_info = json.loads(settings.GOOGLE_CREDENTIALS_JSON)
            credentials = service_account.Credentials.from_service_account_info(
                credentials_info,
                scopes=self.SCOPES,
            )
            return build("sheets", "v4", credentials=credentials)
        except Exception as exc:
            logger.error("Failed to authenticate Google Sheets client: %s", exc)
            raise RuntimeError("Google Sheets authentication failed.") from exc

    def get_config_data(self) -> dict[str, Any]:
        try:
            response = (
                self.service.spreadsheets()
                .values()
                .get(spreadsheetId=self.spreadsheet_id, range="Setting!A2:B")
                .execute()
            )
            rows = response.get("values", [])

            keywords: list[str] = []
            prompt_lines: list[str] = []

            for row in rows:
                if not isinstance(row, list):
                    continue

                keyword_value = str(row[0]).strip() if len(row) > 0 else ""
                prompt_value = str(row[1]).strip() if len(row) > 1 else ""

                if keyword_value:
                    keywords.append(keyword_value)
                if prompt_value:
                    prompt_lines.append(prompt_value)

            prompt_criteria = "\n".join(prompt_lines)

            return {
                "keywords": keywords,
                "prompt_criteria": prompt_criteria,
            }
        except Exception as exc:
            logger.error("Failed to read Google Sheets config data: %s", exc)
            raise RuntimeError("Google Sheets data read failed.") from exc

    def append_news_to_sheet(self, articles: list[dict]) -> None:
        if not articles:
            logger.info("No articles to append into News sheet.")
            return

        today_str = datetime.now().strftime("%Y-%m-%d")
        rows: list[list[str]] = []

        for article in articles:
            pub_date_raw = str(article.get("pubDate", "")).strip()
            pub_date_str = self._format_pub_date(pub_date_raw)

            title = str(article.get("title", "")).strip()
            description = str(article.get("description", "")).strip()
            if len(description) > 200:
                description = f"{description[:200]}..."

            link = str(article.get("originallink") or article.get("link") or "").strip()

            rows.append([today_str, pub_date_str, title, description, link])

        try:
            self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range="News!A:E",
                valueInputOption="USER_ENTERED",
                body={"values": rows},
            ).execute()
            logger.info("News sheet append success. rows=%d", len(rows))
        except Exception as exc:
            logger.error("Failed to append rows into News sheet: %s", exc)
            raise RuntimeError("Google Sheets append failed.") from exc

    @staticmethod
    def _format_pub_date(pub_date_raw: str) -> str:
        if not pub_date_raw:
            return ""

        datetime_formats = [
            "%a, %d %b %Y %H:%M:%S %z",
            "%Y-%m-%d",
        ]
        for datetime_format in datetime_formats:
            try:
                return datetime.strptime(pub_date_raw, datetime_format).strftime("%Y-%m-%d")
            except ValueError:
                continue

        return ""
