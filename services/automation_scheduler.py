#!/usr/bin/env python3
"""Automation scheduler: manages the weekly schedule scan and daily morning automation.

The scheduler runs as a background asyncio task within the FastAPI process.
It uses a simple polling loop rather than an external scheduler dependency.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Defaults — overridable via env vars
_DEFAULT_MORNING_HOUR = 7       # 07:00 Pacific
_DEFAULT_SCAN_HOUR = 3          # 03:00 Pacific (weekly scan)
_DEFAULT_SCAN_WEEKDAY = 0       # Monday
_DEFAULT_TZ_OFFSET = -7         # Pacific time
_POLL_INTERVAL_SECONDS = 300    # Check every 5 minutes


class AutomationScheduler:
    """Lightweight asyncio-based scheduler for race-card automation."""

    def __init__(self, tracks: Dict[str, Dict[str, str]]):
        self.tracks = tracks
        self.tz_offset = int(os.getenv("RACE_TZ_OFFSET_HOURS", str(_DEFAULT_TZ_OFFSET)))
        self.morning_hour = int(os.getenv("AUTOMATION_MORNING_HOUR", str(_DEFAULT_MORNING_HOUR)))
        self.scan_hour = int(os.getenv("AUTOMATION_SCAN_HOUR", str(_DEFAULT_SCAN_HOUR)))
        self.scan_weekday = int(os.getenv("AUTOMATION_SCAN_WEEKDAY", str(_DEFAULT_SCAN_WEEKDAY)))

        # Cached schedule from the most recent scan
        self._schedule: Dict[str, List[str]] = {}
        self._last_scan_date: Optional[str] = None
        self._last_morning_run_date: Optional[str] = None

        self._task: Optional[asyncio.Task] = None
        self._stopping = False

    # ── Public API ───────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the scheduler background loop."""
        token = os.getenv("TRACKSTAR_AUTOMATION_TOKEN", "")
        if not token:
            logger.info("⏸ Automation scheduler disabled — TRACKSTAR_AUTOMATION_TOKEN not set")
            return
        self._stopping = False
        self._task = asyncio.create_task(self._run_loop(), name="automation-scheduler")
        logger.info(
            "🚀 Automation scheduler started — morning=%02d:00, scan=%s@%02d:00 (UTC%+d)",
            self.morning_hour,
            ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][self.scan_weekday],
            self.scan_hour,
            self.tz_offset,
        )

    async def stop(self) -> None:
        """Gracefully stop the scheduler."""
        self._stopping = True
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Automation scheduler stopped")

    # ── Internal loop ────────────────────────────────────────────────────────

    async def _run_loop(self) -> None:
        # Run an initial schedule scan on startup
        await self._do_schedule_scan()

        while not self._stopping:
            try:
                await asyncio.sleep(_POLL_INTERVAL_SECONDS)
                now = self._now()
                today_str = now.strftime("%Y-%m-%d")

                # Weekly schedule scan
                if (
                    now.weekday() == self.scan_weekday
                    and now.hour == self.scan_hour
                    and self._last_scan_date != today_str
                ):
                    await self._do_schedule_scan()
                    self._last_scan_date = today_str

                # Daily morning automation
                if (
                    now.hour >= self.morning_hour
                    and self._last_morning_run_date != today_str
                ):
                    await self._do_morning_run()
                    self._last_morning_run_date = today_str

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Scheduler loop error (will retry): %s", exc, exc_info=True)
                await asyncio.sleep(60)  # Back off on unexpected errors

    async def _do_schedule_scan(self) -> None:
        logger.info("🔍 Running scheduled Equibase scan …")
        try:
            from services.schedule_scanner import scan_upcoming_race_dates

            self._schedule = await asyncio.to_thread(
                scan_upcoming_race_dates,
                self.tracks,
                tz_offset_hours=self.tz_offset,
            )
            self._last_scan_date = self._now().strftime("%Y-%m-%d")
        except Exception as exc:
            logger.error("Schedule scan failed: %s", exc, exc_info=True)

    async def _do_morning_run(self) -> None:
        logger.info("☀️ Running morning automation …")
        try:
            from services.morning_automation import run_morning_automation

            # Re-scan today in case schedule is stale
            if not self._schedule:
                await self._do_schedule_scan()

            await run_morning_automation(
                self.tracks,
                self._schedule,
                tz_offset_hours=self.tz_offset,
            )
        except Exception as exc:
            logger.error("Morning automation failed: %s", exc, exc_info=True)

    def _now(self) -> datetime:
        return datetime.now(timezone(timedelta(hours=self.tz_offset)))

