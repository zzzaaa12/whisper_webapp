"""Diagnose slow yt-dlp metadata extraction without downloading media."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def _safe_url(value: object) -> str:
    """Remove query strings and fragments that may contain private tokens."""
    text = str(value or "")
    try:
        parts = urlsplit(text)
        if not parts.scheme:
            return text[:500]
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))[:500]
    except ValueError:
        return text[:500]


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=True), flush=True)


class DiagnosticLogger:
    def __init__(self, started_at: float) -> None:
        self.started_at = started_at

    def _log(self, level: str, message: object) -> None:
        _emit({
            "event": "yt_dlp_log",
            "level": level,
            "elapsed_ms": round((time.perf_counter() - self.started_at) * 1000),
            "message": str(message)[:1000],
        })

    def debug(self, message: object) -> None:
        self._log("debug", message)

    def warning(self, message: object) -> None:
        self._log("warning", message)

    def error(self, message: object) -> None:
        self._log("error", message)


def _run_child(url: str, client: str, socket_timeout: int) -> int:
    import yt_dlp

    started_at = time.perf_counter()
    options = {
        "quiet": True,
        "no_warnings": False,
        "skip_download": True,
        "retries": 1,
        "socket_timeout": socket_timeout,
        "logger": DiagnosticLogger(started_at),
    }
    if client != "default":
        options["extractor_args"] = {"youtube": {"player_client": [client]}}

    _emit({
        "event": "start",
        "client": client,
        "yt_dlp_version": yt_dlp.version.__version__,
        "socket_timeout_seconds": socket_timeout,
    })

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            original_urlopen = ydl.urlopen

            def timed_urlopen(request):
                request_url = getattr(request, "url", request)
                request_started_at = time.perf_counter()
                _emit({
                    "event": "http_start",
                    "elapsed_ms": round((request_started_at - started_at) * 1000),
                    "url": _safe_url(request_url),
                })
                try:
                    response = original_urlopen(request)
                    _emit({
                        "event": "http_end",
                        "elapsed_ms": round((time.perf_counter() - started_at) * 1000),
                        "duration_ms": round((time.perf_counter() - request_started_at) * 1000),
                        "status": getattr(response, "status", None),
                        "url": _safe_url(request_url),
                    })
                    return response
                except Exception as error:
                    _emit({
                        "event": "http_error",
                        "elapsed_ms": round((time.perf_counter() - started_at) * 1000),
                        "duration_ms": round((time.perf_counter() - request_started_at) * 1000),
                        "url": _safe_url(request_url),
                        "error": f"{type(error).__name__}: {error}"[:1000],
                    })
                    raise

            ydl.urlopen = timed_urlopen
            info = ydl.extract_info(url, download=False)

        _emit({
            "event": "complete",
            "status": "success",
            "elapsed_ms": round((time.perf_counter() - started_at) * 1000),
            "title": str(info.get("title", ""))[:500],
            "duration": info.get("duration"),
            "live_status": info.get("live_status"),
        })
        return 0
    except Exception as error:
        _emit({
            "event": "complete",
            "status": "error",
            "elapsed_ms": round((time.perf_counter() - started_at) * 1000),
            "error": f"{type(error).__name__}: {error}"[:2000],
        })
        return 1


def _run_parent(args: argparse.Namespace) -> int:
    output_path = Path(args.output) if args.output else None
    report = {
        "url": _safe_url(args.url),
        "overall_timeout_seconds": args.timeout,
        "socket_timeout_seconds": args.socket_timeout,
        "results": [],
    }

    for client in args.clients:
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--child",
            "--url",
            args.url,
            "--client",
            client,
            "--socket-timeout",
            str(args.socket_timeout),
        ]
        started_at = time.perf_counter()
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=args.timeout,
            )
            events = []
            for line in completed.stdout.splitlines():
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    events.append({"event": "unparsed_stdout", "message": line[:1000]})
            result = {
                "client": client,
                "status": "completed",
                "exit_code": completed.returncode,
                "elapsed_ms": round((time.perf_counter() - started_at) * 1000),
                "events": events,
                "stderr": completed.stderr[-2000:],
            }
        except subprocess.TimeoutExpired as error:
            stdout = error.stdout.decode("utf-8", "replace") if isinstance(error.stdout, bytes) else (error.stdout or "")
            events = []
            for line in stdout.splitlines():
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
            result = {
                "client": client,
                "status": "timeout",
                "elapsed_ms": round((time.perf_counter() - started_at) * 1000),
                "events": events,
            }

        report["results"].append(result)
        complete = next(
            (event for event in reversed(result["events"]) if event.get("event") == "complete"),
            None,
        )
        _emit({
            "client": client,
            "status": result["status"],
            "elapsed_ms": result["elapsed_ms"],
            "result": complete,
        })

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Report written to {output_path.resolve()}")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Video URL to inspect")
    parser.add_argument("--clients", nargs="+", default=["default", "android", "web"])
    parser.add_argument("--timeout", type=int, default=45, help="Overall timeout per client")
    parser.add_argument("--socket-timeout", type=int, default=15)
    parser.add_argument("--output", help="Optional JSON report path")
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--client", default="default", help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.child:
        return _run_child(args.url, args.client, args.socket_timeout)
    return _run_parent(args)


if __name__ == "__main__":
    raise SystemExit(main())
