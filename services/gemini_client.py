import json
from typing import Any

import google.generativeai as genai

from config.settings import settings
from utils.logger import get_logger


logger = get_logger(__name__)

DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
JSON_MIME_TYPE = "application/json"


class GeminiClient:
    def __init__(self, model_name: str = DEFAULT_GEMINI_MODEL) -> None:
        self.model_name = model_name
        genai.configure(api_key=settings.GEMINI_API_KEY)

    def generate_json_response(
        self,
        system_instruction: str,
        user_prompt: str,
    ) -> dict[str, Any] | None:
        try:
            model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=system_instruction,
            )
            response = model.generate_content(
                user_prompt,
                generation_config={
                    "response_mime_type": JSON_MIME_TYPE,
                },
            )

            response_text = getattr(response, "text", "") or ""
            if not response_text.strip():
                logger.error("Gemini returned an empty response.")
                return None

            return json.loads(response_text)
        except Exception as exc:
            logger.error("Gemini API call failed: %s", exc)
            return None
