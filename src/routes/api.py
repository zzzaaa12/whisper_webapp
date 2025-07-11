from flask import Blueprint, request, jsonify
from src.config import get_config
from task_queue import get_task_queue
import re
from pathlib import Path
import uuid # Import uuid module

from src.services.auth_service import AuthService
from src.services.bookmark_service import BookmarkService
from src.services.trash_service import TrashService
from src.services.url_service import URLService
from src.utils.time_formatter import get_timestamp
from src.utils.file_sanitizer import sanitize_filename

api_bp = Blueprint('api', __name__, url_prefix='/api')

BASE_DIR = Path(__file__).parent.parent.parent.resolve()
SUMMARY_FOLDER = BASE_DIR / "summaries"
SUBTITLE_FOLDER = BASE_DIR / "subtitles"
TRASH_FOLDER = BASE_DIR / "trash"
UPLOAD_FOLDER = BASE_DIR / "uploads"
BOOKMARK_FILE = BASE_DIR / "bookmarks.json"

auth_service = AuthService()
bookmark_service = BookmarkService(BOOKMARK_FILE, SUMMARY_FOLDER)
trash_service = TrashService(TRASH_FOLDER, SUMMARY_FOLDER, SUBTITLE_FOLDER)
url_service = URLService()

@api_bp.route('/trash/move', methods=['POST'])
def api_move_to_trash():
    try:
        data = request.get_json()
        if not data or 'files' not in data:
            return jsonify({'success': False, 'message': '缺少檔案列表'}), 400

        results = []
        for file_info in data['files']:
            file_path = file_info.get('path')
            file_type = file_info.get('type', 'summary')

            if not file_path:
                results.append({'success': False, 'message': '缺少檔案路徑'})
                continue

            success, message = trash_service.move_file_to_trash(Path(file_path), file_type)
            results.append({
                'success': success,
                'message': message,
                'file_path': file_path
            })

        return jsonify({
            'success': True,
            'results': results
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'操作失敗: {str(e)}'}), 500

@api_bp.route('/trash/restore', methods=['POST'])
def api_restore_from_trash():
    try:
        data = request.get_json()
        if not data or 'trash_id' not in data:
            return jsonify({'success': False, 'message': '缺少回收桶項目ID'}), 400

        trash_id = data['trash_id']
        success, message = trash_service.restore_file_from_trash(trash_id)

        return jsonify({
            'success': success,
            'message': message
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'還原失敗: {str(e)}'}), 500

@api_bp.route('/trash/delete', methods=['POST'])
def api_delete_from_trash():
    try:
        data = request.get_json()
        if not data or 'trash_id' not in data:
            return jsonify({'success': False, 'message': '缺少回收桶項目ID'}), 400

        trash_id = data['trash_id']
        success, message = trash_service.delete_file_from_trash(trash_id)

        return jsonify({
            'success': success,
            'message': message
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'刪除失敗: {str(e)}'}), 500

@api_bp.route('/trash/list')
def api_get_trash_list():
    try:
        trash_items = trash_service.get_trash_items()
        return jsonify({
            'success': True,
            'items': trash_items
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'獲取列表失敗: {str(e)}'}), 500

