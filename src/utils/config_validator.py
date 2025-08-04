"""
配置驗證工具
檢查系統配置的完整性和有效性
"""

from typing import List, Tuple, Dict, Any
from pathlib import Path

from src.config import get_config
from src.utils.logger_manager import get_logger_manager


class ConfigValidator:
    """配置驗證器"""

    def __init__(self):
        self.logger = get_logger_manager()
        self.warnings: List[str] = []
        self.errors: List[str] = []

    def validate_all(self) -> Tuple[bool, List[str], List[str]]:
        """
        驗證所有配置

        Returns:
            tuple: (是否通過驗證, 警告列表, 錯誤列表)
        """
        self.warnings.clear()
        self.errors.clear()

        # 驗證基本配置
        self._validate_basic_config()

        # 驗證路徑配置
        self._validate_paths()

        # 驗證 AI 配置
        self._validate_ai_config()

        # 驗證伺服器配置
        self._validate_server_config()

        # 驗證通知配置
        self._validate_notification_config()

        # 驗證 SSL 配置
        self._validate_ssl_config()

        is_valid = len(self.errors) == 0
        return is_valid, self.warnings.copy(), self.errors.copy()

    def _validate_basic_config(self):
        """驗證基本配置"""
        # 檢查 SECRET_KEY
        secret_key = get_config("SECRET_KEY")
        if not secret_key:
            self.warnings.append("未設定 SECRET_KEY，將使用隨機金鑰（重啟後會改變）")
        elif len(str(secret_key)) < 16:
            self.warnings.append("SECRET_KEY 長度過短，建議至少 16 個字元")

        # 檢查 ACCESS_CODE
        access_code = get_config("ACCESS_CODE")
        if not access_code:
            self.warnings.append("未設定 ACCESS_CODE，系統將允許無通行碼存取")
        elif len(str(access_code)) < 6:
            self.warnings.append("ACCESS_CODE 長度過短，建議至少 6 個字元")

    def _validate_paths(self):
        """驗證路徑配置"""
        required_paths = [
            'PATHS.DOWNLOADS_DIR',
            'PATHS.SUMMARIES_DIR',
            'PATHS.SUBTITLES_DIR',
            'PATHS.UPLOADS_DIR',
            'PATHS.LOGS_DIR',
            'PATHS.TRASH_DIR',
            'PATHS.TASKS_DIR'
        ]

        for path_key in required_paths:
            path_value = get_config(path_key)
            if not path_value:
                self.errors.append(f"缺少必要路徑配置: {path_key}")
                continue

            try:
                path_obj = Path(path_value)
                # 嘗試創建目錄（如果不存在）
                path_obj.mkdir(parents=True, exist_ok=True)

                # 檢查是否可寫
                if not path_obj.exists() or not path_obj.is_dir():
                    self.errors.append(f"路徑無效或無法創建: {path_key} = {path_value}")

            except Exception as e:
                self.errors.append(f"路徑配置錯誤 {path_key}: {str(e)}")

    def _validate_ai_config(self):
        """驗證 AI 配置"""
        # 檢查舊版 OpenAI 配置
        openai_key = get_config("OPENAI_API_KEY")
        if openai_key and "金鑰" in str(openai_key):
            self.warnings.append("OPENAI_API_KEY 包含佔位符文字，請設定真實的 API 金鑰")
            openai_key = None

        # 檢查新版 AI 提供商配置
        ai_providers = get_config("AI_PROVIDERS", {})
        valid_providers = []

        if isinstance(ai_providers, dict):
            for provider_name, config in ai_providers.items():
                if not isinstance(config, dict):
                    continue

                api_key = config.get("api_key", "")
                if api_key and "金鑰" not in str(api_key) and api_key.strip():
                    valid_providers.append(provider_name)

        # 如果沒有有效的 AI 配置
        if not openai_key and not valid_providers:
            self.warnings.append("未設定有效的 AI API 金鑰，AI 摘要功能將無法使用")
        elif valid_providers:
            self.logger.info(f"✅ 找到有效的 AI 提供商: {', '.join(valid_providers)}", "config_validator")

    def _validate_server_config(self):
        """驗證伺服器配置"""
        # 檢查伺服器埠號
        server_port = get_config("SERVER_PORT", 5000)
        try:
            port_num = int(server_port)
            if port_num < 1 or port_num > 65535:
                self.errors.append(f"伺服器埠號無效: {server_port}")
            elif port_num < 1024:
                self.warnings.append(f"使用系統埠號 {port_num}，可能需要管理員權限")
        except (ValueError, TypeError):
            self.errors.append(f"伺服器埠號格式錯誤: {server_port}")

        # 檢查網站基礎 URL
        base_url = get_config("WEBSITE_BASE_URL", "localhost")
        if not base_url:
            self.warnings.append("未設定 WEBSITE_BASE_URL，將使用 localhost")

    def _validate_notification_config(self):
        """驗證通知配置"""
        telegram_token = get_config("TELEGRAM_BOT_TOKEN")
        telegram_chat_id = get_config("TELEGRAM_CHAT_ID")

        if telegram_token and not telegram_chat_id:
            self.warnings.append("設定了 TELEGRAM_BOT_TOKEN 但缺少 TELEGRAM_CHAT_ID")
        elif telegram_chat_id and not telegram_token:
            self.warnings.append("設定了 TELEGRAM_CHAT_ID 但缺少 TELEGRAM_BOT_TOKEN")
        elif telegram_token and telegram_chat_id:
            self.logger.info("✅ Telegram 通知配置完整", "config_validator")

    def _validate_ssl_config(self):
        """驗證 SSL 配置"""
        use_ssl = get_config("USE_SSL", False)
        if use_ssl:
            certs_dir = get_config('PATHS.CERTS_DIR')
            if not certs_dir:
                self.errors.append("啟用 SSL 但未設定 CERTS_DIR")
                return

            cert_file = Path(certs_dir) / 'cert.pem'
            key_file = Path(certs_dir) / 'key.pem'

            if not cert_file.exists():
                self.errors.append(f"SSL 憑證檔案不存在: {cert_file}")
            if not key_file.exists():
                self.errors.append(f"SSL 私鑰檔案不存在: {key_file}")

            if cert_file.exists() and key_file.exists():
                self.logger.info("✅ SSL 憑證檔案存在", "config_validator")


