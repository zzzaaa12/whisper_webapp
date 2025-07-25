from flask import Blueprint, request, jsonify
from src.config import get_config
from task_queue import get_task_queue, TaskStatus
import re
import os
from pathlib import Path
import uuid # Import uuid module

from src.services.auth_service import AuthService
from src.services.bookmark_service import BookmarkService
from src.services.trash_service import TrashService
from src.services.url_service import URLService
from src.services.file_service import file_service
from src.utils.time_formatter import get_timestamp
from src.utils.file_sanitizer import sanitize_filename
from src.utils.path_manager import get_path_manager
from src.utils.api_response import APIResponse, LegacyAPIResponse
from src.utils.url_builder import URLBuilder
from src.utils.auth_decorator import require_access_code, require_access_code_legacy

api_bp = Blueprint('api', __name__, url_prefix='/api')

# 使用統一的路徑管理器
path_manager = get_path_manager()
SUMMARY_FOLDER = path_manager.get_summary_folder()
SUBTITLE_FOLDER = path_manager.get_subtitle_folder()
TRASH_FOLDER = path_manager.get_trash_folder()
BOOKMARK_FILE = path_manager.get_bookmark_file()

auth_service = AuthService()
bookmark_service = BookmarkService(BOOKMARK_FILE, SUMMARY_FOLDER)
trash_service = TrashService(TRASH_FOLDER, SUMMARY_FOLDER, SUBTITLE_FOLDER)
url_service = URLService()

@api_bp.route('/trash/move', methods=['POST'])
def api_move_to_trash():
    try:
        data = request.get_json()
        if not data or 'files' not in data:
            return APIResponse.validation_error('缺少檔案列表')

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

        return APIResponse.success({'results': results}, '檔案移動操作完成')
    except Exception as e:
        return APIResponse.internal_error(f'操作失敗: {str(e)}')

@api_bp.route('/trash/restore', methods=['POST'])
def api_restore_from_trash():
    try:
        data = request.get_json()
        if not data or 'trash_id' not in data:
            return APIResponse.validation_error('缺少回收桶項目ID')

        trash_id = data['trash_id']
        success, message = trash_service.restore_file_from_trash(trash_id)

        if success:
            return APIResponse.success(message=message)
        else:
            return APIResponse.error(message, 400)
    except Exception as e:
        return APIResponse.internal_error(f'還原失敗: {str(e)}')

@api_bp.route('/trash/delete', methods=['POST'])
def api_delete_from_trash():
    try:
        data = request.get_json()
        if not data or 'trash_id' not in data:
            return APIResponse.validation_error('缺少回收桶項目ID')

        trash_id = data['trash_id']
        success, message = trash_service.delete_file_from_trash(trash_id)

        if success:
            return APIResponse.success(message=message)
        else:
            return APIResponse.error(message, 400)
    except Exception as e:
        return APIResponse.internal_error(f'刪除失敗: {str(e)}')

@api_bp.route('/trash/list')
def api_get_trash_list():
    try:
        trash_items = trash_service.get_trash_items()
        return APIResponse.success({'items': trash_items})
    except Exception as e:
        return APIResponse.internal_error(f'獲取列表失敗: {str(e)}')

@api_bp.route('/bookmarks/add', methods=['POST'])
def api_add_bookmark():
    try:
        data = request.get_json()
        filename = data.get('filename')
        title = data.get('title')

        if not filename:
            return APIResponse.validation_error('檔案名稱不能為空')

        success, message = bookmark_service.add_bookmark(filename, title)
        if success:
            return APIResponse.success(message=message)
        else:
            return APIResponse.error(message, 400)
    except Exception as e:
        return APIResponse.internal_error(str(e))

@api_bp.route('/bookmarks/remove', methods=['POST'])
def api_remove_bookmark():
    try:
        data = request.get_json()
        filename = data.get('filename')

        if not filename:
            return APIResponse.validation_error('檔案名稱不能為空')

        success, message = bookmark_service.remove_bookmark(filename)
        if success:
            return APIResponse.success(message=message)
        else:
            return APIResponse.error(message, 400)
    except Exception as e:
        return APIResponse.internal_error(str(e))

