"""Page routes for the parallel v2 web interface."""

import re

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for


v2_bp = Blueprint("v2", __name__, url_prefix="/v2")


@v2_bp.route("")
@v2_bp.route("/")
def index():
    return render_template("v2/index.html", active_page="home")



@v2_bp.route("/tasks/new")
def new_task():
    return render_template("v2/new_task.html", active_page="new-task")


@v2_bp.route("/queue")
def queue():
    return render_template("v2/queue.html", active_page="queue")


@v2_bp.route("/summaries")
def summaries():
    return render_template("v2/summaries.html", active_page="summaries")


@v2_bp.route("/bookmarks")
def bookmarks():
    return render_template("v2/bookmarks.html", active_page="bookmarks")


def _settings_authorized():
    return bool(session.get("is_authorized"))


@v2_bp.route("/settings", methods=["GET", "POST"])
def settings():
    from src.config import get_config, update_config

    if not _settings_authorized():
        if request.method == "POST":
            return jsonify({"success": False, "message": "請先使用通行碼登入"}), 401
        return redirect(url_for("main.access", next=request.path))

    providers = get_config("AI_PROVIDERS", {}) or {}
    provider_view = []
    for name, provider in providers.items():
        if name.startswith("_") or not isinstance(provider, dict):
            continue
        provider_view.append({
            "name": name,
            "configured": bool(str(provider.get("api_key", "")).strip()) and "your " not in str(provider.get("api_key", "")).lower(),
            "base_url": provider.get("base_url", ""),
            "model": provider.get("model", ""),
            "max_tokens": provider.get("max_tokens", 10000),
            "temperature": provider.get("temperature", 0.7),
        })

    if request.method == "GET":
        schedule = get_config("TRANSCRIPTION_SCHEDULE", {}) or {}
        return render_template(
            "v2/settings.html", active_page="settings", providers=provider_view,
            current_provider=get_config("AI_PROVIDER", "openai"),
            fallback_enabled=bool(get_config("AI_FALLBACK_ENABLED", True)),
            fallback_order=", ".join(get_config("AI_FALLBACK_ORDER", [])),
            gpu_only=bool(get_config("GPU_ONLY", True)),
            dynamic_unload=bool(get_config("whisper.dynamic_unload_enabled", False)),
            telegram_configured=bool(get_config("TELEGRAM_BOT_TOKEN", "")),
            telegram_chat_id=get_config("TELEGRAM_CHAT_ID", ""),
            telegram_attempts=int(get_config("TELEGRAM_MAX_ATTEMPTS", 3)),
            schedule=schedule,
            access_code_configured=bool(get_config("ACCESS_CODE", "")),
            access_all=bool(get_config("ACCESS_CODE_ALL_PAGE", False)),
            server_port=int(get_config("SERVER_PORT", 5000)),
            public_port=int(get_config("PUBLIC_PORT", 0)),
            website_base_url=get_config("WEBSITE_BASE_URL", "localhost"),
            use_ssl=bool(get_config("USE_SSL", False)),
            force_ipv4=bool(get_config("YTDLP_FORCE_IPV4", True)),
        )

    data = request.get_json(silent=True) or {}
    values = data.get("values")
    if not isinstance(values, dict):
        return jsonify({"success": False, "message": "設定格式錯誤"}), 400

    allowed_bool = {"AI_FALLBACK_ENABLED", "GPU_ONLY", "whisper.dynamic_unload_enabled", "TRANSCRIPTION_SCHEDULE.enabled", "ACCESS_CODE_ALL_PAGE", "USE_SSL", "YTDLP_FORCE_IPV4"}
    allowed_int = {"TELEGRAM_MAX_ATTEMPTS": (1, 10), "TRANSCRIPTION_SCHEDULE.slot_minutes": (5, 240), "SERVER_PORT": (1, 65535), "PUBLIC_PORT": (0, 65535)}
    allowed_text = {"AI_PROVIDER", "TELEGRAM_CHAT_ID", "TRANSCRIPTION_SCHEDULE.timezone", "WEBSITE_BASE_URL"}
    allowed_lists = {"AI_FALLBACK_ORDER", "TRANSCRIPTION_SCHEDULE.apply_to_task_types"}
    updates = {}
    try:
        for key, value in values.items():
            if key in allowed_bool:
                if not isinstance(value, bool): raise ValueError(f"{key} 必須是布林值")
                updates[key] = value
            elif key in allowed_int:
                number = int(value); minimum, maximum = allowed_int[key]
                if not minimum <= number <= maximum: raise ValueError(f"{key} 超出允許範圍")
                updates[key] = number
            elif key in allowed_text:
                text_value = str(value).strip()
                if key == "AI_PROVIDER" and text_value not in {item["name"] for item in provider_view}:
                    raise ValueError("未知的 AI 供應商")
                updates[key] = text_value
            elif key in allowed_lists:
                if not isinstance(value, list): raise ValueError(f"{key} 必須是清單")
                updates[key] = [str(item).strip() for item in value if str(item).strip()]
            elif key.startswith("TRANSCRIPTION_SCHEDULE.weekdays.") and key.rsplit(".", 1)[-1] in set("0123456"):
                if not isinstance(value, list): raise ValueError("排程時段必須是清單")
                updates[key] = [str(item).strip() for item in value if str(item).strip()]
            elif key.startswith("AI_PROVIDERS."):
                parts = key.split(".")
                if len(parts) != 3 or parts[1] not in {item["name"] for item in provider_view} or parts[2] not in {"api_key", "base_url", "model", "max_tokens", "temperature"}:
                    raise ValueError("不允許修改這個 AI 設定")
                if parts[2] == "api_key" and not str(value).strip(): continue
                if parts[2] == "max_tokens": value = max(1, min(200000, int(value)))
                elif parts[2] == "temperature": value = max(0, min(2, float(value)))
                else: value = str(value).strip()
                updates[key] = value
            elif key in {"TELEGRAM_BOT_TOKEN", "ACCESS_CODE"}:
                if str(value).strip(): updates[key] = str(value).strip()
            else:
                raise ValueError(f"不允許修改設定：{key}")
    except (TypeError, ValueError) as error:
        return jsonify({"success": False, "message": str(error)}), 400

    update_config(updates)
    return jsonify({"success": True, "message": "設定已儲存", "restart_required": any(key in {"ACCESS_CODE", "ACCESS_CODE_ALL_PAGE", "SERVER_PORT", "PUBLIC_PORT", "WEBSITE_BASE_URL", "USE_SSL"} for key in updates)})


