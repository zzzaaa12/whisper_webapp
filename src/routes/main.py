
from flask import Blueprint, render_template, send_file, request, session, redirect, url_for, flash
from pathlib import Path
import os

from src.config import get_config
from src.services.auth_service import AuthService
from src.services.bookmark_service import BookmarkService
from src.services.trash_service import TrashService

main_bp = Blueprint('main', __name__)

BASE_DIR = Path(__file__).parent.parent.parent.resolve()
SUMMARY_FOLDER = BASE_DIR / "summaries"
SUBTITLE_FOLDER = BASE_DIR / "subtitles"
TRASH_FOLDER = BASE_DIR / "trash"
BOOKMARK_FILE = BASE_DIR / "bookmarks.json"

auth_service = AuthService()
bookmark_service = BookmarkService(BOOKMARK_FILE, SUMMARY_FOLDER)
trash_service = TrashService(TRASH_FOLDER, SUMMARY_FOLDER, SUBTITLE_FOLDER)


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

    summaries_with_bookmark_status = []
    for f in files:
        summaries_with_bookmark_status.append({
            'filename': f.name,
            'is_bookmarked': bookmark_service.is_bookmarked(f.name)
        })

    return render_template('summaries.html', summaries=summaries_with_bookmark_status)

@main_bp.route('/summary/<filename>')
def show_summary(filename):
    from urllib.parse import unquote
    from flask import request
    from task_queue import get_task_queue

    decoded_filename = unquote(filename)
    safe_path = SUMMARY_FOLDER / decoded_filename

    # New logic to handle task_id
    task_id = request.args.get('task_id')
    if task_id:
        task_queue = get_task_queue()
        task_info = task_queue.get_task(task_id)
        if task_info and task_info.get('result') and task_info['result'].get('summary_file'):
            summary_file_path = Path(task_info['result']['summary_file'])
            if summary_file_path.exists():
                safe_path = summary_file_path
                decoded_filename = summary_file_path.name
            else:
                return "摘要檔案不存在 (透過任務ID)", 404
        else:
            return "任務或摘要檔案資訊不完整", 404

    try:
        safe_path = safe_path.resolve()
        SUMMARY_FOLDER_RESOLVED = SUMMARY_FOLDER.resolve()
        if not str(safe_path).startswith(str(SUMMARY_FOLDER_RESOLVED)):
            return "檔案路徑無效", 400
        if not safe_path.exists():
            return "檔案不存在", 404
        if safe_path.suffix.lower() != '.txt':
            return "檔案類型不支援", 400
    except Exception:
        return "檔案路徑無效", 400

    content = safe_path.read_text(encoding='utf-8')
    subtitle_filename = safe_path.stem + '.srt'
    subtitle_path = SUBTITLE_FOLDER / subtitle_filename
    has_subtitle = subtitle_path.exists()

    return render_template('summary_detail.html',
                         title=safe_path.stem,
                         content=content,
                         filename=safe_path.name,
                         has_subtitle=has_subtitle)

@main_bp.route('/download/summary/<filename>')
def download_summary(filename):
    try:
        from urllib.parse import unquote
        filename = unquote(filename)
        safe_path = (SUMMARY_FOLDER / filename).resolve()
        SUMMARY_FOLDER_RESOLVED = SUMMARY_FOLDER.resolve()
        if not str(safe_path).startswith(str(SUMMARY_FOLDER_RESOLVED)):
            return "檔案路徑無效", 400
        if not safe_path.exists():
            return "檔案不存在", 404
        if safe_path.suffix.lower() != '.txt':
            return "檔案類型不支援", 400
        return send_file(safe_path, as_attachment=True, download_name=filename)
    except Exception as e:
        return f"下載失敗: {str(e)}", 500

@main_bp.route('/download/subtitle/<filename>')
def download_subtitle(filename):
    try:
        from urllib.parse import unquote
        filename = unquote(filename)
        if filename.endswith('.txt'):
            filename = filename[:-4] + '.srt'
        elif not filename.endswith('.srt'):
            filename += '.srt'
        safe_path = (SUBTITLE_FOLDER / filename).resolve()
        SUBTITLE_FOLDER_RESOLVED = SUBTITLE_FOLDER.resolve()
        if not str(safe_path).startswith(str(SUBTITLE_FOLDER_RESOLVED)):
            return "檔案路徑無效", 400
        if not safe_path.exists():
            return "字幕檔案不存在", 404
        if safe_path.suffix.lower() != '.srt':
            return "檔案類型不支援", 400
        return send_file(safe_path, as_attachment=True, download_name=filename)
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
