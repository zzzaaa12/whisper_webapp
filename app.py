#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Whisper WebApp 主程式
語音轉文字和 AI 摘要系統
"""

from pathlib import Path
from dotenv import load_dotenv

from src.app_factory import create_app, setup_directories
from src.socketio_handlers import register_socketio_handlers
from src.config import get_config
from src.utils.logger_manager import get_logger_manager
from src.utils.config_validator import validate_config

# 載入環境變數
load_dotenv()

# 專案根目錄
BASE_DIR = Path(__file__).parent.resolve()


def check_system_config():
    """檢查系統配置並顯示警告"""
    logger_manager = get_logger_manager()

    logger_manager.info("🔍 檢查系統配置...", "app")

    try:
        is_valid, warnings, errors = validate_config()

        # 記錄錯誤
        for error in errors:
            logger_manager.error(f"❌ {error}", "app")

        # 記錄警告
        for warning in warnings:
            logger_manager.warning(f"⚠️ {warning}", "app")

        # 總結
        if errors:
            logger_manager.error(f"配置驗證失敗，發現 {len(errors)} 個錯誤", "app")
            # 檢查是否有嚴重錯誤
            critical_errors = [e for e in errors if "路徑" in e or "埠號" in e]
            if critical_errors:
                logger_manager.error("發現嚴重配置錯誤，請修正後重新啟動", "app")
                return False
        elif warnings:
            logger_manager.warning(f"配置驗證通過，但有 {len(warnings)} 個警告", "app")
        else:
            logger_manager.info("✅ 配置驗證通過，無警告或錯誤", "app")

        return True

    except Exception as e:
        logger_manager.error(f"配置驗證過程中發生錯誤: {e}", "app")
        return False


def setup_ssl():
    """設置 SSL 配置"""
    logger_manager = get_logger_manager()

    use_ssl = get_config("USE_SSL", False)
    ssl_context = None

    if use_ssl:
        cert_file = get_config('PATHS.CERTS_DIR') / 'cert.pem'
        key_file = get_config('PATHS.CERTS_DIR') / 'key.pem'

        if cert_file.exists() and key_file.exists():
            try:
                import ssl
                ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                ssl_context.load_cert_chain(cert_file, key_file)
                logger_manager.info("✅ SSL 憑證已載入，將使用 HTTPS 模式", "app")
            except Exception as e:
                logger_manager.warning(f"SSL 憑證載入失敗: {e}", "app")
                logger_manager.warning("將使用 HTTP 模式啟動", "app")
                ssl_context = None
        else:
            logger_manager.warning("找不到 SSL 憑證檔案 (certs/cert.pem, certs/key.pem)", "app")
            logger_manager.warning("將使用 HTTP 模式啟動", "app")
    else:
        logger_manager.info("📡 使用 HTTP 模式", "app")

    return ssl_context


def start_queue_worker():
    """啟動任務佇列工作程式"""
    logger_manager = get_logger_manager()

    try:
        from src.services.queue_worker import start_queue_worker
        queue_worker = start_queue_worker(
            data_dir=BASE_DIR,
            openai_key=get_config("OPENAI_API_KEY")
        )
        logger_manager.info("✅ 新任務佇列工作程式已啟動", "app")
        return queue_worker
    except Exception as e:
        logger_manager.warning(f"新任務佇列工作程式啟動失敗: {e}", "app")
        return None


def stop_queue_worker():
    """停止任務佇列工作程式"""
    logger_manager = get_logger_manager()

    try:
        from src.services.queue_worker import stop_queue_worker
        stop_queue_worker()
        logger_manager.info("✅ 新任務佇列工作程式已停止", "app")
    except Exception as e:
        logger_manager.warning(f"停止新任務佇列工作程式失敗: {e}", "app")


def main():
    """主函數"""
    logger_manager = get_logger_manager()

    # 創建應用程式（這會初始化 ConfigManager）
    app, socketio, services = create_app(BASE_DIR)

    # 檢查系統配置
    if not check_system_config():
        logger_manager.error("系統配置檢查失敗，程式退出", "app")
        return 1

    # 註冊 SocketIO 處理器
    register_socketio_handlers(socketio, services)

    # 設置目錄
    setup_directories(services)

    # 設置 SSL
    ssl_context = setup_ssl()

    # 啟動佇列工作程式
    queue_worker = start_queue_worker()

    # 獲取伺服器配置
    server_port = int(get_config("SERVER_PORT", 5000))

    # 顯示啟動訊息
    logger_manager.info("🚀 繼續啟動系統...", "app")

    if ssl_context:
        logger_manager.info(f"🔐 HTTPS 伺服器啟動，請在瀏覽器中開啟 https://127.0.0.1:{server_port}", "app")
        logger_manager.info(f"或透過網路存取：https://你的IP地址:{server_port}", "app")
    else:
        logger_manager.info(f"📡 HTTP 伺服器啟動，請在瀏覽器中開啟 http://127.0.0.1:{server_port}", "app")
        logger_manager.info(f"或透過網路存取：http://你的IP地址:{server_port}", "app")

    try:
        socketio.run(
            app,
            host='0.0.0.0',
            port=server_port,
            use_reloader=False,
            ssl_context=ssl_context
        )
    finally:
        logger_manager.info("主伺服器準備關閉...", "app")
        stop_queue_worker()
        logger_manager.info("程式已完全關閉。", "app")


if __name__ == '__main__':
    main()
