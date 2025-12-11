import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from pathlib import Path
import re

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
        """截斷頻道名稱至指定長度（字符數）"""
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

        return channel_name[:max_length]

    def _parse_summary_content(self, content: str) -> dict:
        """解析摘要內容，提取各區塊"""
        result = {
            'ai_info': '',
            'title': '',
            'channel': '',
            'duration': '',
            'url': '',
            'process_time': '',
            'core_topic': '',
            'key_points': '',
            'quotes': '',
            'conclusion': ''
        }
        
        lines = content.split('\n')
        current_section = None
        section_content = []
        
        for line in lines:
            # 解析 header 資訊
            if line.startswith('🤖 AI 摘要：'):
                result['ai_info'] = line.replace('🤖 AI 摘要：', '').strip()
            elif line.startswith('🎬 標題：'):
                result['title'] = line.replace('🎬 標題：', '').strip()
            elif line.startswith('📺 頻道：'):
                result['channel'] = line.replace('📺 頻道：', '').strip()
            elif line.startswith('⏱️ 影片長度：'):
                result['duration'] = line.replace('⏱️ 影片長度：', '').strip()
            elif line.startswith('🔗 網址：'):
                result['url'] = line.replace('🔗 網址：', '').strip()
            elif line.startswith('⏰ 處理時間：'):
                result['process_time'] = line.replace('⏰ 處理時間：', '').strip()
            # 解析各區塊
            elif '## 🎯 核心主題' in line or '# 🎯 核心主題' in line:
                if current_section and section_content:
                    result[current_section] = '\n'.join(section_content)
                current_section = 'core_topic'
                section_content = []
            elif '## 📝 重點整理' in line or '# 📝 重點整理' in line:
                if current_section and section_content:
                    result[current_section] = '\n'.join(section_content)
                current_section = 'key_points'
                section_content = []
            elif '## 💬 關鍵金句' in line or '# 💬 關鍵金句' in line:
                if current_section and section_content:
                    result[current_section] = '\n'.join(section_content)
                current_section = 'quotes'
                section_content = []
            elif '## 🎯 總結' in line or '# 🎯 總結' in line:
                if current_section and section_content:
                    result[current_section] = '\n'.join(section_content)
                current_section = 'conclusion'
                section_content = []
            elif current_section and line.strip() and not line.startswith('=='):
                section_content.append(line)
        
        # 儲存最後一個區塊
        if current_section and section_content:
            result[current_section] = '\n'.join(section_content)
        
        return result

    def _markdown_to_html(self, text: str) -> str:
        """將 Markdown 轉換為 HTML"""
        if not text:
            return ""
        
        lines = text.split('\n')
        html_lines = []
        in_list = False
        list_type = None  # 'ul' or 'ol'
        
        for line in lines:
            stripped = line.strip()
            if not stripped:
                if in_list:
                    html_lines.append(f'</{list_type}>')
                    in_list = False
                continue
            
            # 處理粗體
            stripped = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', stripped)
            
            # 處理引用
            if stripped.startswith('>'):
                quote_text = stripped[1:].strip().strip('"「」')
                html_lines.append(f'<blockquote style="border-left: 3px solid #667eea; padding-left: 15px; margin: 12px 0; color: #4a5568; font-style: italic; font-size: 16px;">"{quote_text}"</blockquote>')
                continue
            
            # 處理有序列表
            ol_match = re.match(r'^(\d+)\.\s+(.+)$', stripped)
            if ol_match:
                if not in_list or list_type != 'ol':
                    if in_list:
                        html_lines.append(f'</{list_type}>')
                    html_lines.append('<ol style="margin: 10px 0; padding-left: 24px; font-size: 16px;">')
                    in_list = True
                    list_type = 'ol'
                html_lines.append(f'<li style="margin: 8px 0; line-height: 1.8;">{ol_match.group(2)}</li>')
                continue
            
            # 處理無序列表
            if stripped.startswith('- ') or stripped.startswith('• '):
                if not in_list or list_type != 'ul':
                    if in_list:
                        html_lines.append(f'</{list_type}>')
                    html_lines.append('<ul style="margin: 10px 0; padding-left: 24px; font-size: 16px;">')
                    in_list = True
                    list_type = 'ul'
                content = stripped[2:] if stripped.startswith('- ') else stripped[2:]
                html_lines.append(f'<li style="margin: 8px 0; line-height: 1.8;">{content}</li>')
                continue
            
            # 處理縮排的子項目
            if line.startswith('   ') and in_list:
                sub_content = stripped
                if sub_content.startswith('- '):
                    sub_content = sub_content[2:]
                html_lines.append(f'<li style="margin: 6px 0; margin-left: 24px; line-height: 1.7; list-style-type: circle;">{sub_content}</li>')
                continue
            
            # 關閉列表並添加段落
            if in_list:
                html_lines.append(f'</{list_type}>')
                in_list = False
            
            html_lines.append(f'<p style="margin: 10px 0; line-height: 1.8; font-size: 16px;">{stripped}</p>')
        
        if in_list:
            html_lines.append(f'</{list_type}>')
        
        return '\n'.join(html_lines)

    def _build_html_email(self, parsed: dict, title: str, channel_name: str) -> str:
        """建立精美的 HTML 郵件"""
        
        video_url = parsed.get('url', '')
        display_title = parsed.get('title', '') or title
        display_channel = parsed.get('channel', '') or channel_name
        duration = parsed.get('duration', '')
        process_time = parsed.get('process_time', '')
        ai_info = parsed.get('ai_info', '')
        
        # 轉換各區塊為 HTML
        core_topic_html = self._markdown_to_html(parsed.get('core_topic', ''))
        key_points_html = self._markdown_to_html(parsed.get('key_points', ''))
        quotes_html = self._markdown_to_html(parsed.get('quotes', ''))
        conclusion_html = self._markdown_to_html(parsed.get('conclusion', ''))
        
        # 建立影片按鈕
        video_button = ''
        if video_url:
            video_button = f'''
            <a href="{video_url}" target="_blank" style="display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 12px 24px; border-radius: 25px; text-decoration: none; font-weight: 500; margin-top: 15px; font-size: 15px;">
                ▶️ 觀看原始影片
            </a>
            '''
        
        html = f'''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f5f7fa;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f5f7fa; padding: 30px 15px;">
        <tr>
            <td align="center">
                <!-- 主容器：電腦版最大 800px，手機版自適應 -->
                <table cellpadding="0" cellspacing="0" style="max-width: 800px; width: 100%; background-color: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);">
                    
                    <!-- Header -->
                    <tr>
                        <td style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 35px 30px; text-align: center;">
                            <h1 style="margin: 0; color: white; font-size: 28px; font-weight: 600; letter-spacing: 0.5px;">
                                🎬 影片摘要
                            </h1>
                        </td>
                    </tr>
                    
                    <!-- Video Info Card -->
                    <tr>
                        <td style="padding: 30px;">
                            <table width="100%" cellpadding="0" cellspacing="0" style="background: linear-gradient(135deg, #f8f9ff 0%, #f0f4ff 100%); border-radius: 12px;">
                                <tr>
                                    <td style="padding: 25px;">
                                        <h2 style="margin: 0 0 18px 0; color: #1a202c; font-size: 22px; font-weight: 600; line-height: 1.5;">
                                            {display_title}
                                        </h2>
                                        <table cellpadding="0" cellspacing="0" style="width: 100%;">
                                            <tr>
                                                <td style="padding: 6px 0;">
                                                    <span style="color: #718096; font-size: 15px;">📺 頻道：</span>
                                                    <span style="color: #4a5568; font-size: 15px; font-weight: 500;">{display_channel}</span>
                                                </td>
                                            </tr>
                                            {f'<tr><td style="padding: 6px 0;"><span style="color: #718096; font-size: 15px;">⏱️ 長度：</span><span style="color: #4a5568; font-size: 15px;">{duration}</span></td></tr>' if duration else ''}
                                            {f'<tr><td style="padding: 6px 0;"><span style="color: #718096; font-size: 15px;">🤖 AI：</span><span style="color: #4a5568; font-size: 15px;">{ai_info}</span></td></tr>' if ai_info else ''}
                                            {f'<tr><td style="padding: 6px 0;"><span style="color: #718096; font-size: 15px;">⏰ 處理：</span><span style="color: #4a5568; font-size: 15px;">{process_time}</span></td></tr>' if process_time else ''}
                                        </table>
                                        {video_button}
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    
                    <!-- Core Topic Section -->
                    {self._build_section('🎯 核心主題', core_topic_html, '#667eea') if core_topic_html else ''}
                    
                    <!-- Key Points Section -->
                    {self._build_section('📝 重點整理', key_points_html, '#48bb78') if key_points_html else ''}
                    
                    <!-- Quotes Section -->
                    {self._build_section('💬 關鍵金句', quotes_html, '#ed8936') if quotes_html else ''}
                    
                    <!-- Conclusion Section -->
                    {self._build_section('🎯 總結', conclusion_html, '#9f7aea') if conclusion_html else ''}
                    
                    <!-- Footer -->
                    <tr>
                        <td style="background-color: #f8fafc; padding: 25px 30px; text-align: center; border-top: 1px solid #e2e8f0;">
                            <p style="margin: 0; color: #a0aec0; font-size: 14px;">
                                此郵件由 <strong style="color: #718096;">Whisper WebUI</strong> 自動發送
                            </p>
                        </td>
                    </tr>
                    
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
'''
        return html

    def _build_section(self, title: str, content: str, color: str) -> str:
        """建立區塊 HTML"""
        if not content:
            return ''
        
        return f'''
        <tr>
            <td style="padding: 0 30px 25px 30px;">
                <table width="100%" cellpadding="0" cellspacing="0" style="border-left: 4px solid {color}; padding-left: 20px;">
                    <tr>
                        <td>
                            <h3 style="margin: 0 0 15px 0; color: #2d3748; font-size: 18px; font-weight: 600;">
                                {title}
                            </h3>
                            <div style="color: #4a5568; font-size: 16px; line-height: 1.8;">
                                {content}
                            </div>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
        '''

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

            # 解析摘要內容
            parsed = self._parse_summary_content(summary_content)
            
            # 截斷頻道名稱
            truncated_channel = self._truncate_channel_name(channel_name)

            # 建立郵件
            msg = MIMEMultipart('alternative')
            msg['From'] = self.sender_email
            msg['To'] = self.recipient_email
            msg['Subject'] = Header(f'📺 [{truncated_channel}] {title}', 'utf-8')

            # 純文字版本（備用）
            text_part = MIMEText(summary_content, 'plain', 'utf-8')
            msg.attach(text_part)
            
            # HTML 版本
            html_content = self._build_html_email(parsed, title, channel_name)
            html_part = MIMEText(html_content, 'html', 'utf-8')
            msg.attach(html_part)

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
