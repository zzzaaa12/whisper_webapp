"""
統一的AI摘要服務模組
整合所有AI摘要相關功能，避免代碼重複
"""

from typing import Optional, Dict, Any, Callable
from pathlib import Path
from datetime import datetime # Added for datetime usage
from src.config import get_config
from src.utils.logger_manager import get_logger_manager

class SummaryService:
    """統一的摘要服務類別 - 支援多 AI 提供商"""

    def __init__(self, openai_api_key: Optional[str] = None, ai_provider: Optional[str] = None):
        """
        初始化摘要服務

        Args:
            openai_api_key: OpenAI API 金鑰（向後兼容）
            ai_provider: AI 提供商名稱 (openai, claude, ollama, groq 等)
        """
        self.openai = None
        self.logger_manager = get_logger_manager()

        # 決定使用的 AI 提供商
        self.ai_provider = ai_provider or get_config("AI_PROVIDER", "openai")

        # 向後兼容：如果直接傳入 openai_api_key，則使用 openai 提供商
        if openai_api_key:
            self.ai_provider = "openai"
            self._legacy_api_key = openai_api_key
        else:
            self._legacy_api_key = None

        # 當前提供商配置
        self.current_provider_config = None
        self._fallback_tried = []  # 記錄已嘗試的提供商

        self._init_ai_client()

    def _get_provider_config(self, provider_name: str) -> Optional[Dict[str, Any]]:
        """獲取指定 AI 提供商的配置"""
        try:
            # 嘗試從新版配置中獲取
            providers_config = get_config("AI_PROVIDERS", {})
            if isinstance(providers_config, dict) and provider_name in providers_config:
                config = providers_config[provider_name].copy()

                # 處理特殊情況：如果使用 legacy API key
                if provider_name == "openai" and self._legacy_api_key:
                    config["api_key"] = self._legacy_api_key

                # 檢查 API key 是否包含 "金鑰" - 如果包含則表示未設置有效金鑰
                api_key = config.get("api_key", "")
                if "金鑰" in str(api_key):
                    self.logger_manager.debug(f"Provider {provider_name} API key contains placeholder, skipping", "ai_summary")
                    return None
                elif api_key == "":
                    self.logger_manager.debug(f"Provider {provider_name} API key is empty, skipping", "ai_summary")
                    return None

                return config

            # 向後兼容：從舊版配置構建 openai 配置
            if provider_name == "openai":
                api_key = self._legacy_api_key or get_config("OPENAI_API_KEY")
                if api_key:
                    # 檢查舊版 API key 是否包含 "金鑰"
                    if "金鑰" in str(api_key):
                        self.logger_manager.debug("Legacy OpenAI API key contains placeholder, skipping", "ai_summary")
                        return None

                    return {
                        "api_key": api_key,
                        "base_url": "https://api.openai.com/v1",
                        "model": get_config("OPENAI_MODEL", "gpt-4o-mini"),
                        "max_tokens": int(get_config("OPENAI_MAX_TOKENS", "10000") or "10000"),
                        "temperature": float(get_config("OPENAI_TEMPERATURE", "0.7") or "0.7")
                    }

            return None

        except Exception as e:
            self.logger_manager.error(f"Error getting provider config for {provider_name}: {e}", "ai_summary")
            return None

    def _init_ai_client(self):
        """初始化 AI 客戶端"""
        self.current_provider_config = self._get_provider_config(self.ai_provider or "openai")

        if not self.current_provider_config:
            self.logger_manager.warning(f"No valid config found for AI provider '{self.ai_provider}'", "ai_summary")

            # 嘗試容錯切換到其他可用的提供商
            if self._try_fallback_provider():
                self.logger_manager.info(f"Successfully switched to fallback provider: {self.ai_provider}", "ai_summary")
            else:
                self.logger_manager.warning("No valid AI providers available", "ai_summary")
                return

        # 再次檢查配置是否有效（可能已經通過容錯切換更新）
        if not self.current_provider_config or not self.current_provider_config.get("api_key"):
            self.logger_manager.warning(f"No valid API key found for AI provider '{self.ai_provider}'", "ai_summary")
            return

        if not self.openai:
            try:
                import openai
                self.openai = openai
            except ImportError:
                self.logger_manager.warning("OpenAI library not installed", "ai_summary")

    def _get_model_config(self) -> Dict[str, Any]:
        """獲取當前提供商的模型配置"""
        if not self.current_provider_config:
            # 向後兼容的預設配置
            return {
                'model': get_config("OPENAI_MODEL", "gpt-4o-mini"),
                'max_tokens': int(get_config("OPENAI_MAX_TOKENS", "10000") or "10000"),
                'temperature': float(get_config("OPENAI_TEMPERATURE", "0.7") or "0.7")
            }

        return {
            'model': self.current_provider_config.get('model', 'gpt-4o-mini'),
            'max_tokens': self.current_provider_config.get('max_tokens', 10000),
            'temperature': self.current_provider_config.get('temperature', 0.7)
        }

    def _try_fallback_provider(self, log_callback: Optional[Callable] = None) -> bool:
        """嘗試容錯切換到下一個可用的提供商"""
        fallback_enabled = get_config("AI_FALLBACK_ENABLED", True)
        if not fallback_enabled:
            return False

        fallback_order = get_config("AI_FALLBACK_ORDER", ["openai", "claude", "groq", "ollama"])
        if not isinstance(fallback_order, list):
            return False

        # 記錄當前失敗的提供商
        if self.ai_provider not in self._fallback_tried:
            self._fallback_tried.append(self.ai_provider)

        # 找到下一個可用的提供商
        for provider in fallback_order:
            if provider not in self._fallback_tried:
                provider_config = self._get_provider_config(provider)
                if provider_config and provider_config.get("api_key"):
                    if log_callback:
                        log_callback(f"🔄 切換到 AI 提供商: {provider}", 'info')

                    self.ai_provider = provider
                    self.current_provider_config = provider_config
                    return True

        return False

    def _call_ai_api(self, prompt: str, model_config: Dict[str, Any], log_callback: Optional[Callable]) -> Any:
        if not self.openai:
            self._init_ai_client()

        if not self.openai:
            raise RuntimeError("OpenAI module failed to load.")

        # 動態創建客戶端（支援不同的 base_url）
        client_kwargs = {"api_key": self.current_provider_config["api_key"]}

        # 如果有自定義的 base_url，則設定
        if "base_url" in self.current_provider_config:
            base_url = self.current_provider_config["base_url"]
            if base_url != "https://api.openai.com/v1":  # 非預設的才設定
                client_kwargs["base_url"] = base_url

        client = self.openai.OpenAI(**client_kwargs)

        if log_callback:
            log_callback(f"🤖 使用模型：{model_config['model']} (提供商: {self.ai_provider})", 'info')

        # 調用 AI API
        response = client.chat.completions.create(
            model=model_config['model'],
            messages=[
                {"role": "system", "content": "你是專業的影片內容摘要專家，擅長從字幕中提取重點並整理成結構化摘要。請使用正體中文（台灣用語）回答，保持簡潔精準。字幕是透過語音轉文字的方式產出，如果文字或詞語有明顯錯誤，可先修正再回答。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=model_config['max_tokens'],
            temperature=model_config['temperature']
        )
        return response

    def _create_prompt(self, subtitle_content: str, prompt_type: str = "structured") -> str:
        """
        創建摘要prompt

        Args:
            subtitle_content: 字幕內容
            prompt_type: prompt類型 ('simple', 'structured', 'detailed')
        """
        if prompt_type == "simple":
            # 簡單模式 - 保持原有格式
            prompt = f"請整理一下這個youtube對話紀錄，條列出每一個項目與內容\n\n{subtitle_content}"
        elif prompt_type == "detailed":
            # 詳細模式 - 更豐富的 Markdown 格式
            prompt = f"""請將以下影片內容整理成詳細的結構化摘要，使用 Markdown 格式：

## 🎯 影片內容摘要

請分析以下內容並按照下列結構整理：

### 📋 主要議題
- 列出影片討論的核心主題

### 💡 重點內容
- 重要觀點和見解
- 關鍵數據或事實
- 值得注意的論述

### 🔍 詳細分析
根據內容深度分段說明各個重點

### 📌 結論與要點
- 總結重要結論
- 可行動的建議或啟發

---

**影片原始內容：**
{subtitle_content}"""

        else:
            # 結構化模式（預設）- 針對 GPT-4.1-mini 優化，支援自動判斷影片類型
            prompt = f"""你是專業的影片內容摘要專家。請將以下字幕內容整理成結構化摘要。

【第一步：判斷影片類型】
請先分析字幕內容，判斷這是哪種類型的影片：
- 教學類（有步驟、操作說明、安裝設定等）
- 訪談類（對話、觀點交流、人物故事）
- 新聞類（事件報導、時事分析）
- 評論類（產品評測、觀點評論）
- 其他（娛樂、Vlog 等）

【第二步：根據類型選擇格式】

▼ 如果是【教學類】影片，使用此格式：

## 🎯 核心主題
- 這部教學要教什麼（1-2 句話）

## 📋 前置知識
- 需要先了解的概念或工具（若無則寫「無特殊要求」）

## 📝 步驟教學
1. **步驟標題**
   - 具體操作說明
   - 注意事項
2. **步驟標題**
   - 具體操作說明
（依內容列出完整步驟）

## ⚠️ 常見錯誤與注意事項
- 初學者容易踩的坑或重要提醒

## 🎯 總結
用 50-100 字總結學習重點

▼ 如果是【其他類型】影片，使用此格式：

## 🎯 核心主題
- 用 1-3 個要點說明影片主旨

## 📝 重點整理
1. **重點標題**
   - 具體說明
2. **重點標題**
   - 具體說明
（依內容長度列出 3-8 個重點）

## 💬 關鍵金句
> 引用 3-10 句影片中的重要話語或觀點

## 🎯 總結
用 50-100 字總結影片核心價值

【輸出規則】
1. 使用正體中文（台灣用語）
2. 不要輸出「影片類型判斷」，直接輸出摘要內容
3. 嚴格按照對應格式的區塊標題輸出
4. 每個區塊都必須有內容，不可省略

【字幕內容】
{subtitle_content}"""

        return prompt

        # ===== 舊版 prompt v2（備份）=====
        # prompt = f"""你是專業的影片內容摘要專家。請將以下字幕內容整理成結構化摘要。
        #
        # 【輸出規則】
        # 1. 使用正體中文（台灣用語）
        # 2. 嚴格按照以下四個區塊輸出，不要增加或修改標題
        # 3. 每個區塊都必須有內容，不可省略
        #
        # 【輸出格式】
        #
        # ## 🎯 核心主題
        # - 用 1-3 個要點說明影片主旨（每點不超過 30 字）
        #
        # ## 📝 重點整理
        # 1. **重點標題**
        #    - 具體說明（每個重點 2-4 個子項目）
        # 2. **重點標題**
        #    - 具體說明
        # （依內容長度列出 3-8 個重點）
        #
        # ## 💬 關鍵金句
        # > 引用 3-10 句影片中的重要話語或觀點
        #
        # ## 🎯 總結
        # 用 50-100 字總結影片核心價值
        #
        # 【字幕內容】
        # {subtitle_content}"""

    def _add_header(self, summary: str, header_info: Dict[str, Any]) -> str:
        """
        為摘要添加檔案資訊header

        Args:
            summary: 原始摘要內容
            header_info: header資訊字典
        """
        header_lines = []

        # AI 提供商資訊
        if self.ai_provider and self.current_provider_config:
            model_name = self.current_provider_config.get('model', 'unknown')
            provider_display = {
                'openai': 'OpenAI',
                'claude': 'Anthropic Claude',
                'gemini': 'Google Gemini',
                'deepseek': 'DeepSeek',
                'ollama': 'Ollama (本地)',
                'grok': 'xAI Grok'
            }.get(self.ai_provider, self.ai_provider.upper())

            header_lines.append(f"🤖 AI 摘要：{provider_display} ({model_name})")

        # 檔案資訊
        if 'filename' in header_info:
            header_lines.append(f"📁 檔案：{header_info['filename']}")

        # 影片資訊
        if 'title' in header_info and header_info['title']:
            header_lines.append(f"🎬 標題：{header_info['title']}")
        if 'uploader' in header_info and header_info['uploader']:
            header_lines.append(f"📺 頻道：{header_info['uploader']}")
        if 'duration_string' in header_info and header_info['duration_string']:
            header_lines.append(f"⏱️ 影片長度：{header_info['duration_string']}")
        if 'url' in header_info and header_info['url']:
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
        if not self.current_provider_config:
            error_msg = "❌ 當前AI提供商配置未初始化，無法生成摘要"
            if log_callback:
                log_callback(error_msg, 'error')
            return False, error_msg

        if not subtitle_content or not subtitle_content.strip():
            error_msg = "❌ 字幕內容為空，無法生成摘要"
            if log_callback:
                log_callback(error_msg, 'error')
            return False, error_msg

        # 最多嘗試 3 次（包含容錯切換）
        max_attempts = 3
        attempt = 0

        while attempt < max_attempts:
            try:
                attempt += 1

                if log_callback:
                    provider_name = (self.ai_provider or "openai").upper()
                    log_callback(f"▶️ 開始生成 AI 摘要 ({provider_name})...", 'info')

                if progress_callback:
                    progress_callback(90)

                # 創建prompt
                prompt = self._create_prompt(subtitle_content, prompt_type)

                # 獲取模型配置
                model_config = self._get_model_config()

                response = self._call_ai_api(prompt, model_config, log_callback)

                # 提取摘要內容
                summary_content = response.choices[0].message.content
                summary = summary_content.strip() if summary_content else ""

                if not summary:
                    error_msg = "⚠️ AI 未回傳有效摘要內容"
                    if log_callback:
                        log_callback(error_msg, 'warning')
                    return False, error_msg

                # 添加header（如果提供）或至少添加 AI 提供商信息
                if header_info:
                    summary = self._add_header(summary, header_info)
                else:
                    # 沒有完整 header 時，至少添加 AI 提供商信息
                    if self.ai_provider and self.current_provider_config:
                        from datetime import datetime

                        model_name = self.current_provider_config.get('model', 'unknown')
                        provider_display = {
                            'openai': 'OpenAI',
                            'claude': 'Anthropic Claude',
                            'gemini': 'Google Gemini',
                            'deepseek': 'DeepSeek',
                            'ollama': 'Ollama (本地)',
                            'grok': 'xAI Grok'
                        }.get(self.ai_provider, self.ai_provider.upper())

                        ai_header = (
                            f"🤖 AI 摘要：{provider_display} ({model_name})\n"
                            f"⏰ 處理時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                            f"{'='*50}\n\n"
                        )
                        summary = ai_header + summary

                if progress_callback:
                    progress_callback(100)

                if log_callback:
                    log_callback(f"✅ AI 摘要生成完成 (提供商: {self.ai_provider})", 'success')

                return True, summary

            except Exception as e:
                error_msg = f"❌ AI 摘要生成失敗 (提供商: {self.ai_provider}): {str(e)}"
                if log_callback:
                    log_callback(error_msg, 'error')

                # 如果還有嘗試機會，嘗試容錯切換
                if attempt < max_attempts:
                    if self._try_fallback_provider(log_callback):
                        if log_callback:
                            log_callback(f"🔄 嘗試重試，當前提供商: {self.ai_provider}", 'info')
                        continue
                    else:
                        if log_callback:
                            log_callback("❌ 沒有可用的備用 AI 提供商", 'error')
                        break
                else:
                    if log_callback:
                        log_callback(f"🔍 錯誤詳情: {traceback.format_exc()}", 'error')
                    break

        return False, f"❌ AI 摘要生成失敗，已嘗試 {attempt} 次"

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

def get_summary_service(openai_api_key: Optional[str] = None, ai_provider: Optional[str] = None) -> SummaryService:
    """
    獲取全域摘要服務實例（單例模式）

    Args:
        openai_api_key: OpenAI API 金鑰
        ai_provider: AI 提供商名稱

    Returns:
        SummaryService: 摘要服務實例
    """
    global _summary_service_instance

    if _summary_service_instance is None:
        _summary_service_instance = SummaryService(openai_api_key, ai_provider)
    elif openai_api_key:
        # 更新API金鑰
        _summary_service_instance.current_provider_config = _summary_service_instance._get_provider_config(ai_provider or _summary_service_instance.ai_provider)
        _summary_service_instance._init_ai_client()

    return _summary_service_instance

def reset_summary_service():
    """重置全域摘要服務實例"""
    global _summary_service_instance
    _summary_service_instance = None