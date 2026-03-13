#!/usr/bin/env python3
"""Helpers for admin-created race card payloads and dashboard summaries."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def extract_json_object(response_text: str) -> Dict[str, Any]:
    """Extract a JSON object from raw model output."""
    text = (response_text or "").strip()
    if not text:
        raise ValueError("OpenRouter returned an empty response")

    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()

    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass

    json_match = re.search(r"\{.*\}", text, re.DOTALL)
    if json_match:
        payload = json.loads(json_match.group(0))
        if isinstance(payload, dict):
            return payload

    raise ValueError("OpenRouter response did not contain a valid JSON object")


def normalize_admin_results(
    structured_card: Dict[str, Any],
    *,
    race_date: str,
    track_id: str,
    llm_model: str,
    source_urls: Optional[List[str]] = None,
    admin_notes: str = "",
    analysis_duration_seconds: float = 0.0,
) -> Dict[str, Any]:
    """Normalize admin-created card data into the existing results contract."""
    raw_races = structured_card.get("race_analyses") or structured_card.get("races") or []
    race_analyses: List[Dict[str, Any]] = []

    for index, race in enumerate(raw_races, start=1):
        predictions = _normalize_predictions(
            race.get("predictions") or race.get("entries") or race.get("horses") or []
        )
        if not predictions:
            continue

        race_analysis = {
            "race_number": _to_int(race.get("race_number") or race.get("number"), index),
            "race_type": race.get("race_type") or race.get("type") or "",
            "distance": race.get("distance") or "",
            "surface": race.get("surface") or "",
            "predictions": predictions,
            "top_pick": predictions[0],
            "exotic_suggestions": race.get("exotic_suggestions") if isinstance(race.get("exotic_suggestions"), dict) else {},
        }
        race_analyses.append(race_analysis)

    if not race_analyses:
        raise ValueError("No race analyses with predictions were found in the model response")

    summary = summarize_race_analyses(race_analyses)
    generated_at = datetime.now(timezone.utc).isoformat()

    return {
        "race_date": race_date,
        "track_id": track_id,
        "generated_at": generated_at,
        "analysis_duration_seconds": round(float(analysis_duration_seconds or 0.0), 2),
        "race_analyses": race_analyses,
        "summary": summary,
        "card_overview": structured_card.get("card_overview") or structured_card.get("overview") or "",
        "source_urls": source_urls or [],
        "admin_metadata": {
            "workflow": "admin_openrouter",
            "model_used": llm_model,
            "notes": admin_notes.strip(),
            "source_urls": source_urls or [],
            "created_at": generated_at,
        },
        "ai_services_used": {
            "openrouter_client": True,
            "scraping_assistant": False,
            "analysis_enhancer": False,
        },
    }


def summarize_race_analyses(race_analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Create a results.html-compatible summary from normalized race analyses."""
    total_races = len(race_analyses)
    total_horses = sum(len(race.get("predictions", [])) for race in race_analyses)

    best_bets = []
    top_pick_probabilities = []
    for race in race_analyses:
        top_pick = race.get("top_pick") or (race.get("predictions") or [None])[0]
        if top_pick:
            best_bets.append({**top_pick, "race_number": race.get("race_number")})
            top_pick_probabilities.append(float(top_pick.get("win_probability") or 0.0) / 100)

    best_bets.sort(key=lambda item: item.get("composite_rating") or 0.0, reverse=True)
    average_confidence = sum(top_pick_probabilities) / len(top_pick_probabilities) if top_pick_probabilities else 0.0

    return {
        "total_races": total_races,
        "successful_races": total_races,
        "total_horses": total_horses,
        "best_bets": best_bets[:3],
        "success_rate": 100 if total_races else 0,
        "ai_enhanced_races": total_races,
        "ai_enhancement_rate": 100 if total_races else 0,
        "average_confidence": round(average_confidence, 3),
        "betting_recommendations": {},
    }


def _normalize_predictions(raw_predictions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []

    for rank, prediction in enumerate(raw_predictions, start=1):
        horse_name = prediction.get("horse_name") or prediction.get("name") or prediction.get("horse")
        if not horse_name:
            continue

        composite_rating = _to_float(
            prediction.get("composite_rating") or prediction.get("rating") or prediction.get("confidence_score"),
            default=max(1.0, 100.0 - rank),
        )
        factors = _normalize_factors(prediction.get("factors"))

        normalized.append({
            "horse_name": str(horse_name).strip(),
            "post_position": prediction.get("post_position") or prediction.get("post") or prediction.get("program_number"),
            "jockey": prediction.get("jockey") or "",
            "trainer": prediction.get("trainer") or "",
            "composite_rating": round(composite_rating, 1),
            "win_probability": 0.0,
            "factors": factors,
            "notes": prediction.get("notes") or prediction.get("analysis") or "",
        })

    normalized.sort(key=lambda item: item["composite_rating"], reverse=True)
    total_rating = sum(item["composite_rating"] for item in normalized) or 1.0
    for item in normalized:
        item["win_probability"] = round((item["composite_rating"] / total_rating) * 100, 1)

    return normalized


def _normalize_factors(factors: Any) -> Optional[Dict[str, float]]:
    if not isinstance(factors, dict):
        return None

    normalized = {
        "speed_rating": round(_to_float(factors.get("speed_rating") or factors.get("speed")), 1),
        "form_rating": round(_to_float(factors.get("form_rating") or factors.get("form")), 1),
        "class_rating": round(_to_float(factors.get("class_rating") or factors.get("class")), 1),
        "workout_rating": round(_to_float(factors.get("workout_rating") or factors.get("workout")), 1),
    }
    return normalized if any(value > 0 for value in normalized.values()) else None


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default