@api_bp.route('/bookmarks/list')
def api_get_bookmarks():
    try:
        bookmarks = bookmark_service.get_bookmarks()
        return APIResponse.success({
            'bookmarks': bookmarks,
            'count': len(bookmarks)
        })
    except Exception as e:
        return APIResponse.internal_error(str(e))

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
            return APIResponse.auth_error()
        return APIResponse.success(message='通行碼驗證成功')
    except Exception as e:
        return APIResponse.internal_error(f'驗證通行碼時發生錯誤：{str(e)}')

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

        # 如果是通過任務佇列處理，需要創建任務並更新結果
        task_id = data.get('task_id')
        if task_id:
            queue_manager = get_task_queue()
            # 更新任務結果
            result = {
                'summary_file': str(file_path),
                'filename': safe_filename,
                'file_size': len(content.encode('utf-8'))
            }
            queue_manager.update_task_status(
                task_id,
                TaskStatus.COMPLETED,
                progress=100,
                result=result
            )

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
        access_code = request.form.get('access_code', '').strip()

        # 檢查是否需要通行碼驗證
        from flask import session
        if get_config("ACCESS_CODE_ALL_PAGE", False) and session.get('is_authorized'):
            # 已通過全站認證，跳過通行碼驗證
            pass
        else:
            # 需要驗證通行碼
            if not auth_service.verify_access_code(access_code):
                return jsonify({'success': False, 'message': '通行碼錯誤'}), 401

        if 'media_file' not in request.files:
            return jsonify({'success': False, 'message': '沒有選擇檔案'}), 400

        file = request.files['media_file']
        user_ip = auth_service.get_client_ip()

        result = file_service.save_uploaded_media(file, user_ip)

        if not result.get('success'):
            status_code = result.pop('status_code', 500)
            return jsonify(result), status_code

        return jsonify(result)

    except Exception as e:
        # Consider logging the exception e for debugging
        return jsonify({'success': False, 'message': f'上傳檔案時發生未預期的錯誤：{str(e)}'}), 500

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

@api_bp.route('/queue/delete', methods=['POST'])
@require_access_code
def api_delete_failed_task():
    """刪除失敗的任務"""
    try:
        data = request.get_json()
        if not data or 'task_id' not in data:
            return APIResponse.validation_error('缺少任務ID')

        task_id = data['task_id']
        queue_manager = get_task_queue()
        success, message = queue_manager.delete_task(task_id)

        if success:
            return APIResponse.success(message=message)
        else:
            return APIResponse.error(message, 400)
    except Exception as e:
        return APIResponse.internal_error(f'刪除任務失敗: {str(e)}')

@api_bp.route('/queue/delete-batch', methods=['POST'])
@require_access_code
def api_delete_tasks_batch():
    """批量刪除指定狀態的任務"""
    try:
        data = request.get_json()
        if not data or 'status' not in data:
            return APIResponse.validation_error('缺少狀態參數')

        status = data['status']
        if status not in ['failed', 'cancelled']:
            return APIResponse.validation_error('只能批量刪除失敗或已取消的任務')

        queue_manager = get_task_queue()
        success, message, deleted_count = queue_manager.delete_tasks_by_status(status)

        if success:
            return APIResponse.success({
                'deleted_count': deleted_count,
                'message': message
            }, message)
        else:
            return APIResponse.error(message, 400)
    except Exception as e:
        return APIResponse.internal_error(f'批量刪除任務失敗: {str(e)}')

@api_bp.route('/queue/restart', methods=['POST'])
@require_access_code
def api_restart_failed_task():
    """重啟失敗的任務"""
    try:
        data = request.get_json()
        if not data or 'task_id' not in data:
            return APIResponse.validation_error('缺少任務ID')

        task_id = data['task_id']
        queue_manager = get_task_queue()
        success, message = queue_manager.restart_task(task_id)

        if success:
            return APIResponse.success(message=message)
        else:
            return APIResponse.error(message, 400)
    except Exception as e:
        return APIResponse.internal_error(f'重啟任務失敗: {str(e)}')

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

        # 檢查是否需要通行碼驗證
        from flask import session
        if get_config("ACCESS_CODE_ALL_PAGE", False) and session.get('is_authorized'):
            # 已通過全站認證，跳過通行碼驗證
            pass
        else:
            # 需要驗證通行碼
            if not auth_service.verify_access_code(access_code):
                return jsonify({'success': False, 'message': '通行碼錯誤'}), 401

        valid_types = ['youtube', 'upload_media', 'upload_subtitle']
        if task_type not in valid_types:
            return jsonify({'success': False, 'message': f'無效的任務類型。支援類型: {", ".join(valid_types)}'}), 400

        # 如果是 YouTube 任務，檢測是否為 live 直播
        if task_type == 'youtube':
            youtube_url = task_data.get('url', '')
            if youtube_url:
                if not url_service.validate_youtube_url(youtube_url):
                    return jsonify({'success': False, 'message': '請輸入有效的 YouTube 網址'}), 400

                is_live, live_message = url_service.is_youtube_live(youtube_url)
                if is_live:
                    return jsonify({'success': False, 'message': f'不支援處理直播影片。{live_message}'}), 400

        user_ip = auth_service.get_client_ip()
        queue_manager = get_task_queue()
        task_id = queue_manager.add_task(task_type, task_data, priority, user_ip)

        queue_position = queue_manager.get_user_queue_position(task_id)

        # 使用統一的URL構建工具
        base_url = URLBuilder.build_base_url()

        return APIResponse.success({
            'task_id': task_id,
            'queue_position': queue_position,
            'base_url': base_url
        }, '任務已加入佇列')
    except Exception as e:
        return APIResponse.internal_error(f'新增任務失敗: {str(e)}')

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

        # 檢查是否需要通行碼驗證
        from flask import session
        if get_config("ACCESS_CODE_ALL_PAGE", False) and session.get('is_authorized'):
            # 已通過全站認證，跳過通行碼驗證
            pass
        else:
            # 需要驗證通行碼
            if not auth_service.verify_access_code(access_code):
                return jsonify({'status': 'error', 'message': '通行碼錯誤'}), 401

        if not url_service.validate_youtube_url(youtube_url):
            return jsonify({'status': 'error', 'message': '請輸入有效的 YouTube 網址 (必須包含 https:// 或 http://)'}), 400

        if len(youtube_url) > 500:
            return jsonify({'status': 'error', 'message': 'URL 長度超過限制'}), 400

        # 檢測是否為 live 直播
        is_live, live_message = url_service.is_youtube_live(youtube_url)
        if is_live:
            return jsonify({'status': 'error', 'message': f'不支援處理直播影片。{live_message}'}), 400

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

        # 使用統一的URL構建工具
        base_url = URLBuilder.build_base_url()

        return LegacyAPIResponse.processing(
            f'YouTube任務已加入佇列，目前排隊位置: {queue_position}',
            queue_task_id,
            queue_position,
            youtube_url=youtube_url,
            base_url=base_url
        )

    except Exception as e:
        return LegacyAPIResponse.error(f'處理請求時發生錯誤：{str(e)}', 500)

