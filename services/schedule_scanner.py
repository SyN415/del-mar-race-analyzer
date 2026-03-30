#!/usr/bin/env python3
"""Schedule scanner: probes Equibase to discover upcoming race dates for configured tracks."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from services.race_card_admin import (
    build_equibase_card_overview_url,
)
from urllib import request as urllib_request

logger = logging.getLogger(__name__)

# How many days ahead to scan for race activity
SCAN_HORIZON_DAYS = 7


def _probe_equibase_has_entries(track_id: str, race_date: str, country: str = "USA") -> bool:
    """Return True if Equibase has an entry page for the given track/date.

    A successful HTTP 200 with meaningful HTML (contains race-related tokens)
    indicates entries are posted — i.e. there is racing scheduled.
    """
    url = build_equibase_card_overview_url(track_id, race_date, country=country)
    req = urllib_request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
        },
    )
    try:
        with urllib_request.urlopen(req, timeout=15) as resp:
            if resp.status != 200:
                return False
            html = resp.read().decode("utf-8", errors="ignore")
            # Equibase returns a generic page even for dates without racing;
            # real entry pages contain race-number links or runner rows.
            if len(html) < 500:
                return False
            # Look for signs of actual entries
            lower = html.lower()
            has_entries = (
                "race " in lower
                or "entries" in lower
                or "onvsaddclick" in lower
                or "post position" in lower
                or "jockey" in lower
            )
            return has_entries
    except Exception as exc:
        logger.debug("Equibase probe failed for %s on %s: %s", track_id, race_date, exc)
        return False


def scan_upcoming_race_dates(
    tracks: Dict[str, Dict[str, str]],
    horizon_days: int = SCAN_HORIZON_DAYS,
    tz_offset_hours: int = -7,
) -> Dict[str, List[str]]:
    """Scan Equibase for each configured track and return {track_id: [race_date, ...]}.

    Parameters
    ----------
    tracks : dict
        ``TRACK_CONFIG_FULL``-style mapping ``{track_id: {"name": ..., "country": ...}}``.
    horizon_days : int
        Number of days ahead to probe (default 7).
    tz_offset_hours : int
        UTC offset for determining "today" (default -7 for Pacific).

    Returns
    -------
    dict
        ``{track_id: ["YYYY-MM-DD", ...]}`` — only tracks with at least one
        scheduled date are included.
    """
    tz = timezone(timedelta(hours=tz_offset_hours))
    today = datetime.now(tz).date()

    schedule: Dict[str, List[str]] = {}
    for track_id, cfg in tracks.items():
        country = cfg.get("country", "USA")
        track_dates: List[str] = []
        for offset in range(horizon_days):
            probe_date = today + timedelta(days=offset)
            date_str = probe_date.strftime("%Y-%m-%d")
            if _probe_equibase_has_entries(track_id, date_str, country=country):
                track_dates.append(date_str)
                logger.info("📅 %s has entries on %s", track_id, date_str)
            else:
                logger.debug("   %s — no entries on %s", track_id, date_str)
        if track_dates:
            schedule[track_id] = track_dates

    logger.info(
        "Schedule scan complete: %d track(s) with upcoming races — %s",
        len(schedule),
        {tid: dates for tid, dates in schedule.items()},
    )
    return schedule

