"""Shared yt-dlp network options."""

from src.config import get_config


def get_ytdlp_network_options() -> dict:
    """Prefer IPv4 on networks where unreachable IPv6 causes long stalls."""
    if get_config("YTDLP_FORCE_IPV4", True):
        return {"source_address": "0.0.0.0"}
    return {}
