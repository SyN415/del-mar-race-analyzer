#!/usr/bin/env python3
"""Morning automation: runs the full race-card workflow for each track with races today."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from starlette.requests import Request as StarletteRequest
from starlette.datastructures import Headers

logger = logging.getLogger(__name__)


def _make_automation_request() -> StarletteRequest:
    """Build a fake Starlette Request carrying the automation bearer token."""
    token = os.getenv("TRACKSTAR_AUTOMATION_TOKEN", "")
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "query_string": b"",
        "headers": [
            (b"authorization", f"Bearer {token}".encode()),
            (b"content-type", b"application/json"),
        ],
    }
    return StarletteRequest(scope)


async def run_track_workflow(
    track_id: str,
    race_date: str,
    *,
    app_module: Any,
) -> bool:
    """Execute the full 4-step admin workflow for one track/date.

    Returns True on success, False on failure.
    """
    from app import (
        AdminRaceCardRequest,
        AdminDeepDiveRequest,
        AutoCurateRequest,
        CuratedCardRequest,
        create_admin_race_card,
        admin_race_deep_dive,
        auto_curate_card,
        save_curated_card,
        app_state,
    )

    http_request = _make_automation_request()
    log_prefix = f"[AUTO {track_id} {race_date}]"

    # ── Step 1: Build the race card ──────────────────────────────────────────
    logger.info("%s Step 1/4 — building race card …", log_prefix)
    t0 = time.perf_counter()
    try:
        card_req = AdminRaceCardRequest(
            race_date=race_date,
            track_id=track_id,
            source_mode="web_search",
        )
        card_resp = await create_admin_race_card(card_req, http_request=http_request)
        card_body = card_resp.body
        import json
        card_data = json.loads(card_body)
        session_id = card_data["session_id"]
        logger.info("%s   race card built — session=%s (%.1fs)", log_prefix, session_id, time.perf_counter() - t0)
    except Exception as exc:
        logger.error("%s   FAILED at step 1 (race card): %s", log_prefix, exc, exc_info=True)
        return False

    # ── Step 2: Deep-dive each race ──────────────────────────────────────────
    logger.info("%s Step 2/4 — deep-diving races …", log_prefix)
    session_manager = await app_state.ensure_session_manager()
    if not session_manager:
        logger.error("%s   session manager unavailable", log_prefix)
        return False

    results = await session_manager.get_session_results(session_id)
    race_analyses = results.get("race_analyses", [])
    race_numbers = sorted({r.get("race_number", 0) for r in race_analyses if r.get("race_number")})
    logger.info("%s   found %d races: %s", log_prefix, len(race_numbers), race_numbers)

    for rn in race_numbers:
        try:
            dd_req = AdminDeepDiveRequest(
                session_id=session_id,
                race_number=rn,
                race_date=race_date,
                track_id=track_id,
            )
            await admin_race_deep_dive(dd_req, http_request=http_request)
            logger.info("%s   deep-dive race %d complete", log_prefix, rn)
        except Exception as exc:
            logger.warning("%s   deep-dive race %d failed (continuing): %s", log_prefix, rn, exc)

    # ── Step 3: Auto-curate the full card ────────────────────────────────────
    logger.info("%s Step 3/4 — auto-curating …", log_prefix)
    try:
        curate_req = AutoCurateRequest(
            session_id=session_id,
            race_date=race_date,
            track_id=track_id,
        )
        curate_resp = await auto_curate_card(curate_req, http_request=http_request)
        curate_data = json.loads(curate_resp.body)
        logger.info("%s   auto-curate complete — %d races curated", log_prefix, len(curate_data.get("races", [])))
    except Exception as exc:
        logger.error("%s   FAILED at step 3 (auto-curate): %s", log_prefix, exc, exc_info=True)
        return False

    # ── Step 4: Save and publish ─────────────────────────────────────────────
    logger.info("%s Step 4/4 — saving & publishing …", log_prefix)
    try:
        races_payload = curate_data.get("races", [])
        card_overview = curate_data.get("card_overview", "")

        # Build top-level picks from the first curated race (if available)
        first_race = races_payload[0] if races_payload else {}
        horse_names_by_race = curate_data.get("horse_names_by_race", {})

        publish_req = CuratedCardRequest(
            race_date=race_date,
            track_id=track_id,
            session_id=session_id,
            top_pick={"horse_name": first_race.get("top_pick", ""), "race_number": first_race.get("race_number", 1)} if first_race.get("top_pick") else None,
            value_play={"horse_name": first_race.get("value_play", ""), "race_number": first_race.get("race_number", 1)} if first_race.get("value_play") else None,
            longshot={"horse_name": first_race.get("longshot", ""), "race_number": first_race.get("race_number", 1)} if first_race.get("longshot") else None,
            admin_notes="Auto-generated by TrackStarAI morning automation",
            betting_strategy=first_race.get("betting_strategy", ""),
            is_published=True,
            races=races_payload,
            card_overview=card_overview,
        )
        await save_curated_card(publish_req, http_request=http_request)
        elapsed = time.perf_counter() - t0
        logger.info("%s ✅ Published successfully (total %.1fs)", log_prefix, elapsed)
        return True
    except Exception as exc:
        logger.error("%s   FAILED at step 4 (publish): %s", log_prefix, exc, exc_info=True)
        return False


async def run_morning_automation(
    tracks: Dict[str, Dict[str, str]],
    schedule: Dict[str, List[str]],
    tz_offset_hours: int = -7,
) -> Dict[str, str]:
    """Run the full workflow for every track that has races today.

    Parameters
    ----------
    tracks : dict
        ``TRACK_CONFIG_FULL``-style mapping.
    schedule : dict
        ``{track_id: ["YYYY-MM-DD", ...]}`` from ``scan_upcoming_race_dates``.
    tz_offset_hours : int
        UTC offset for "today" (default -7 Pacific).

    Returns
    -------
    dict
        ``{track_id: "ok" | "skipped" | "error:<msg>"}``
    """
    import app as app_module

    tz = timezone(timedelta(hours=tz_offset_hours))
    today_str = datetime.now(tz).strftime("%Y-%m-%d")
    results: Dict[str, str] = {}

    for track_id in tracks:
        track_dates = schedule.get(track_id, [])
        if today_str not in track_dates:
            logger.info("⏭ %s — no races today (%s)", track_id, today_str)
            results[track_id] = "skipped"
            continue

        # Idempotency: skip if a published curated card already exists
        session_manager = await app_module.app_state.ensure_session_manager()
        if session_manager:
            existing = await session_manager.get_curated_card(today_str, track_id)
            if existing and existing.get("is_published"):
                logger.info("⏭ %s — curated card already published for %s", track_id, today_str)
                results[track_id] = "skipped"
                continue

        ok = await run_track_workflow(track_id, today_str, app_module=app_module)
        results[track_id] = "ok" if ok else "error"

    logger.info("🏁 Morning automation complete: %s", results)
    return results

