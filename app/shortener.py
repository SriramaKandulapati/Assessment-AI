import re
import secrets
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

from app.storage import connect, now_iso

ALIAS_RE = re.compile(r"^[A-Za-z0-9_-]{3,32}$")


class ShortenerError(Exception):
    def __init__(self, status_code, code, message):
        self.status_code, self.code, self.message = status_code, code, message


def normalize_url(raw):
    if len(raw) > 2048:
        raise ShortenerError(422, "invalid_url", "URL must be at most 2048 characters")
    try:
        parsed = urlsplit(raw.strip())
        if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
            raise ValueError()
        if parsed.username or parsed.password:
            raise ValueError()
        _ = parsed.port
    except ValueError:
        raise ShortenerError(422, "invalid_url", "Provide an absolute HTTP(S) URL without embedded credentials")
    return urlunsplit((parsed.scheme.lower(), parsed.netloc, parsed.path or "/", parsed.query, parsed.fragment))


def create_link(target_url, alias=None, expires_at=None):
    target_url = normalize_url(target_url)
    if expires_at:
        try:
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if expiry.tzinfo is None:
                raise ValueError()
            if expiry <= datetime.now(timezone.utc):
                raise ValueError()
        except ValueError:
            raise ShortenerError(422, "invalid_expiry", "expires_at must be a future ISO 8601 timestamp with timezone")
    if alias is not None and not ALIAS_RE.fullmatch(alias):
        raise ShortenerError(422, "invalid_alias", "Alias must be 3-32 letters, numbers, underscores, or hyphens")
    with connect() as db:
        for _ in range(5):
            code = alias or secrets.token_urlsafe(6).replace("-", "a").replace("_", "b")[:8]
            try:
                db.execute("INSERT INTO links(code,target_url,created_at,expires_at) VALUES(?,?,?,?)",
                           (code, target_url, now_iso(), expires_at))
                break
            except Exception as exc:
                if alias or "UNIQUE" not in str(exc):
                    if "UNIQUE" in str(exc):
                        raise ShortenerError(409, "alias_taken", "That alias is already in use")
                    raise
        else:
            raise ShortenerError(503, "code_generation_failed", "Could not allocate a short code")
        row = db.execute("SELECT * FROM links WHERE code=?", (code,)).fetchone()
    return dict(row)


def resolve_link(code):
    with connect() as db:
        row = db.execute("SELECT * FROM links WHERE code=?", (code,)).fetchone()
        if not row:
            raise ShortenerError(404, "link_not_found", "Short link does not exist")
        if row["disabled"]:
            raise ShortenerError(410, "link_disabled", "Short link is disabled")
        if row["expires_at"] and datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00")) <= datetime.now(timezone.utc):
            raise ShortenerError(410, "link_expired", "Short link has expired")
        db.execute("INSERT INTO clicks(code,clicked_at) VALUES(?,?)", (code, now_iso()))
    return row["target_url"]


def disable_link(code):
    with connect() as db:
        cursor = db.execute("UPDATE links SET disabled=1 WHERE code=?", (code,))
        if cursor.rowcount == 0:
            raise ShortenerError(404, "link_not_found", "Short link does not exist")
        return {"code": code, "disabled": True}


def link_analytics(code, bucket="day"):
    if bucket not in ("hour", "day"):
        raise ShortenerError(422, "invalid_bucket", "bucket must be hour or day")
    fmt = "%Y-%m-%dT%H" if bucket == "hour" else "%Y-%m-%d"
    with connect() as db:
        if not db.execute("SELECT 1 FROM links WHERE code=?", (code,)).fetchone():
            raise ShortenerError(404, "link_not_found", "Short link does not exist")
        total = db.execute("SELECT COUNT(*) FROM clicks WHERE code=?", (code,)).fetchone()[0]
        rows = db.execute("SELECT clicked_at FROM clicks WHERE code=? ORDER BY clicked_at", (code,)).fetchall()
    counts = {}
    for row in rows:
        key = datetime.fromisoformat(row[0]).strftime(fmt)
        counts[key] = counts.get(key, 0) + 1
    return {"code": code, "total_clicks": total, "bucket": bucket,
            "series": [{"period": k, "clicks": v} for k, v in sorted(counts.items())]}
