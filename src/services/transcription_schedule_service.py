from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from threading import Lock
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from src.config import get_config


DEFAULT_TIME_RANGES = ["00:00-08:00", "12:30-13:30", "18:30-20:00"]
DEFAULT_TIMEZONE = "Asia/Taipei"
DEFAULT_TASK_TYPES = ["youtube", "upload_media"]
WEEKDAY_KEYS = [str(i) for i in range(7)]
SLOTS_PER_DAY = 48
SLOT_MINUTES = 30


_force_run_lock = Lock()
_force_run_state = {
    "enabled": False,
    "forced_task_ids": [],
    "forced_at": None,
    "forced_by": None,
}


def _default_weekdays() -> Dict[str, List[str]]:
    return {day: list(DEFAULT_TIME_RANGES) for day in WEEKDAY_KEYS}


def get_default_schedule_config() -> dict:
    return {
        "enabled": True,
        "timezone": DEFAULT_TIMEZONE,
        "slot_minutes": SLOT_MINUTES,
        "apply_to_task_types": list(DEFAULT_TASK_TYPES),
        "weekdays": _default_weekdays(),
    }


def _parse_time_to_slot(value: str) -> int:
    hour_text, minute_text = value.split(":", 1)
    hour = int(hour_text)
    minute = int(minute_text)
    return (hour * 60 + minute) // SLOT_MINUTES


def _format_slot(slot: int) -> str:
    total_minutes = slot * SLOT_MINUTES
    hour = total_minutes // 60
    minute = total_minutes % 60
    return f"{hour:02d}:{minute:02d}"


def _ranges_to_slots(ranges: List[str]) -> List[bool]:
    slots = [False] * SLOTS_PER_DAY
    for range_value in ranges:
        if not isinstance(range_value, str) or "-" not in range_value:
            continue
        start_text, end_text = range_value.split("-", 1)
        try:
            start_slot = max(0, min(SLOTS_PER_DAY, _parse_time_to_slot(start_text)))
            end_slot = max(0, min(SLOTS_PER_DAY, _parse_time_to_slot(end_text)))
        except Exception:
            continue

        for slot in range(start_slot, end_slot):
            slots[slot] = True
    return slots


def _slots_to_ranges(slots: List[bool]) -> List[str]:
    ranges: List[str] = []
    start_slot: Optional[int] = None
    padded_slots = list(slots) + [False]

    for slot_index, enabled in enumerate(padded_slots):
        if enabled and start_slot is None:
            start_slot = slot_index
        elif not enabled and start_slot is not None:
            ranges.append(f"{_format_slot(start_slot)}-{_format_slot(slot_index)}")
            start_slot = None

    return ranges


def normalize_schedule_config(raw_schedule: Optional[dict]) -> dict:
    schedule = deepcopy(get_default_schedule_config())
    if isinstance(raw_schedule, dict):
        schedule["enabled"] = bool(raw_schedule.get("enabled", schedule["enabled"]))
        schedule["timezone"] = str(raw_schedule.get("timezone", schedule["timezone"]) or DEFAULT_TIMEZONE)
        schedule["slot_minutes"] = SLOT_MINUTES

        task_types = raw_schedule.get("apply_to_task_types", schedule["apply_to_task_types"])
        if isinstance(task_types, list):
            cleaned_types = [task_type for task_type in task_types if task_type in DEFAULT_TASK_TYPES]
            schedule["apply_to_task_types"] = cleaned_types or list(DEFAULT_TASK_TYPES)

        weekdays = raw_schedule.get("weekdays", {})
        if isinstance(weekdays, dict):
            normalized_weekdays = {}
            for day in WEEKDAY_KEYS:
                day_value = weekdays.get(day, DEFAULT_TIME_RANGES)
                if not isinstance(day_value, list):
                    day_value = list(DEFAULT_TIME_RANGES)
                normalized_weekdays[day] = _slots_to_ranges(_ranges_to_slots(day_value))
            schedule["weekdays"] = normalized_weekdays

    return schedule


def get_transcription_schedule_config() -> dict:
    raw_schedule = get_config("TRANSCRIPTION_SCHEDULE", None)
    return normalize_schedule_config(raw_schedule)


def build_schedule_grid(schedule: dict) -> Dict[str, List[bool]]:
    weekdays = schedule.get("weekdays", {})
    return {day: _ranges_to_slots(weekdays.get(day, [])) for day in WEEKDAY_KEYS}


def schedule_payload(schedule: dict, now: Optional[datetime] = None) -> dict:
    normalized = normalize_schedule_config(schedule)
    status = get_schedule_status(normalized, now=now)
    return {
        **normalized,
        "grid": build_schedule_grid(normalized),
        **status,
    }


