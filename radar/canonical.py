"""URL canonicalization and item ids."""

import hashlib
from urllib.parse import parse_qsl, urlsplit, urlunsplit

TRACKING_PARAMS = {"fbclid", "gclid", "ref", "source"}
YOUTUBE_HOSTS = {"youtube.com", "m.youtube.com"}


def _youtube_video_id(host: str, path: str, query: list[tuple[str, str]]) -> str | None:
    """Return the video id if the URL points to a single YouTube video."""
    if host == "youtu.be":
        return path.strip("/") or None
    if host in YOUTUBE_HOSTS:
        if path.startswith("/shorts/"):
            return path.removeprefix("/shorts/").strip("/") or None
        if path == "/watch":
            return dict(query).get("v")
    return None


def canonicalize(url: str) -> str:
    """Normalize a URL so the same content always maps to the same string."""
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = parts.netloc.lower().removeprefix("www.")
    query = parse_qsl(parts.query, keep_blank_values=True)

    video_id = _youtube_video_id(host, parts.path, query)
    if video_id:
        return f"https://youtube.com/watch?v={video_id}"

    # Filter the raw "key=value" segments so the remaining params keep their original encoding.
    kept = [p for p in parts.query.split("&") if p and not _is_tracking(p.split("=", 1)[0])]
    path = parts.path.rstrip("/")
    return urlunsplit((scheme, host, path, "&".join(kept), ""))


def _is_tracking(key: str) -> bool:
    """True for tracking query params that never change the content."""
    key = key.lower()
    return key.startswith("utm_") or key in TRACKING_PARAMS


def item_id(canonical_url: str) -> str:
    """First 12 hex chars of sha1(canonical_url)."""
    return hashlib.sha1(canonical_url.encode("utf-8")).hexdigest()[:12]
