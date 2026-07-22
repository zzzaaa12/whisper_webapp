# API Contract v1

This document freezes the existing HTTP and Socket.IO interface while the `/v2`
web interface is developed. Existing paths, methods, request encodings, field
names, status codes, and response envelopes must remain backward compatible.

## Compatibility rules

- `/v2` is a web-page namespace, not a replacement API namespace.
- Existing `/api/*`, `/download/*`, and Socket.IO contracts remain available.
- Additive response fields are allowed. Existing fields may not be removed,
  renamed, or assigned a different meaning.
- Existing JSON, form, and multipart request encodings may not be changed.
- New incompatible APIs must use a new path and may not replace v1 routes.
- The legacy `{status, message}` and standard `{success, message}` envelopes are
  both intentional and must not be consolidated in place.

## Known external-device contract

The repository client in `app/model.py` uses these interfaces.

| Method | Path | Encoding | Required input | Success contract |
| --- | --- | --- | --- | --- |
| GET | `/api/queue/status` | query | none | JSON with `success: true`, `status`, `force_start` |
| POST | `/api/process` | JSON | `youtube_url` or `audio_url`; `access_code` when session auth is unavailable | legacy JSON with `status`, `message`, and normally `task_id`, `queue_position` |
| POST | `/api/verify_access_code` | form | `access_code` | JSON with `success`, `message` |
| POST | `/api/upload_media` | multipart | file field `media_file`; form field `access_code` when required | JSON with `success` plus upload/task result fields |
| POST | `/api/upload_subtitle` | JSON | `filename`, `content`, `access_code`; optional `task_id` | JSON with `success`; on success `filename`, `path`, `size` |

### `/api/process` optional input

- `auto`: integer-compatible flag; processing is automatic when equal to `1`.
- `title`: caller-provided title.
- `uploader`: caller-provided channel/uploader.

The endpoint returns HTTP 200 with `status: "processing"` when queued. It may
also return HTTP 200 with `status: "completed"` when an existing summary is
found. Errors use `status: "error"` and an appropriate 4xx/5xx status.

## HTTP route inventory

### Submission and authentication

| Method | Path |
| --- | --- |
| POST | `/api/process` |
| POST | `/api/process2` |
| POST | `/api/queue/add` |
| POST | `/api/upload_media` |
| POST | `/api/upload_subtitle` |
| POST | `/api/verify_access_code` |

### Queue

| Method | Path |
| --- | --- |
| GET | `/api/queue/status` |
| GET | `/api/queue/list` |
| GET | `/api/queue/task/<task_id>` |
| POST | `/api/queue/cancel` |
| POST | `/api/queue/cleanup` |
| POST | `/api/queue/delete` |
| POST | `/api/queue/delete-batch` |
| POST | `/api/queue/restart` |
| POST | `/api/queue/force-start` |

### Summaries and bookmarks

| Method | Path |
| --- | --- |
| POST | `/api/summaries/list` |
| POST | `/api/last_5_summary` |
| POST | `/api/get_summary` |
| POST | `/api/delete` |
| POST | `/api/batch-delete` |
| POST | `/api/bookmark` |
| POST | `/api/batch-bookmark` |
| POST | `/api/bookmarks/add` |
| POST | `/api/bookmarks/remove` |
| GET | `/api/bookmarks/list` |
| GET | `/api/bookmarks/check/<filename>` |

### Trash

| Method | Path |
| --- | --- |
| POST | `/api/trash/move` |
| POST | `/api/trash/restore` |
| POST | `/api/trash/delete` |
| GET | `/api/trash/list` |

### System

| Method | Path |
| --- | --- |
| GET | `/api/health` |
| GET | `/api/system/status` |
| GET | `/api/system/config-status` |
| GET | `/api/system/transcription-schedule` |
| POST | `/api/system/transcription-schedule` |
| POST | `/api/client-diagnostics` |

### File download

| Method | Path |
| --- | --- |
| GET | `/download/summary/<filename>` |
| GET | `/download/subtitle/<filename>` |

`search_tool/server.py` separately exposes `POST /api/search`; it is not part of
the main Flask application's blueprint.

## Standard response envelope

Most APIs use:

```json
{"success": true, "message": "...", "additional_fields": "..."}
```

Errors normally use:

```json
{"success": false, "message": "...", "error_code": "optional"}
```

Validation, authentication, missing data, conflict, large payload, and server
errors currently map to HTTP 400, 401, 404, 409, 413, and 500 respectively.

## Socket.IO contract

### Client to server

| Event | Payload |
| --- | --- |
| `start_processing` | object containing `audio_url` and `access_code` |
| `cancel_processing` | no required payload |
| `clear_logs` | no required payload |
| `request_gpu_status` | no required payload |

### Server to client

| Event | Payload |
| --- | --- |
| `update_log` | `{log, type}` |
| `task_log` | `{task_id, log, type}` |
| `server_status_update` | `{is_busy, current_task}` |
| `gpu_status_update` | existing GPU status object |
| `processing_finished` | object, currently empty |
| `access_code_error` | `{message}` |

## `/v2` consumption policy

The `/v2` JavaScript API adapter may normalize responses internally, but that
normalization must stay in the browser. It must not change server responses.
The v2 Socket.IO adapter follows the same rule.

