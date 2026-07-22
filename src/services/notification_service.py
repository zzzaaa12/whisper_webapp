"""Reliable Telegram notification delivery."""

from __future__ import annotations

import time

import requests

from src.config import get_config
from src.utils.logger_manager import get_logger_manager


TELEGRAM_TEXT_LIMIT = 4096
TELEGRAM_CHUNK_SIZE = 3800


def _split_message(message: str, limit: int = TELEGRAM_CHUNK_SIZE) -> list[str]:
    """Split plain text on line boundaries, with a hard limit fallback."""
    text = str(message or "").strip()
    if not text:
        return []

    chunks: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:
            if current:
                chunks.append(current.rstrip())
                current = ""
            chunks.append(line[:limit].rstrip())
            line = line[limit:]

        if len(current) + len(line) > limit:
            chunks.append(current.rstrip())
            current = line
        else:
            current += line

    if current.strip():
        chunks.append(current.rstrip())
    return chunks


class NotificationService:
    """Send Telegram notifications with splitting and transient retries."""

    def __init__(self, post=None, sleep=None):
        self._post = post or requests.post
        self._sleep = sleep or time.sleep

    @staticmethod
    def _error_description(response) -> tuple[str, int | None]:
        try:
            body = response.json()
        except (ValueError, TypeError):
            return "invalid Telegram response", None

        description = str(body.get("description", "Telegram API error"))[:500]
        parameters = body.get("parameters") or {}
        retry_after = parameters.get("retry_after")
        try:
            retry_after = int(retry_after) if retry_after is not None else None
        except (TypeError, ValueError):
            retry_after = None
        return description, retry_after

    def _send_chunk(self, api_url: str, chat_id: str, text: str) -> bool:
        logger = get_logger_manager()
        max_attempts = max(1, int(get_config("TELEGRAM_MAX_ATTEMPTS", 3)))

        for attempt in range(1, max_attempts + 1):
            try:
                response = self._post(
                    api_url,
                    data={"chat_id": chat_id, "text": text},
                    timeout=(5, 15),
                )
                if response.status_code == 200:
                    return True

                description, retry_after = self._error_description(response)
                retryable = response.status_code == 429 or response.status_code >= 500
                logger.warning(
                    f"Telegram send failed: status={response.status_code} "
                    f"attempt={attempt}/{max_attempts} error={description}",
                    "notification",
                )
                if not retryable or attempt >= max_attempts:
                    return False

                delay = retry_after if retry_after is not None else min(2 ** (attempt - 1), 8)
                self._sleep(max(1, delay))
            except requests.RequestException as error:
                logger.warning(
                    f"Telegram network error: type={type(error).__name__} "
                    f"attempt={attempt}/{max_attempts}",
                    "notification",
                )
                if attempt >= max_attempts:
                    return False
                self._sleep(min(2 ** (attempt - 1), 8))

        return False

    def send_telegram_notification(self, message: str) -> bool:
        bot_token = get_config("TELEGRAM_BOT_TOKEN")
        chat_id = get_config("TELEGRAM_CHAT_ID")
        logger = get_logger_manager()

        if not bot_token or not chat_id:
            logger.debug("Telegram credentials not set. Skipping notification.", "notification")
            return False

        chunks = _split_message(message)
        if not chunks:
            logger.warning("Skipped empty Telegram notification", "notification")
            return False

        api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        total = len(chunks)
        for index, chunk in enumerate(chunks, start=1):
            if total > 1:
                chunk = f"({index}/{total})\n{chunk}"
            if len(chunk) > TELEGRAM_TEXT_LIMIT:
                logger.error("Telegram chunk exceeded safe text limit", "notification")
                return False
            if not self._send_chunk(api_url, str(chat_id), chunk):
                logger.error(
                    f"Telegram notification incomplete: failed_chunk={index}/{total}",
                    "notification",
                )
                return False

        logger.info(f"Telegram notification sent: chunks={total}", "notification")
        return True


_notification_service = NotificationService()


def send_telegram_notification(message: str) -> bool:
    return _notification_service.send_telegram_notification(message)