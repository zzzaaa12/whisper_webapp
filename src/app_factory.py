"""
Flask 應用程式工廠
負責創建和配置 Flask 應用程式實例
"""

import os
from pathlib import Path
from flask import Flask, session, redirect, url_for, request

from src.config import init_config, get_config
from src.services.socketio_instance import init_socketio
from src.services.auth_service import AuthService
from src.services.file_service import FileService
from src.services.bookmark_service import BookmarkService
from src.services.trash_service import TrashService
from src.services.url_service import URLService
from src.services.log_service import LogService
from src.services.gpu_service import GPUService
from src.services.socket_service import SocketService
from src.utils.path_manager import get_path_manager
from src.utils.logger_manager import setup_logging, get_logger_manager
from src.middleware.error_handler import register_error_handlers, register_request_logging


def create_app(base_dir: Path = None):
    """
    創建 Flask 應用程式實例

    Args:
        base_dir: 專案根目錄路徑

    Returns:
        tuple: (app, socketio, services_dict)
    """
    if base_dir is None:
        base_dir = Path(__file__).parent.parent.resolve()

    # 初始化配置
    init_config(base_dir)

    # 初始化日誌系統
    setup_logging(base_dir / "logs", enable_console=True)
    logger_manager = get_logger_manager()

    # 創建 Flask 應用程式
    app = Flask(__name__)
    app.config['SECRET_KEY'] = get_config('SECRET_KEY', os.urandom(24))

    # 確保路徑管理器在配置初始化後才被使用
    path_manager = get_path_manager()

    # 註冊模板上下文處理器
    @app.context_processor
    def inject_session():
        """Make session available to all templates"""
        return dict(session=session)

    @app.context_processor
    def inject_config():
        """Make config available to all templates"""
        return dict(config=get_config)

    # 初始化 SocketIO
    socketio = init_socketio(app)

    # 初始化服務
    services = _init_services(base_dir, socketio)

    # 註冊安全中介軟體
    _register_security_middleware(app)

    # 註冊路由
    _register_blueprints(app)

    # 註冊管理路由
    _register_admin_routes(app, services['auth_service'])

    # 註冊錯誤處理器
    register_error_handlers(app)
    register_request_logging(app)

    logger_manager.info("Flask 應用程式初始化完成", "app_factory")

    return app, socketio, services


def _init_services(base_dir: Path, socketio):
    """
    初始化所有服務

    Args:
        base_dir: 專案根目錄
        socketio: SocketIO 實例

    Returns:
        dict: 服務實例字典
    """
    # 初始化服務
    auth_service = AuthService()
    file_service = FileService()
    log_service = LogService(get_config('PATHS.LOGS_DIR'))
    gpu_service = GPUService()
    socket_service = SocketService(socketio, log_service)
    bookmark_service = BookmarkService(
        base_dir / "bookmarks.json",
        get_config('PATHS.SUMMARIES_DIR')
    )
    trash_service = TrashService(
        get_config('PATHS.TRASH_DIR'),
        get_config('PATHS.SUMMARIES_DIR'),
        get_config('PATHS.SUBTITLES_DIR')
    )
    url_service = URLService()

    return {
        'auth_service': auth_service,
        'file_service': file_service,
        'log_service': log_service,
        'gpu_service': gpu_service,
        'socket_service': socket_service,
        'bookmark_service': bookmark_service,
        'trash_service': trash_service,
        'url_service': url_service
    }


def _register_security_middleware(app):
    """
    註冊安全中介軟體

    Args:
        app: Flask 應用程式實例
    """
    @app.after_request
    def set_security_headers(response):
        """設定安全標頭"""
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'

        # 如果使用 SSL，設定更強的 HSTS
        use_ssl = get_config("USE_SSL", False)
        if use_ssl:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
        else:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'

        return response

    @app.before_request
    def require_access_code():
        """在每個請求前檢查是否需要通行碼"""
        # API 請求應跳過此驗證
        if request.path.startswith('/api'):
            return

        # 檢查功能是否開啟
        if not get_config("ACCESS_CODE_ALL_PAGE", False):
            return

        # 檢查使用者是否已通過驗證
        if session.get('is_authorized'):
            return

        # 允許訪問特定頁面，避免無限重導向
        # 也允許訪問 Socket.IO 的內部路徑
        if request.endpoint in ['main.access', 'static'] or request.path.startswith('/socket.io'):
            return

        # 重導向到通行碼輸入頁面
        return redirect(url_for('main.access', next=request.path))


def _register_blueprints(app):
    """
    註冊藍圖路由

    Args:
        app: Flask 應用程式實例
    """
    from src.routes.main import main_bp
    from src.routes.api import api_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp)


def _register_admin_routes(app, auth_service):
    """
    註冊管理路由

    Args:
        app: Flask 應用程式實例
        auth_service: 認證服務實例
    """
    from flask import render_template, request

    @app.route('/admin/login-attempts')
    def admin_login_attempts():
        """管理端點：查看登入嘗試狀態"""
        admin_code = get_config("ADMIN_CODE")
        if not admin_code or request.args.get('code') != admin_code:
            return "未授權訪問", 401

        attempts_info = auth_service.get_login_attempts_info()
        return render_template(
            'admin_login_attempts.html',
            attempts=attempts_info,
            max_attempts=auth_service.max_attempts,
            block_duration=auth_service.block_duration//60
        )


def setup_directories(services):
    """
    設置必要的目錄

    Args:
        services: 服務實例字典
    """
    file_service = services['file_service']

    # 確保所有必要目錄存在
    for folder_key in ['DOWNLOADS_DIR', 'SUMMARIES_DIR', 'SUBTITLES_DIR', 'LOGS_DIR', 'TRASH_DIR', 'UPLOADS_DIR']:
        file_service.ensure_dir(get_config(f'PATHS.{folder_key}'))

    # 建立回收桶子資料夾
    file_service.ensure_dir(get_config('PATHS.TRASH_DIR') / "summaries")
    file_service.ensure_dir(get_config('PATHS.TRASH_DIR') / "subtitles")