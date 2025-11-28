from flask import Blueprint, render_template, send_file, request, session, redirect, url_for, flash
from pathlib import Path
import os
import re
from datetime import datetime

from src.config import get_config
from src.utils.channel_mapping import get_display_name
from src.services.auth_service import AuthService
from src.services.bookmark_service import BookmarkService
from src.services.trash_service import TrashService
from src.services.notification_service import send_telegram_notification
from src.utils.path_manager import get_path_manager
from src.utils.file_validator import FileValidator

main_bp = Blueprint('main', __name__)

# 使用統一的路徑管理器
path_manager = get_path_manager()
SUMMARY_FOLDER = path_manager.get_summary_folder()
SUBTITLE_FOLDER = path_manager.get_subtitle_folder()
TRASH_FOLDER = path_manager.get_trash_folder()
BOOKMARK_FILE = path_manager.get_bookmark_file()

auth_service = AuthService()
bookmark_service = BookmarkService(BOOKMARK_FILE, SUMMARY_FOLDER)
trash_service = TrashService(TRASH_FOLDER, SUMMARY_FOLDER, SUBTITLE_FOLDER)


def extract_channel_from_summary(file_path):
    """從摘要文件中提取頻道信息"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            # 只讀取前幾行來尋找頻道信息
            for i, line in enumerate(f):
                if i > 10:  # 只檢查前10行
                    break
                # 尋找 "📺 頻道：" 格式
                if '📺 頻道：' in line:
                    channel = line.split('📺 頻道：')[1].strip()
                    return channel
                # 也支援其他可能的格式
                elif '頻道：' in line:
                    channel = line.split('頻道：')[1].strip()
                    return channel
        return "未知頻道"
    except Exception:
        return "未知頻道"


def extract_video_info_from_summary(file_path):
    """從摘要文件中提取影片信息"""
    video_info = {
        'title': None,
        'channel': None,
        'duration': None,
        'url': None,
        'process_time': None
    }

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            # 讀取前20行來尋找影片信息
            for i, line in enumerate(f):
                if i > 20:  # 只檢查前20行
                    break

                line = line.strip()

                # 提取標題
                if '🎬 標題：' in line:
                    video_info['title'] = line.split('🎬 標題：')[1].strip()
                elif '標題：' in line and not video_info['title']:
                    video_info['title'] = line.split('標題：')[1].strip()

                # 提取頻道
                if '📺 頻道：' in line:
                    video_info['channel'] = line.split('📺 頻道：')[1].strip()
                elif '頻道：' in line and not video_info['channel']:
                    video_info['channel'] = line.split('頻道：')[1].strip()

                # 提取影片長度
                if '⏱️ 影片長度：' in line:
                    video_info['duration'] = line.split('⏱️ 影片長度：')[1].strip()
                elif '影片長度：' in line:
                    video_info['duration'] = line.split('影片長度：')[1].strip()
                elif '時長：' in line:
                    video_info['duration'] = line.split('時長：')[1].strip()

                # 提取網址
                if '🔗 網址：' in line:
                    video_info['url'] = line.split('🔗 網址：')[1].strip()
                elif '網址：' in line and not video_info['url']:
                    video_info['url'] = line.split('網址：')[1].strip()

                # 提取處理時間
                if '⏰ 處理時間：' in line:
                    video_info['process_time'] = line.split('⏰ 處理時間：')[1].strip()
                elif '處理時間：' in line and not video_info['process_time']:
                    video_info['process_time'] = line.split('處理時間：')[1].strip()

    except Exception as e:
        print(f"提取影片信息時發生錯誤: {e}")

    return video_info


@main_bp.route('/access', methods=['GET', 'POST'])
def access():
    """處理全站通行碼驗證"""
    # 如果功能未開啟，或已經驗證過，直接導向首頁
    if not get_config("ACCESS_CODE_ALL_PAGE", False):
        session['is_authorized'] = True
        return redirect(url_for('main.index'))

    if session.get('is_authorized'):
        return redirect(url_for('main.index'))

    # 檢查 IP 是否被鎖定（GET 和 POST 都要檢查）
    client_ip = request.environ.get('REMOTE_ADDR', 'Unknown IP')
    if auth_service.is_locked(client_ip):
        lock_remaining = auth_service.get_lock_remaining_time(client_ip)
        lock_minutes = lock_remaining // 60
        lock_seconds = lock_remaining % 60

        # 對於被鎖定的 IP，直接渲染特殊的鎖定頁面
        return render_template('access_code.html',
                             is_locked=True,
                             lock_minutes=lock_minutes,
                             lock_seconds=lock_seconds)

    if request.method == 'POST':
        code = request.form.get('access_code')
        user_agent = request.headers.get('User-Agent', 'Unknown User Agent')

        if auth_service.verify_access_code(code):
            # 登入成功，重置該 IP 的錯誤計數
            auth_service.reset_attempts(client_ip)

            session['is_authorized'] = True
            # 讓 session 在瀏覽器關閉時過期
            session.permanent = False
            flash('登入成功！', 'success')

            # 發送通行碼驗證成功的 Telegram 通知
            success_message = (
                f"🟢 **通行碼驗證成功**\n\n"
                f"📧 **IP 位址**: `{client_ip}`\n"
                f"🖥️ **使用者代理**: `{user_agent}`\n"
                f"⏰ **時間**: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
            )
            send_telegram_notification(success_message)

            next_url = request.form.get('next')
            # 安全性檢查：確保 next_url 是相對路徑
            if next_url and next_url.startswith('/'):
                return redirect(next_url)
            return redirect(url_for('main.index'))
        else:
            # 記錄失敗嘗試，檢查是否觸發鎖定
            is_locked = auth_service.track_failed_attempt(client_ip)
            failed_count = auth_service.get_failed_attempts_count(client_ip)
            remaining_attempts = auth_service.get_remaining_attempts(client_ip)

            if is_locked:
                flash('通行碼錯誤次數過多，您的 IP 已被鎖定 30 分鐘', 'danger')

                # 發送 IP 被鎖定的通知
                locked_message = (
                    f"🔴 **IP 已被鎖定**\n\n"
                    f"❌ **最後輸入的通行碼**: `{code}`\n"
                    f"📧 **IP 位址**: `{client_ip}`\n"
                    f"🖥️ **使用者代理**: `{user_agent}`\n"
                    f"⏰ **時間**: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n"
                    f"🔢 **失敗次數**: `{failed_count}次`\n"
                    f"🔒 **鎖定時間**: `30分鐘`"
                )
                send_telegram_notification(locked_message)
            else:
                flash(f'通行碼不正確，還剩 {remaining_attempts} 次嘗試機會', 'danger')

                # 發送通行碼驗證失敗的 Telegram 通知
                failure_message = (
                    f"🔴 **通行碼驗證失敗**\n\n"
                    f"❌ **輸入的通行碼**: `{code}`\n"
                    f"📧 **IP 位址**: `{client_ip}`\n"
                    f"🖥️ **使用者代理**: `{user_agent}`\n"
                    f"⏰ **時間**: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n"
                    f"🔢 **累計失敗**: `{failed_count}次`\n"
                    f"⚠️ **剩餘嘗試**: `{remaining_attempts}次`"
                )
                send_telegram_notification(failure_message)

            return render_template('access_code.html')

    return render_template('access_code.html')


@main_bp.route('/')
def index():
    return render_template('index.html')


@main_bp.route('/summary')
def list_summaries():
    if not SUMMARY_FOLDER.exists():
        return "摘要資料夾不存在。", 500
    files = sorted(SUMMARY_FOLDER.glob('*.txt'), key=os.path.getmtime, reverse=True)

    summaries_with_info = []
    channel_counts = {}
    channel_original_names = {}  # 儲存顯示名稱對應的原始名稱

    for f in files:
        channel = extract_channel_from_summary(f)
        channel_display = get_display_name(channel)  # 取得顯示名稱
        video_info = extract_video_info_from_summary(f)

        # 使用文件內容中的標題，如果沒有則處理檔名作為標題
        if video_info.get('title'):
            display_title = video_info.get('title')
        else:
            # 從檔名提取更好的標題
            filename_title = f.stem
            # 移除常見的前綴模式，例如日期、Auto標記等
            filename_title = re.sub(r'^var_www_html_yt_sub_\d{8}_', '', filename_title)  # 移除路徑前綴和日期
            filename_title = re.sub(r'_summary$', '', filename_title)  # 移除結尾的_summary
            filename_title = filename_title.replace('_', ' ')  # 將底線替換為空格
            display_title = filename_title

        # 統計每個頻道的摘要數量（使用顯示名稱）
        channel_counts[channel_display] = channel_counts.get(channel_display, 0) + 1
        # 記錄原始名稱
        channel_original_names[channel_display] = channel

        # 讀取摘要預覽（提取核心主題）
        preview = ''
        try:
            content = f.read_text(encoding='utf-8')
            lines = content.split('\n')

            # 尋找核心主題區塊
            in_core_topics = False
            core_topics_lines = []

            for line in lines:
                line_stripped = line.strip()

                # 找到核心主題標題
                if '核心主題' in line_stripped and line_stripped.startswith('#'):
                    in_core_topics = True
                    continue

                # 如果在核心主題區塊中
                if in_core_topics:
                    # 遇到下一個標題就停止
                    if line_stripped.startswith('#'):
                        break

                    # 收集非空行
                    if line_stripped and not line_stripped.startswith('='):
                        core_topics_lines.append(line_stripped)

            # 合併內容並處理換行
            if core_topics_lines:
                # 合併所有行
                preview = ' '.join(core_topics_lines)

                # 在第二個及之後的 ' - ' 前插入換行符號
                parts = preview.split(' - ')
                if len(parts) > 1:
                    # 保留第一個項目，其餘項目前加換行
                    preview = parts[0] + ''.join(['\n- ' + part for part in parts[1:]])

                # 限制在200字以內
                if len(preview) > 200:
                    preview = preview[:200] + '...'
        except Exception as e:
            print(f"Error extracting preview from {f.name}: {e}")
            preview = ''

        summaries_with_info.append({
            'filename': f.name,
            'title': display_title,
            'preview': preview,  # 新增預覽
            'is_bookmarked': bookmark_service.is_bookmarked(f.name),
            'channel': channel,  # 保留原始名稱用於後端篩選
            'channel_display': channel_display  # 顯示名稱
        })

    # 更智能的頻道排序方式
    def sort_channels_smart(channels_dict):
        """
        智能排序頻道：
        1. 按摘要數量降序排列（最多摘要的頻道在前）
        2. 相同數量時按字母順序排列
        3. "未知頻道" 始終放在最後
        """
        # 分離出 "未知頻道"
        unknown_channel = "未知頻道"
        has_unknown = unknown_channel in channels_dict

        # 過濾掉 "未知頻道" 進行排序
        filtered_channels = {k: v for k, v in channels_dict.items() if k != unknown_channel}

        # 按數量降序，相同數量時按名稱升序
        sorted_channels = sorted(
            filtered_channels.items(),
            key=lambda x: (-x[1], x[0])  # 負號表示降序，然後按名稱升序
        )

        # 只返回頻道名稱
        result = [channel for channel, count in sorted_channels]

        # 將 "未知頻道" 放在最後
        if has_unknown:
            result.append(unknown_channel)

        return result

    sorted_channels = sort_channels_smart(channel_counts)

    # 只顯示前20個頻道用於快速篩選
    top_channels = sorted_channels[:20]

    return render_template('summaries.html',
                         summaries=summaries_with_info,
                         channels=sorted_channels,
                         top_channels=top_channels,
                         channel_counts=channel_counts,
                         channel_original_names=channel_original_names)


@main_bp.route('/summary/<filename>')
def show_summary(filename):
    from flask import request
    from task_queue import get_task_queue

    # New logic to handle task_id
    task_id = request.args.get('task_id')
    if task_id:
        task_queue = get_task_queue()
        task_info = task_queue.get_task(task_id)
        if task_info and task_info.get('result') and task_info['result'].get('summary_file'):
            summary_file_path = Path(task_info['result']['summary_file'])
            if summary_file_path.exists():
                filename = summary_file_path.name
            else:
                return "摘要檔案不存在 (透過任務ID)", 404
        else:
            return "任務或摘要檔案資訊不完整", 404

    # 使用統一的檔案驗證
    is_valid, error_msg, safe_path = FileValidator.validate_summary_file(filename, SUMMARY_FOLDER)
    if not is_valid:
        return error_msg, 400 if "無效" in error_msg else 404

    content = safe_path.read_text(encoding='utf-8')
    subtitle_filename = safe_path.stem + '.srt'
    subtitle_path = SUBTITLE_FOLDER / subtitle_filename
    has_subtitle = subtitle_path.exists()

    # 提取影片信息
    video_info = extract_video_info_from_summary(safe_path)

    # 使用文件內容中的標題，如果沒有則處理檔名作為標題
    if video_info.get('title'):
        page_title = video_info.get('title')
    else:
        # 從檔名提取更好的標題
        filename_title = safe_path.stem
        # 移除常見的前綴模式，例如日期、Auto標記等
        filename_title = re.sub(r'^var_www_html_yt_sub_\d{8}_', '', filename_title)  # 移除路徑前綴和日期
        filename_title = re.sub(r'_summary$', '', filename_title)  # 移除結尾的_summary
        filename_title = filename_title.replace('_', ' ')  # 將底線替換為空格
        page_title = filename_title

    return render_template('summary_detail.html',
                         title=page_title,
                         content=content,
                         filename=safe_path.name,
                         has_subtitle=has_subtitle,
                         video_info=video_info)

@main_bp.route('/download/summary/<filename>')
def download_summary(filename):
    try:
        # 使用統一的檔案驗證
        is_valid, error_msg, safe_path = FileValidator.validate_summary_file(filename, SUMMARY_FOLDER)
        if not is_valid:
            return error_msg, 400 if "無效" in error_msg else 404

        return send_file(safe_path, as_attachment=True, download_name=safe_path.name)
    except Exception as e:
        return f"下載失敗: {str(e)}", 500

@main_bp.route('/download/subtitle/<filename>')
def download_subtitle(filename):
    try:
        # 使用統一的檔案驗證
        is_valid, error_msg, safe_path = FileValidator.validate_subtitle_file(filename, SUBTITLE_FOLDER)
        if not is_valid:
            return error_msg, 400 if "無效" in error_msg else 404

        return send_file(safe_path, as_attachment=True, download_name=safe_path.name)
    except Exception as e:
        return f"下載失敗: {str(e)}", 500

@main_bp.route('/trash')
def trash_page():
    trash_items = trash_service.get_trash_items()
    return render_template('trash.html', trash_items=trash_items)

@main_bp.route('/bookmarks')
def bookmarks_page():
    try:
        bookmarks = bookmark_service.get_bookmarks()
        return render_template('bookmarks.html', bookmarks=bookmarks)
    except Exception as e:
        return f"Error loading bookmarks page: {e}", 500

@main_bp.route('/queue')
def queue_page():
    return render_template('queue.html')

@main_bp.route('/logout')
def logout():
    """處理登出功能"""
    session.clear()
    flash('您已成功登出', 'success')
    return redirect(url_for('main.access'))