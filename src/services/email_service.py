import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from pathlib import Path

from src.config import get_config

class EmailService:
    """郵件發送服務"""

    def __init__(self):
        self.smtp_server = get_config("EMAIL.SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = get_config("EMAIL.SMTP_PORT", 587)
        self.sender_email = get_config("EMAIL.SENDER_EMAIL", "")
        self.sender_password = get_config("EMAIL.APP_PASSWORD", "")  # Gmail 應用程式密碼
        self.recipient_email = get_config("EMAIL.RECIPIENT_EMAIL", "")

    def _truncate_channel_name(self, channel_name: str, max_length: int = 20) -> str:
        """截斷頻道名稱至指定長度（字符數）

        Args:
            channel_name: 原始頻道名稱
            max_length: 最大長度（預設20）

        Returns:
            str: 截斷後的頻道名稱
        """
        if not channel_name:
            return ""

        if len(channel_name) <= max_length:
            return channel_name

        index = -1
        if "吳淡如" in channel_name:
            index = channel_name.find("（")
        elif "區塊鏈日報" in channel_name:
            index = channel_name.find(" ")
        elif "Afford Anything Podcast" in channel_name:
            channel_name = "Afford Anything"

        if index != -1:
            channel_name = channel_name[:index]

        # 截斷至 max_length 個字符
        return channel_name[:max_length]

    def send_summary(self, title: str, summary_path: Path, channel_name: str = "") -> bool:
        """發送摘要郵件

        Args:
            title: 摘要標題
            summary_path: 摘要檔案路徑
            channel_name: 頻道名稱（可選，默認為空）

        Returns:
            bool: 是否發送成功
        """
        if not all([self.sender_email, self.sender_password, self.recipient_email]):
            print("郵件設定不完整，跳過發送")
            return False

        try:
            # 讀取摘要內容
            with open(summary_path, 'r', encoding='utf-8') as f:
                summary_content = f.read()

            # 截斷頻道名稱至20個字符
            truncated_channel = self._truncate_channel_name(channel_name)

            # 建立郵件
            msg = MIMEMultipart()
            msg['From'] = self.sender_email
            msg['To'] = self.recipient_email
            msg['Subject'] = Header(f'Whisper[{truncated_channel}] {title}', 'utf-8')

            # 郵件內容
            body = f"""
            <h2>{title}</h2>
            <pre style="white-space: pre-wrap; font-family: monospace;">
            {summary_content}
            </pre>
            <hr>
            <p><small>此郵件由 Whisper WebUI 自動發送</small></p>
            """
            msg.attach(MIMEText(body, 'html', 'utf-8'))

            # 發送郵件
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.send_message(msg)

            print(f"摘要郵件發送成功：{title}")
            return True

        except Exception as e:
            print(f"發送摘要郵件時發生錯誤：{str(e)}")
            return False