@api_bp.route('/queue/status')
def api_queue_status():
    try:
        queue_manager = get_task_queue()
        status = queue_manager.get_queue_status()
        return APIResponse.success({'status': status})
    except Exception as e:
        return APIResponse.internal_error(str(e))

@api_bp.route('/queue/list')
def api_queue_list():
    try:
        queue_manager = get_task_queue()
        status_filter = request.args.get('status')
        limit = request.args.get('limit', type=int)
        tasks = queue_manager.get_task_list(status_filter, limit)
        return APIResponse.success({'tasks': tasks})
    except Exception as e:
        return APIResponse.internal_error(str(e))

@api_bp.route('/queue/task/<task_id>')
def api_queue_task_detail(task_id):
    try:
        queue_manager = get_task_queue()
        task = queue_manager.get_task(task_id)
        if task:
            return APIResponse.success({'task': task})
        else:
            return APIResponse.not_found('任務未找到')
    except Exception as e:
        return APIResponse.internal_error(str(e))

@api_bp.route('/delete', methods=['POST'])
def api_delete_summary():
    """刪除摘要檔案（移動到垃圾桶）"""
    try:
        data = request.get_json()
        if not data or 'filename' not in data:
            return jsonify({'success': False, 'message': '缺少檔案名稱'}), 400

        filename = data['filename']

        # 驗證檔案名稱
        if not filename or not filename.endswith('.txt'):
            return jsonify({'success': False, 'message': '無效的檔案名稱'}), 400

        file_path = SUMMARY_FOLDER / filename
        if not file_path.exists():
            return jsonify({'success': False, 'message': '檔案不存在'}), 404

        # 移動到垃圾桶
        success, message = trash_service.move_file_to_trash(file_path, 'summary')

        if success:
            return jsonify({'success': True, 'message': message})
        else:
            return jsonify({'success': False, 'message': message}), 500

    except Exception as e:
        return jsonify({'success': False, 'message': f'刪除失敗: {str(e)}'}), 500

@api_bp.route('/batch-delete', methods=['POST'])
def api_batch_delete_summaries():
    """批量刪除摘要檔案（移動到垃圾桶）"""
    try:
        data = request.get_json()
        if not data or 'filenames' not in data:
            return jsonify({'success': False, 'message': '缺少檔案列表'}), 400

        filenames = data['filenames']
        if not isinstance(filenames, list) or not filenames:
            return jsonify({'success': False, 'message': '檔案列表格式錯誤'}), 400

        results = []
        success_count = 0

        for filename in filenames:
            try:
                # 驗證檔案名稱
                if not filename or not filename.endswith('.txt'):
                    results.append({'filename': filename, 'success': False, 'message': '無效的檔案名稱'})
                    continue

                file_path = SUMMARY_FOLDER / filename
                if not file_path.exists():
                    results.append({'filename': filename, 'success': False, 'message': '檔案不存在'})
                    continue

                # 移動到垃圾桶
                success, message = trash_service.move_file_to_trash(file_path, 'summary')
                results.append({
                    'filename': filename,
                    'success': success,
                    'message': message
                })

                if success:
                    success_count += 1

            except Exception as e:
                results.append({
                    'filename': filename,
                    'success': False,
                    'message': f'處理失敗: {str(e)}'
                })

        return jsonify({
            'success': True,
            'message': f'批量刪除完成，成功處理 {success_count}/{len(filenames)} 個檔案',
            'results': results,
            'success_count': success_count,
            'total_count': len(filenames)
        })

    except Exception as e:
        return jsonify({'success': False, 'message': f'批量刪除失敗: {str(e)}'}), 500