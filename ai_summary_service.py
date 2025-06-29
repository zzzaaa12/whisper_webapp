"""
統一的AI摘要服務模組
整合所有AI摘要相關功能，避免代碼重複
"""

import os
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Callable
import traceback

class SummaryService:
    """統一的摘要服務類別"""

    def __init__(self, openai_api_key: Optional[str] = None, config_getter: Optional[Callable] = None):
        """
        初始化摘要服務

        Args:
            openai_api_key: OpenAI API 金鑰
            config_getter: 配置獲取函數，用於獲取各種配置值
        """
        self.openai_api_key = openai_api_key
        self.config_getter = config_getter or (lambda key, default=None: os.getenv(key, default))
        self.openai = None
        self._init_openai()

    def _init_openai(self):
        """初始化OpenAI客戶端"""
        if not self.openai_api_key:
            self.openai_api_key = self.config_getter("OPENAI_API_KEY")

        if self.openai_api_key and not self.openai:
            try:
                import openai
                self.openai = openai
            except ImportError:
                print("[SUMMARY] Warning: OpenAI library not installed")

    def _get_model_config(self) -> Dict[str, Any]:
        """獲取模型配置"""
        max_tokens_str = self.config_getter("OPENAI_MAX_TOKENS", "20000")
        temperature_str = self.config_getter("OPENAI_TEMPERATURE", "0.7")

        return {
            'model': self.config_getter("OPENAI_MODEL", "gpt-4.1-mini"),
            'max_tokens': int(max_tokens_str) if max_tokens_str is not None else 20000,
            'temperature': float(temperature_str) if temperature_str is not None else 0.7
        }

    def _create_prompt(self, subtitle_content: str, prompt_type: str = "structured") -> str:
        """
        創建摘要prompt

        Args:
            subtitle_content: 字幕內容
            prompt_type: prompt類型 ('simple', 'structured', 'detailed')
        """
        # 統一使用新的prompt格式
        prompt = f"請整理一下這個youtube對話紀錄，條列出每一個項目與內容，放在最前面的段落：【影片內容摘要】\n\n{subtitle_content}"

        return prompt

    def _add_header(self, summary: str, header_info: Dict[str, Any]) -> str:
        """
        為摘要添加檔案資訊header

        Args:
            summary: 原始摘要內容
            header_info: header資訊字典
        """
        header_lines = []

        # 檔案資訊
        if 'filename' in header_info:
            header_lines.append(f"📁 檔案：{header_info['filename']}")

        # 影片資訊
        if 'title' in header_info:
            header_lines.append(f"🎬 標題：{header_info['title']}")
        if 'uploader' in header_info:
            header_lines.append(f"📺 頻道：{header_info['uploader']}")
        if 'url' in header_info:
            header_lines.append(f"🔗 網址：{header_info['url']}")

        # 處理時間
        header_lines.append(f"⏰ 處理時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # 生成完整header
        if header_lines:
            header = "\n".join(header_lines) + f"\n{'='*50}\n\n"
            return header + summary

        return summary

    def generate_summary(self,
                        subtitle_content: str,
                        prompt_type: str = "structured",
                        header_info: Optional[Dict[str, Any]] = None,
                        progress_callback: Optional[Callable] = None,
                        log_callback: Optional[Callable] = None) -> tuple[bool, str]:
        """
        生成摘要

        Args:
            subtitle_content: 字幕內容
            prompt_type: prompt類型
            header_info: header資訊（可選）
            progress_callback: 進度回調函數（可選）
            log_callback: 日誌回調函數（可選）

        Returns:
            tuple: (成功標誌, 摘要內容或錯誤信息)
        """
        if not self.openai_api_key:
            error_msg = "❌ OpenAI API key 未設定，無法生成摘要"
            if log_callback:
                log_callback(error_msg, 'error')
            return False, error_msg

        if not subtitle_content or not subtitle_content.strip():
            error_msg = "❌ 字幕內容為空，無法生成摘要"
            if log_callback:
                log_callback(error_msg, 'error')
            return False, error_msg

        try:
            if log_callback:
                log_callback("▶️ 開始生成 AI 摘要...", 'info')

            if progress_callback:
                progress_callback(90)

            # 初始化OpenAI客戶端
            if not self.openai:
                self._init_openai()

            if not self.openai:
                error_msg = "❌ OpenAI 模組載入失敗"
                if log_callback:
                    log_callback(error_msg, 'error')
                return False, error_msg

            client = self.openai.OpenAI(api_key=self.openai_api_key)

            # 創建prompt
            prompt = self._create_prompt(subtitle_content, prompt_type)

            # 獲取模型配置
            model_config = self._get_model_config()

            if log_callback:
                log_callback(f"🤖 使用模型：{model_config['model']}", 'info')

            # 調用OpenAI API
            response = client.chat.completions.create(
                model=model_config['model'],
                messages=[
                    {"role": "system", "content": "You are a helpful assistant. 用台灣用語與正體中文回答"},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=model_config['max_tokens'],
                temperature=model_config['temperature']
            )

            # 提取摘要內容
            summary_content = response.choices[0].message.content
            summary = summary_content.strip() if summary_content else ""

            if not summary:
                error_msg = "⚠️ AI 未回傳有效摘要內容"
                if log_callback:
                    log_callback(error_msg, 'warning')
                return False, error_msg

            # 添加header（如果提供）
            if header_info:
                summary = self._add_header(summary, header_info)

            if progress_callback:
                progress_callback(100)

            if log_callback:
                log_callback("✅ AI 摘要生成完成", 'success')

            return True, summary

        except Exception as e:
            error_msg = f"❌ AI 摘要生成失敗: {str(e)}"
            if log_callback:
                log_callback(error_msg, 'error')
                log_callback(f"🔍 錯誤詳情: {traceback.format_exc()}", 'error')
            return False, error_msg

    def save_summary(self,
                    summary: str,
                    save_path: Path,
                    log_callback: Optional[Callable] = None) -> bool:
        """
        儲存摘要到檔案

        Args:
            summary: 摘要內容
            save_path: 儲存路徑
            log_callback: 日誌回調函數（可選）

        Returns:
            bool: 儲存成功標誌
        """
        try:
            # 確保目錄存在
            save_path.parent.mkdir(parents=True, exist_ok=True)

            # 寫入檔案
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(summary)

            if log_callback:
                log_callback(f"📄 摘要已儲存至: {save_path}", 'info')

            return True

        except Exception as e:
            error_msg = f"❌ 摘要儲存失敗: {str(e)}"
            if log_callback:
                log_callback(error_msg, 'error')
            return False

    def generate_and_save_summary(self,
                                 subtitle_content: str,
                                 save_path: Path,
                                 prompt_type: str = "structured",
                                 header_info: Optional[Dict[str, Any]] = None,
                                 progress_callback: Optional[Callable] = None,
                                 log_callback: Optional[Callable] = None,
                                 telegram_callback: Optional[Callable] = None) -> tuple[bool, str]:
        """
        生成並儲存摘要（一站式服務）

        Args:
            subtitle_content: 字幕內容
            save_path: 儲存路徑
            prompt_type: prompt類型
            header_info: header資訊
            progress_callback: 進度回調
            log_callback: 日誌回調
            telegram_callback: Telegram通知回調

        Returns:
            tuple: (成功標誌, 摘要內容或錯誤信息)
        """
        # 生成摘要
        success, result = self.generate_summary(
            subtitle_content=subtitle_content,
            prompt_type=prompt_type,
            header_info=header_info,
            progress_callback=progress_callback,
            log_callback=log_callback
        )

        if not success:
            return False, result

        summary = result

        # 儲存摘要
        if not self.save_summary(summary, save_path, log_callback):
            return False, "摘要生成成功但儲存失敗"

        # 發送日誌
        if log_callback:
            log_callback(f"---摘要內容---\n{summary}", 'info')

        # 發送Telegram通知（如果提供）
        if telegram_callback and header_info:
            try:
                # 提取原始摘要（去除header）
                lines = summary.split('\n')
                summary_start = 0
                for i, line in enumerate(lines):
                    if '=' in line and len(line) > 20:  # 找到分隔線
                        summary_start = i + 2
                        break

                clean_summary = '\n'.join(lines[summary_start:]) if summary_start > 0 else summary

                # 構建Telegram消息
                if 'title' in header_info:
                    # 影片類型
                    tg_message = (
                        f"✅ *摘要完成:*\n\n"
                        f"🎬 *標題:* `{header_info.get('title', 'N/A')}`\n"
                        f"📺 *頻道:* `{header_info.get('uploader', 'N/A')}`\n\n"
                        f"📝 *完整摘要:*\n`{clean_summary[:1000]}{'...' if len(clean_summary) > 1000 else ''}`"
                    )
                else:
                    # 檔案類型
                    tg_message = (
                        f"✅ *摘要完成:*\n\n"
                        f"📁 *檔案:* `{header_info.get('filename', 'N/A')}`\n\n"
                        f"📝 *完整摘要:*\n`{clean_summary[:1000]}{'...' if len(clean_summary) > 1000 else ''}`"
                    )

                telegram_callback(tg_message)

            except Exception as e:
                if log_callback:
                    log_callback(f"⚠️ Telegram通知發送失敗: {e}", 'warning')

        return True, summary


# 全域摘要服務實例
_summary_service_instance = None

def get_summary_service(openai_api_key: Optional[str] = None, config_getter: Optional[Callable] = None) -> SummaryService:
    """
    獲取全域摘要服務實例（單例模式）

    Args:
        openai_api_key: OpenAI API 金鑰
        config_getter: 配置獲取函數

    Returns:
        SummaryService: 摘要服務實例
    """
    global _summary_service_instance

    if _summary_service_instance is None:
        _summary_service_instance = SummaryService(openai_api_key, config_getter)
    elif openai_api_key:
        # 更新API金鑰
        _summary_service_instance.openai_api_key = openai_api_key
        _summary_service_instance._init_openai()

    return _summary_service_instance

def reset_summary_service():
    """重置全域摘要服務實例"""
    global _summary_service_instance
    _summary_service_instance = None