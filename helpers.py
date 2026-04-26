"""Date/time helpers — NZ timezone, weekly windows, delivery cutoff."""
import hashlib
import hmac
import os
from datetime import datetime, date, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from db import get_setting


# ---------- order tracking tokens ----------

def _signing_key() -> bytes:
    # Stable per deployment; if FLASK_SECRET changes, old links break (acceptable).
    return (os.getenv("FLASK_SECRET") or "vya-default-secret").encode()


def make_order_token(order_id: int) -> str:
    """Short HMAC-based token so customers can revisit /order/<id>?t=<token>.

    16 hex chars = ~64 bits of entropy — plenty for "don't guess other orders"
    while keeping the link short enough to be SMS-safe.
    """
    mac = hmac.new(_signing_key(), str(order_id).encode(), hashlib.sha256)
    return mac.hexdigest()[:16]


def verify_order_token(order_id: int, token: str) -> bool:
    if not token:
        return False
    return hmac.compare_digest(make_order_token(order_id), token)


# ---------- public base URL (auto-detect from request, fallback to env) ----------

def current_base_url() -> str:
    """Best canonical base URL for emails / SMS links.

    Priority:
      1. Flask request context  → scheme + host the customer actually hit
         (handles localhost dev AND production transparently, including
         AWS ALB → http://EC2 with X-Forwarded-Proto=https)
      2. PUBLIC_BASE_URL env var
      3. Hardcoded localhost dev default
    """
    try:
        from flask import has_request_context, request
        if has_request_context():
            # X-Forwarded-Proto wins (AWS ALB / CloudFront set this); else
            # request.scheme reads it from ProxyFix or socket.
            scheme = request.headers.get("X-Forwarded-Proto") or request.scheme or "http"
            host = request.headers.get("X-Forwarded-Host") or request.host
            # Sanity: never return https://localhost — browsers won't trust it
            if host.startswith(("127.", "localhost", "0.0.0.0")):
                scheme = "http"
            return f"{scheme}://{host}".rstrip("/")
    except Exception:
        pass
    return os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

NZ = ZoneInfo("Pacific/Auckland")


def now_nz() -> datetime:
    return datetime.now(NZ)


def today_nz() -> date:
    return now_nz().date()


def week_start(d: date) -> date:
    """Monday of the week containing d (ISO)."""
    return d - timedelta(days=d.weekday())


def this_week_start() -> date:
    return week_start(today_nz())


def next_week_start() -> date:
    return this_week_start() + timedelta(days=7)


def closed_weekdays():
    """Set of int weekdays (0=Mon..6=Sun) the kitchen is closed."""
    raw = get_setting("closed_weekdays", "5")
    return {int(x) for x in raw.split(",") if x.strip()}


def cutoff_hour() -> int:
    return int(get_setting("cutoff_hour", "18"))


def next_delivery_date(now: Optional[datetime] = None) -> date:
    """Compute next available delivery date based on cutoff + closed days.

    Rule: if now < cutoff_hour, deliver tomorrow; else day-after.
    Skip any date that's a closed weekday.
    """
    n = now or now_nz()
    cut = cutoff_hour()
    base = n.date() + timedelta(days=1 if n.hour < cut else 2)
    closed = closed_weekdays()
    while base.weekday() in closed:
        base += timedelta(days=1)
    return base


def is_deliverable_date(d: date) -> bool:
    return d.weekday() not in closed_weekdays() and d >= next_delivery_date()


def date_label(d: date, lang: str = "zh") -> str:
    if lang == "zh":
        wk = "一二三四五六日"[d.weekday()]
        return f"{d.strftime('%Y-%m-%d')}（周{wk}）"
    return d.strftime("%a, %d %b %Y")
