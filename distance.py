"""Distance + min-order calculation.

Strategy:
  - Compute driving distance from kitchen origin → customer address.
  - Map distance to a min-order quantity using the `delivery_buckets` setting
    (format: "km_max:min_qty,km_max:min_qty,...").
  - If GOOGLE_MAPS_API_KEY is missing, return a "needs_manual_pick" response
    so the frontend can fall back to a region radio.
"""
import os
from dataclasses import dataclass
from typing import Optional

from db import get_setting

KITCHEN_ORIGIN = os.getenv(
    "KITCHEN_ADDRESS",
    "Laurina Road, Sunnynook, Auckland 0620, New Zealand",
)


@dataclass
class Quote:
    deliverable: bool
    distance_km: Optional[float]
    min_qty: Optional[int]
    bucket_label: Optional[str]   # e.g. "≤ 6 km"
    error: Optional[str]
    fallback: bool                # True if maps key missing → frontend picks region


def parse_buckets(raw: Optional[str] = None):
    """Returns list of (km_max, min_qty), sorted by km_max asc."""
    raw = raw or get_setting("delivery_buckets", "6:10,12:20,20:30,30:40")
    out = []
    for part in raw.split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        km, qty = part.split(":", 1)
        try:
            out.append((float(km), int(qty)))
        except ValueError:
            continue
    out.sort(key=lambda x: x[0])
    return out


def bucket_for_km(km: float):
    buckets = parse_buckets()
    max_km = float(get_setting("max_delivery_km", "30"))
    if km > max_km:
        return None, None
    prev_km = 0.0
    for km_max, qty in buckets:
        if km <= km_max:
            label = f"≤ {km_max:g} km" if prev_km == 0 else f"{prev_km:g}–{km_max:g} km"
            return qty, label
        prev_km = km_max
    return None, None


def quote_by_km(km: float) -> Quote:
    qty, label = bucket_for_km(km)
    if qty is None:
        return Quote(
            deliverable=False, distance_km=km, min_qty=None,
            bucket_label=None,
            error=f"超出配送范围({km:.1f} km > {get_setting('max_delivery_km', '30')} km)",
            fallback=False,
        )
    return Quote(
        deliverable=True, distance_km=km, min_qty=qty,
        bucket_label=label, error=None, fallback=False,
    )


def quote_by_address(address: str) -> Quote:
    """Resolve address → driving km via Google Maps, then bucket.

    Returns a fallback Quote if the maps key is missing — the frontend should
    show a region-picker UI in that case.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
    if not api_key:
        return Quote(
            deliverable=False, distance_km=None, min_qty=None,
            bucket_label=None,
            error="GOOGLE_MAPS_API_KEY not set — please pick your region manually.",
            fallback=True,
        )

    address = (address or "").strip()
    if not address:
        return Quote(
            deliverable=False, distance_km=None, min_qty=None,
            bucket_label=None, error="Address required.", fallback=False,
        )

    try:
        import googlemaps
    except ImportError:
        return Quote(
            deliverable=False, distance_km=None, min_qty=None,
            bucket_label=None, error="googlemaps library not installed.",
            fallback=True,
        )

    try:
        gmaps = googlemaps.Client(key=api_key)
        result = gmaps.distance_matrix(
            origins=[KITCHEN_ORIGIN],
            destinations=[address],
            mode="driving",
            units="metric",
            region="nz",
        )
        elem = result["rows"][0]["elements"][0]
        if elem.get("status") != "OK":
            return Quote(
                deliverable=False, distance_km=None, min_qty=None,
                bucket_label=None,
                error=f"地址无法识别 / Unrecognised address ({elem.get('status')}).",
                fallback=False,
            )
        meters = elem["distance"]["value"]
        km = round(meters / 1000.0, 2)
        return quote_by_km(km)
    except Exception as e:
        return Quote(
            deliverable=False, distance_km=None, min_qty=None,
            bucket_label=None,
            error=f"Distance lookup failed: {e}", fallback=True,
        )


def quote_by_region(region: str) -> Quote:
    """Manual fallback: customer picks a region label.

    Returns the region's min_qty as if at the upper edge of that bucket.
    """
    buckets = parse_buckets()
    region_to_idx = {  # north shore = bucket[0], etc.
        "north_shore": 0, "central": 1, "west": 2, "east": 3,
    }
    idx = region_to_idx.get(region)
    if idx is None or idx >= len(buckets):
        return Quote(
            deliverable=False, distance_km=None, min_qty=None,
            bucket_label=None, error="未知区域 / Unknown region.", fallback=False,
        )
    km_max, qty = buckets[idx]
    return Quote(
        deliverable=True, distance_km=km_max, min_qty=qty,
        bucket_label=f"≤ {km_max:g} km", error=None, fallback=False,
    )
