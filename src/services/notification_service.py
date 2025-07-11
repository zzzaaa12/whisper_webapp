
import requests
from src.config import get_config

class NotificationService:
    """統一通知服務"""

    def send_telegram_notification(self, message: str) -> bool:
        """統一Telegram通知函數"""
        bot_token = get_config('TELEGRAM_BOT_TOKEN')
        chat_id = get_config('TELEGRAM_CHAT_ID')

        if not bot_token or not chat_id:
            print("[NOTIFICATION] Telegram credentials not set. Skipping notification.")
            return False

        api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'Markdown'
        }

        try:
            response = requests.post(api_url, data=payload, timeout=5)
            if response.status_code == 200:
                return True
            else:
                print(f"[NOTIFICATION] Error sending Telegram message: {response.text}")
                return False
        except Exception as e:
            print(f"[NOTIFICATION] Exception while sending Telegram message: {e}")
            return False

# 全域單例實例
_notification_service = NotificationService()

def send_telegram_notification(message: str) -> bool:
    """便捷Telegram通知函數"""
    return _notification_service.send_telegram_notification(message)