def get_schedule_status(schedule: Optional[dict] = None, now: Optional[datetime] = None) -> dict:
    normalized = normalize_schedule_config(schedule or get_transcription_schedule_config())
    timezone_name = normalized["timezone"]
    tz = ZoneInfo(timezone_name)
    now_dt = now.astimezone(tz) if now else datetime.now(tz)
    grid = build_schedule_grid(normalized)
    day_key = str(now_dt.weekday())
    current_slot = (now_dt.hour * 60 + now_dt.minute) // SLOT_MINUTES
    current_slot = min(current_slot, SLOTS_PER_DAY - 1)
    is_allowed = bool(grid.get(day_key, [False] * SLOTS_PER_DAY)[current_slot])

    next_allowed_at = None
    if normalized["enabled"]:
        for offset in range(0, 7 * SLOTS_PER_DAY):
            candidate = now_dt + timedelta(minutes=offset * SLOT_MINUTES)
            candidate_day = str(candidate.weekday())
            candidate_slot = (candidate.hour * 60 + candidate.minute) // SLOT_MINUTES
            candidate_slot = min(candidate_slot, SLOTS_PER_DAY - 1)
            if grid.get(candidate_day, [False] * SLOTS_PER_DAY)[candidate_slot]:
                if offset > 0 or is_allowed:
                    next_allowed_at = candidate.replace(minute=(candidate.minute // SLOT_MINUTES) * SLOT_MINUTES,
                                                        second=0, microsecond=0)
                    break

    return {
        "server_time": now_dt.isoformat(),
        "timezone": timezone_name,
        "is_allowed_now": (not normalized["enabled"]) or is_allowed,
        "next_allowed_at": next_allowed_at.isoformat() if next_allowed_at else None,
    }


def can_process_task(task_type: str, schedule: Optional[dict] = None, now: Optional[datetime] = None) -> bool:
    normalized = normalize_schedule_config(schedule or get_transcription_schedule_config())
    if task_type not in normalized["apply_to_task_types"]:
        return True
    return get_schedule_status(normalized, now=now)["is_allowed_now"]


def activate_force_run(task_ids: List[str], forced_by: Optional[str] = None, now: Optional[datetime] = None) -> dict:
    unique_ids = [str(task_id) for task_id in dict.fromkeys(task_ids) if task_id]
    timestamp = (now or datetime.now()).isoformat()
    with _force_run_lock:
        _force_run_state["enabled"] = bool(unique_ids)
        _force_run_state["forced_task_ids"] = unique_ids
        _force_run_state["forced_at"] = timestamp if unique_ids else None
        _force_run_state["forced_by"] = forced_by if unique_ids else None
        return deepcopy(_force_run_state)


def clear_force_run() -> dict:
    with _force_run_lock:
        _force_run_state["enabled"] = False
        _force_run_state["forced_task_ids"] = []
        _force_run_state["forced_at"] = None
        _force_run_state["forced_by"] = None
        return deepcopy(_force_run_state)


def get_force_run_state() -> dict:
    with _force_run_lock:
        return deepcopy(_force_run_state)


def can_force_start_task(task) -> bool:
    if task is None:
        return False

    state = get_force_run_state()
    if not state.get("enabled"):
        return False

    task_id = getattr(task, "task_id", None)
    task_type = getattr(task, "task_type", "")
    return task_id in state.get("forced_task_ids", []) and task_type in DEFAULT_TASK_TYPES


def sync_force_run_with_tasks(tasks: List[dict]) -> dict:
    state = get_force_run_state()
    if not state.get("enabled"):
        return state

    active_task_ids = {
        str(task.get("task_id"))
        for task in tasks
        if task.get("status") in {"queued", "processing"}
    }
    remaining = [task_id for task_id in state.get("forced_task_ids", []) if task_id in active_task_ids]

    if remaining == state.get("forced_task_ids", []):
        return state

    if remaining:
        with _force_run_lock:
            _force_run_state["forced_task_ids"] = remaining
            return deepcopy(_force_run_state)

    return clear_force_run()


def sanitize_schedule_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Schedule payload must be an object.")

    timezone_name = str(payload.get("timezone", DEFAULT_TIMEZONE) or DEFAULT_TIMEZONE)
    ZoneInfo(timezone_name)

    weekdays = payload.get("weekdays")
    if not isinstance(weekdays, dict):
        raise ValueError("weekdays must be an object.")

    normalized_weekdays: Dict[str, List[str]] = {}
    for day in WEEKDAY_KEYS:
        slots = weekdays.get(day)
        if not isinstance(slots, list) or len(slots) != SLOTS_PER_DAY:
            raise ValueError(f"weekday {day} must contain exactly {SLOTS_PER_DAY} boolean slots.")
        bool_slots = [bool(slot) for slot in slots]
        normalized_weekdays[day] = _slots_to_ranges(bool_slots)

    enabled = bool(payload.get("enabled", True))

    task_types = payload.get("apply_to_task_types", list(DEFAULT_TASK_TYPES))
    if not isinstance(task_types, list):
        raise ValueError("apply_to_task_types must be a list.")
    cleaned_types = [task_type for task_type in task_types if task_type in DEFAULT_TASK_TYPES]
    if not cleaned_types:
        cleaned_types = list(DEFAULT_TASK_TYPES)

    return normalize_schedule_config({
        "enabled": enabled,
        "timezone": timezone_name,
        "slot_minutes": SLOT_MINUTES,
        "apply_to_task_types": cleaned_types,
        "weekdays": normalized_weekdays,
    })
