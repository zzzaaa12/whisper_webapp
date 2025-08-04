from flask import Blueprint, render_template, send_file, request, session, redirect, url_for, flash
from pathlib import Path
import os
import re
from typing import Tuple, Optional
from urllib.parse import unquote

from src.config import get_config
from src.services.auth_service import AuthService
from src.services.bookmark_service import BookmarkService
from src.services.trash_service import TrashService
from src.utils.path_manager import get_path_manager

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


def validate_safe_path(filename: str, allowed_folder: Path,
                      allowed_extensions: Optional[set] = None) -> Tuple[bool, str, Optional[Path]]:
    """
    統一的檔案路徑安全驗證

    Args:
        filename: 檔案名稱
        allowed_folder: 允許的資料夾路徑
        allowed_extensions: 允許的副檔名集合（可選）

    Returns:
        tuple: (是否有效, 錯誤訊息, 安全路徑)
    """
    try:
        # URL 解碼檔案名稱
        decoded_filename = unquote(filename)

        # 構建安全路徑
        safe_path = (allowed_folder / decoded_filename).resolve()
        allowed_folder_resolved = allowed_folder.resolve()

        # 檢查路徑是否在允許的資料夾內
        if not str(safe_path).startswith(str(allowed_folder_resolved)):
            return False, "檔案路徑無效", None

        # 檢查檔案是否存在
        if not safe_path.exists():
            return False, "檔案不存在", None

        # 檢查副檔名（如果指定）
        if allowed_extensions and safe_path.suffix.lower() not in allowed_extensions:
            return False, "檔案類型不支援", None

        return True, "", safe_path

    except Exception as e:
        return False, f"檔案路徑驗證失敗: {str(e)}", None


def validate_summary_file(filename: str, summary_folder: Path) -> Tuple[bool, str, Optional[Path]]:
    """驗證摘要檔案"""
    return validate_safe_path(filename, summary_folder, allowed_extensions={'.txt'})


def validate_subtitle_file(filename: str, subtitle_folder: Path) -> Tuple[bool, str, Optional[Path]]:
    """驗證字幕檔案"""
    # 處理檔案名稱轉換（.txt -> .srt）
    if filename.endswith('.txt'):
        filename = filename[:-4] + '.srt'
    elif not filename.endswith('.srt'):
        filename += '.srt'

    return validate_safe_path(filename, subtitle_folder, allowed_extensions={'.srt'})


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

    if request.method == 'POST':
        code = request.form.get('access_code')
        if auth_service.verify_access_code(code):
            session['is_authorized'] = True
            # 讓 session 在瀏覽器關閉時過期
            session.permanent = False
            flash('登入成功！', 'success')

            next_url = request.form.get('next')
            # 安全性檢查：確保 next_url 是相對路徑
            if next_url and next_url.startswith('/'):
                return redirect(next_url)
            return redirect(url_for('main.index'))
        else:
            flash('通行碼不正確', 'danger')
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

    for f in files:
        channel = extract_channel_from_summary(f)

        # 統計每個頻道的摘要數量
        channel_counts[channel] = channel_counts.get(channel, 0) + 1

        summaries_with_info.append({
            'filename': f.name,
            'is_bookmarked': bookmark_service.is_bookmarked(f.name),
            'channel': channel
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

    return render_template('summaries.html',
                         summaries=summaries_with_info,
                         channels=sorted_channels,
                         channel_counts=channel_counts)

@main_bp.route('/summary/<filename>')
def show_summary(filename):
    from flask import request
    from src.core.task_queue import get_task_queue

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
    is_valid, error_msg, safe_path = validate_summary_file(filename, SUMMARY_FOLDER)
    if not is_valid:
        return error_msg, 400 if "無效" in error_msg else 404

    content = safe_path.read_text(encoding='utf-8')
    subtitle_filename = safe_path.stem + '.srt'
    subtitle_path = SUBTITLE_FOLDER / subtitle_filename
    has_subtitle = subtitle_path.exists()

    # 提取影片信息
    video_info = extract_video_info_from_summary(safe_path)

    return render_template('summary_detail.html',
                         title=safe_path.stem,
                         content=content,
                         filename=safe_path.name,
                         has_subtitle=has_subtitle,
                         video_info=video_info)

@main_bp.route('/download/summary/<filename>')
def download_summary(filename):
    try:
        # 使用統一的檔案驗證
        is_valid, error_msg, safe_path = validate_summary_file(filename, SUMMARY_FOLDER)
        if not is_valid:
            return error_msg, 400 if "無效" in error_msg else 404

        return send_file(safe_path, as_attachment=True, download_name=safe_path.name)
    except Exception as e:
        return f"下載失敗: {str(e)}", 500

@main_bp.route('/download/subtitle/<filename>')
def download_subtitle(filename):
    try:
        # 使用統一的檔案驗證
        is_valid, error_msg, safe_path = validate_subtitle_file(filename, SUBTITLE_FOLDER)
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