@api_bp.route('/bookmarks/add', methods=['POST'])
def api_add_bookmark():
    try:
        data = request.get_json()
        filename = data.get('filename')
        title = data.get('title')

        if not filename:
            return jsonify({'success': False, 'message': '檔案名稱不能為空'})

        success, message = bookmark_service.add_bookmark(filename, title)
        return jsonify({'success': success, 'message': message})

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@api_bp.route('/bookmarks/remove', methods=['POST'])
def api_remove_bookmark():
    try:
        data = request.get_json()
        filename = data.get('filename')

        if not filename:
            return jsonify({'success': False, 'message': '檔案名稱不能為空'})

        success, message = bookmark_service.remove_bookmark(filename)
        return jsonify({'success': success, 'message': message})

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@api_bp.route('/bookmarks/list')
def api_get_bookmarks():
    try:
        bookmarks = bookmark_service.get_bookmarks()
        return jsonify({
            'success': True,
            'bookmarks': bookmarks,
            'count': len(bookmarks)
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@api_bp.route('/bookmarks/check/<filename>')
def api_check_bookmark(filename):
    try:
        is_bookmarked_result = bookmark_service.is_bookmarked(filename)
        return jsonify({
            'success': True,
            'is_bookmarked': is_bookmarked_result
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@api_bp.route('/system/config-status')
def api_get_config_status():
    try:
        access_code = get_config("ACCESS_CODE")
        openai_key = get_config("OPENAI_API_KEY")
        return jsonify({
            'success': True,
            'has_access_code': bool(access_code),
            'has_openai_key': bool(openai_key)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'獲取配置狀態失敗: {str(e)}'
        }), 500

@api_bp.route('/verify_access_code', methods=['POST'])
def api_verify_access_code():
    try:
        access_code = request.form.get('access_code', '').strip()
        if not auth_service.verify_access_code(access_code):
            return jsonify({'success': False, 'message': '通行碼錯誤'}), 401
        return jsonify({'success': True, 'message': '通行碼驗證成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'驗證通行碼時發生錯誤：{str(e)}'}), 500

@api_bp.route('/upload_subtitle', methods=['POST'])
def api_upload_subtitle():
    try:
        if not request.is_json:
            return jsonify({'success': False, 'message': '請求格式錯誤，需要 JSON 格式'}), 400
        data = request.get_json()
        filename = data.get('filename', '').strip()
        content = data.get('content', '')
        access_code = data.get('access_code', '').strip()

        if not filename:
            return jsonify({'success': False, 'message': '缺少檔案名稱參數'}), 400
        if not content:
            return jsonify({'success': False, 'message': '缺少檔案內容參數'}), 400
        if not auth_service.verify_access_code(access_code):
            return jsonify({'success': False, 'message': '通行碼錯誤'}), 401

        safe_filename = filename
        if not safe_filename:
            return jsonify({'success': False, 'message': '檔案名稱無效'}), 400
        if not safe_filename.lower().endswith('.txt'):
            safe_filename += '.txt'

        file_path = SUMMARY_FOLDER / safe_filename
        if file_path.exists():
            return jsonify({'success': False, 'message': f'檔案 {safe_filename} 已存在'}), 409

        if len(content.encode('utf-8')) > 10 * 1024 * 1024:
            return jsonify({'success': False, 'message': '檔案內容過大，最大限制 10MB'}), 413

        SUMMARY_FOLDER.mkdir(exist_ok=True)
        file_path.write_text(content, encoding='utf-8')

        return jsonify({
            'success': True,
            'message': '檔案上傳成功',
            'filename': safe_filename,
            'path': str(file_path),
            'size': len(content.encode('utf-8'))
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'上傳檔案時發生錯誤：{str(e)}'}), 500

@api_bp.route('/upload_media', methods=['POST'])
def api_upload_media():
    try:
        if 'media_file' not in request.files:
            return jsonify({'success': False, 'message': '沒有選擇檔案'}), 400
        file = request.files['media_file']
        if file.filename == '':
            return jsonify({'success': False, 'message': '沒有選擇檔案'}), 400

        access_code = request.form.get('access_code', '').strip()
        title = os.path.splitext(file.filename)[0] if file.filename else ""

        if not auth_service.verify_access_code(access_code):
            return jsonify({'success': False, 'message': '通行碼錯誤'}), 401

        file.seek(0, 2)
        file_size = file.tell()
        file.seek(0)

        max_size = 500 * 1024 * 1024
        if file_size > max_size:
            return jsonify({'success': False, 'message': f'檔案過大，最大限制 500MB，目前檔案 {file_size / (1024*1024):.1f}MB'}), 413

        allowed_extensions = {
            '.mp3', '.mp4', '.wav', '.m4a', '.flv', '.avi', '.mov',
            '.mkv', '.webm', '.ogg', '.aac', '.wma', '.wmv', '.3gp'
        }
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in allowed_extensions:
            return jsonify({'success': False, 'message': f'不支援的檔案格式：{file_ext}。支援格式：{", ".join(sorted(allowed_extensions))}'}), 400

        timestamp = get_timestamp("file")
        safe_title = sanitize_filename(title) if title else "未命名"
        task_id = str(uuid.uuid4())[:8]
        safe_filename = f"{timestamp}_{task_id}_{safe_title}{file_ext}"

        UPLOAD_FOLDER.mkdir(exist_ok=True)
        file_path = UPLOAD_FOLDER / safe_filename
        file.save(str(file_path))

        date_str = get_timestamp("date")
        base_name = f"{date_str} - {safe_title}"
        subtitle_path = SUBTITLE_FOLDER / f"{base_name}.srt"
        summary_path = SUMMARY_FOLDER / f"{base_name}.txt"

        user_ip = auth_service.get_client_ip()
        queue_manager = get_task_queue()

        task_data = {
            'audio_file': str(file_path),
            'subtitle_path': str(subtitle_path),
            'summary_path': str(summary_path),
            'title': title or safe_title,
            'filename': safe_filename
        }

        queue_task_id = queue_manager.add_task('upload_media', task_data, priority=5, user_ip=user_ip)

        queue_position = queue_manager.get_user_queue_position(queue_task_id)

        website_base_url = get_config("WEBSITE_BASE_URL", "127.0.0.1")
        use_ssl = get_config("USE_SSL", False)
        server_port = get_config("SERVER_PORT", 5000)
        public_port = get_config("PUBLIC_PORT", 0)

        effective_port = public_port if public_port > 0 else server_port

        protocol = "https" if use_ssl else "http"
        if (protocol == "http" and effective_port == 80) or \
           (protocol == "https" and effective_port == 443):
            base_url = f"{protocol}://{website_base_url}"
        else:
            base_url = f"{protocol}://{website_base_url}:{effective_port}"
        summary_url = f"{base_url}/summaries/{queue_task_id}"

        return jsonify({
            'success': True,
            'message': '檔案上傳成功，已加入處理佇列',
            'task_id': queue_task_id,
            'queue_position': queue_position,
            'filename': safe_filename,
            'title': title or safe_title,
            'file_size': file_size,
            'original_task_id': task_id,
            'summary_url': summary_url
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'上傳檔案時發生錯誤：{str(e)}'}), 500

@api_bp.route('/queue/cancel', methods=['POST'])
def api_cancel_queue_task():
    try:
        data = request.get_json()
        if not data or 'task_id' not in data:
            return jsonify({'success': False, 'message': '缺少任務ID'}), 400

        task_id = data['task_id']
        access_code = data.get('access_code', '').strip()

        if not auth_service.verify_access_code(access_code):
            return jsonify({'success': False, 'message': '通行碼錯誤'}), 401

        queue_manager = get_task_queue()
        success, message = queue_manager.cancel_task(task_id, access_code)

        return jsonify({
            'success': success,
            'message': message
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'取消任務失敗: {str(e)}'}), 500

@api_bp.route('/queue/cleanup', methods=['POST'])
def api_cleanup_queue():
    try:
        data = request.get_json()
        access_code = data.get('access_code', '').strip() if data else ''
        older_than_days = data.get('older_than_days', 7) if data else 7

        if not auth_service.verify_access_code(access_code):
            return jsonify({'success': False, 'message': '通行碼錯誤'}), 401

        queue_manager = get_task_queue()
        deleted_count = queue_manager.cleanup_completed_tasks(older_than_days)

        return jsonify({
            'success': True,
            'message': f'已清理 {deleted_count} 個已完成的任務',
            'deleted_count': deleted_count
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'清理任務失敗: {str(e)}'}), 500

@api_bp.route('/queue/add', methods=['POST'])
def api_add_queue_task():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': '缺少請求資料'}), 400

        task_type = data.get('task_type')
        task_data = data.get('data', {})
        priority = data.get('priority', 5)
        access_code = data.get('access_code', '').strip()

        if not task_type:
            return jsonify({'success': False, 'message': '缺少任務類型'}), 400
        if not auth_service.verify_access_code(access_code):
            return jsonify({'success': False, 'message': '通行碼錯誤'}), 401

        valid_types = ['youtube', 'upload_media', 'upload_subtitle']
        if task_type not in valid_types:
            return jsonify({'success': False, 'message': f'無效的任務類型。支援類型: {", ".join(valid_types)}'}), 400

        user_ip = auth_service.get_client_ip()
        queue_manager = get_task_queue()
        task_id = queue_manager.add_task(task_type, task_data, priority, user_ip)

        queue_position = queue_manager.get_user_queue_position(task_id)

        website_base_url = get_config("WEBSITE_BASE_URL", "127.0.0.1")
        use_ssl = get_config("USE_SSL", False)
        server_port = get_config("SERVER_PORT", 5000)
        public_port = get_config("PUBLIC_PORT", 0)

        effective_port = public_port if public_port > 0 else server_port

        protocol = "https" if use_ssl else "http"
        if (protocol == "http" and effective_port == 80) or \
           (protocol == "https" and effective_port == 443):
            base_url = f"{protocol}://{website_base_url}"
        else:
            base_url = f"{protocol}://{website_base_url}:{effective_port}"
        summary_url = f"{base_url}/summaries/{task_id}"

        return jsonify({
            'success': True,
            'message': '任務已加入佇列',
            'task_id': task_id,
            'queue_position': queue_position,
            'summary_url': summary_url
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'新增任務失敗: {str(e)}'}), 500

@api_bp.route('/process', methods=['POST'])
def api_process_youtube():
    try:
        if not request.is_json:
            return jsonify({'status': 'error', 'message': '請求格式錯誤，需要 JSON 格式'}), 400

        data = request.get_json()
        youtube_url = data.get('youtube_url', '').strip()
        auto_process = data.get('auto', 0) == 1
        access_code = data.get('access_code', '').strip()

        if not youtube_url:
            return jsonify({'status': 'error', 'message': '缺少 youtube_url 參數'}), 400
        if not auth_service.verify_access_code(access_code):
            return jsonify({'status': 'error', 'message': '通行碼錯誤'}), 401

        if not url_service.validate_youtube_url(youtube_url):
            return jsonify({'status': 'error', 'message': '請輸入有效的 YouTube 網址 (必須包含 https:// 或 http://)'}), 400

        if len(youtube_url) > 500:
            return jsonify({'status': 'error', 'message': 'URL 長度超過限制'}), 400

        user_ip = auth_service.get_client_ip()
        queue_manager = get_task_queue()

        task_data = {
            'url': youtube_url,
            'auto': auto_process
        }

        try:
            from urllib.parse import urlparse, parse_qs
            parsed_url = urlparse(youtube_url)

            if 'youtube.com' in parsed_url.netloc:
                video_id = parse_qs(parsed_url.query).get('v', [None])[0]
                if video_id:
                    task_data['video_id'] = video_id
                    task_data['display_name'] = f"YouTube 影片 ({video_id})"
            elif 'youtu.be' in parsed_url.netloc:
                video_id = parsed_url.path.lstrip('/')
                if video_id:
                    task_data['video_id'] = video_id
                    task_data['display_name'] = f"YouTube 影片 ({video_id})"
        except Exception as e:
            print(f"無法解析YouTube URL: {e}")
            task_data['display_name'] = "YouTube 影片"

        queue_task_id = queue_manager.add_task('youtube', task_data, priority=5, user_ip=user_ip)
        queue_position = queue_manager.get_user_queue_position(queue_task_id)

        website_base_url = get_config("WEBSITE_BASE_URL", "127.0.0.1")
        use_ssl = get_config("USE_SSL", False)
        server_port = get_config("SERVER_PORT", 5000)
        public_port = get_config("PUBLIC_PORT", 0)

        effective_port = public_port if public_port > 0 else server_port

        protocol = "https" if use_ssl else "http"
        if (protocol == "http" and effective_port == 80) or \
           (protocol == "https" and effective_port == 443):
            base_url = f"{protocol}://{website_base_url}"
        else:
            base_url = f"{protocol}://{website_base_url}:{effective_port}"
        summary_url = f"{base_url}/summaries/{queue_task_id}"

        return jsonify({
            'status': 'processing',
            'message': f'YouTube任務已加入佇列，目前排隊位置: {queue_position}',
            'task_id': queue_task_id,
            'queue_position': queue_position,
            'youtube_url': youtube_url,
            'summary_url': summary_url
        }), 200

    except Exception as e:
        return jsonify({'status': 'error', 'message': f'處理請求時發生錯誤：{str(e)}'}), 500

@api_bp.route('/queue/status')
def api_queue_status():
    try:
        queue_manager = get_task_queue()
        status = queue_manager.get_queue_status()
        return jsonify({'success': True, 'status': status})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@api_bp.route('/queue/list')
def api_queue_list():
    try:
        queue_manager = get_task_queue()
        status_filter = request.args.get('status')
        limit = request.args.get('limit', type=int)
        tasks = queue_manager.get_task_list(status_filter, limit)
        return jsonify({'success': True, 'tasks': tasks})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@api_bp.route('/queue/task/<task_id>')
def api_queue_task_detail(task_id):
    try:
        queue_manager = get_task_queue()
        task = queue_manager.get_task(task_id)
        if task:
            return jsonify({'success': True, 'task': task})
        else:
            return jsonify({'success': False, 'message': '任務未找到'}), 404
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500