@v2_bp.route("/summaries/<filename>")
def summary_detail(filename):
    from src.routes.main import (
        SUMMARY_FOLDER,
        SUBTITLE_FOLDER,
        bookmark_service,
        extract_video_info_from_summary,
    )
    from src.utils.file_validator import FileValidator

    is_valid, error_message, safe_path = FileValidator.validate_summary_file(
        filename, SUMMARY_FOLDER
    )
    if not is_valid:
        return error_message, 400 if "無效" in error_message else 404

    content = safe_path.read_text(encoding="utf-8")
    video_info = extract_video_info_from_summary(safe_path)
    if video_info.get("url") and not video_info["url"].startswith(("http://", "https://")):
        video_info["url"] = None

    title = video_info.get("title")
    if not title:
        title = re.sub(r"^var_www_html_yt_sub_\d{8}_", "", safe_path.stem)
        title = re.sub(r"_summary$", "", title).replace("_", " ")

    subtitle_filename = f"{safe_path.stem}.srt"
    return_url = request.args.get("return", "")
    allowed_return = (
        return_url in ("/v2", "/v2/")
        or return_url.startswith("/v2/summaries")
        or return_url.startswith("/v2/bookmarks")
    )
    if not allowed_return:
        return_url = "/v2/summaries"
    return render_template(
        "v2/summary_detail.html",
        active_page="summaries",
        title=title,
        content=content,
        filename=safe_path.name,
        subtitle_filename=subtitle_filename,
        has_subtitle=(SUBTITLE_FOLDER / subtitle_filename).is_file(),
        is_bookmarked=bookmark_service.is_bookmarked(safe_path.name),
        video_info=video_info,
        return_url=return_url,
    )


@v2_bp.route("/api-docs")
def api_docs():
    return render_template("v2/api_docs.html", active_page="api-docs")