def validate_config() -> Tuple[bool, List[str], List[str]]:
    """
    便捷函數：驗證配置

    Returns:
        tuple: (是否通過驗證, 警告列表, 錯誤列表)
    """
    validator = ConfigValidator()
    return validator.validate_all()


def log_config_status():
    """記錄配置狀態到日誌"""
    try:
        logger = get_logger_manager()

        logger.info("🔍 檢查系統配置...", "config_validator")

        is_valid, warnings, errors = validate_config()

        # 記錄錯誤
        for error in errors:
            logger.error(f"❌ {error}", "config_validator")

        # 記錄警告
        for warning in warnings:
            logger.warning(f"⚠️ {warning}", "config_validator")

        # 總結
        if errors:
            logger.error(f"配置驗證失敗，發現 {len(errors)} 個錯誤", "config_validator")
        elif warnings:
            logger.warning(f"配置驗證通過，但有 {len(warnings)} 個警告", "config_validator")
        else:
            logger.info("✅ 配置驗證通過，無警告或錯誤", "config_validator")

        return is_valid, warnings, errors

    except Exception as e:
        # 如果配置驗證本身失敗，返回安全的預設值
        try:
            logger = get_logger_manager()
            logger.error(f"配置驗證過程中發生錯誤: {e}", "config_validator")
        except:
            print(f"配置驗證過程中發生錯誤: {e}")

        return False, [], [f"配置驗證失敗: {str(e)}"]