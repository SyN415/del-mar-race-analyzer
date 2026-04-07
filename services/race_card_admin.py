#!/usr/bin/env python3
"""Helpers for admin-created race card payloads and dashboard summaries."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib import request as urllib_request


class AdminRaceCardJSONError(ValueError):
    """Raised when admin race-card structured output cannot be parsed safely."""

    def __init__(
        self,
        public_message: str,
        *,
        diagnostic_message: Optional[str] = None,
        position: int = -1,
    ) -> None:
        super().__init__(public_message)
        self.public_message = public_message
        self.diagnostic_message = diagnostic_message or public_message
        self.position = position


def extract_json_object(response_text: str) -> Dict[str, Any]:
    """Extract a JSON object from raw model output."""
    text = (response_text or "").strip()
    if not text:
        raise AdminRaceCardJSONError("OpenRouter returned an empty response.")

    parse_error: Optional[AdminRaceCardJSONError] = None
    for candidate in _collect_json_candidates(text):
        for variant in _build_json_candidate_variants(candidate):
            try:
                payload = json.loads(variant)
            except json.JSONDecodeError as exc:
                candidate_error = _build_json_decode_error(variant, exc)
                if parse_error is None or candidate_error.position > parse_error.position:
                    parse_error = candidate_error
                continue

            if isinstance(payload, dict):
                return payload

            candidate_error = AdminRaceCardJSONError(
                "OpenRouter returned JSON, but the top-level value was not an object.",
                diagnostic_message="Parsed JSON content successfully, but the root value was not an object.",
                position=len(variant),
            )
            if parse_error is None or candidate_error.position > parse_error.position:
                parse_error = candidate_error

    if parse_error is not None:
        raise parse_error

    raise AdminRaceCardJSONError("OpenRouter response did not contain a JSON object.")


def _collect_json_candidates(text: str) -> List[str]:
    candidates: List[str] = []
    _append_unique_candidate(candidates, text)

    for fenced_block in re.findall(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE):
        _append_unique_candidate(candidates, fenced_block)

    for json_object in _extract_brace_balanced_objects(text):
        _append_unique_candidate(candidates, json_object)

    return candidates


def _append_unique_candidate(candidates: List[str], candidate: str) -> None:
    normalized = (candidate or "").strip()
    if normalized and normalized not in candidates:
        candidates.append(normalized)


def _build_json_candidate_variants(candidate: str) -> List[str]:
    variants = [candidate.strip()]
    without_trailing_commas = _remove_trailing_commas(variants[0])
    if without_trailing_commas != variants[0]:
        variants.append(without_trailing_commas)
    return variants


def _extract_brace_balanced_objects(text: str) -> List[str]:
    objects: List[str] = []
    start_index: Optional[int] = None
    depth = 0
    in_string = False
    escape_next = False

    for index, char in enumerate(text):
        if start_index is None:
            if char == "{":
                start_index = index
                depth = 1
                in_string = False
                escape_next = False
            continue

        if in_string:
            if escape_next:
                escape_next = False
            elif char == "\\":
                escape_next = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue

        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                objects.append(text[start_index:index + 1].strip())
                start_index = None

    return objects


def _remove_trailing_commas(text: str) -> str:
    result: List[str] = []
    in_string = False
    escape_next = False
    index = 0

    while index < len(text):
        char = text[index]
        if in_string:
            result.append(char)
            if escape_next:
                escape_next = False
            elif char == "\\":
                escape_next = True
            elif char == '"':
                in_string = False
            index += 1
            continue

        if char == '"':
            in_string = True
            result.append(char)
            index += 1
            continue

        if char == ",":
            look_ahead = index + 1
            while look_ahead < len(text) and text[look_ahead].isspace():
                look_ahead += 1
            if look_ahead < len(text) and text[look_ahead] in "]}":
                index += 1
                continue

        result.append(char)
        index += 1

    return "".join(result)


def _build_json_decode_error(text: str, exc: json.JSONDecodeError) -> AdminRaceCardJSONError:
    location = f"{exc.msg} at line {exc.lineno} column {exc.colno}"
    return AdminRaceCardJSONError(
        f"OpenRouter returned malformed JSON ({location}).",
        diagnostic_message=f"{location}. Context near error: {_extract_error_excerpt(text, exc.pos)}",
        position=exc.pos,
    )


def _extract_error_excerpt(text: str, position: int, radius: int = 80) -> str:
    start = max(0, position - radius)
    end = min(len(text), position + radius)
    excerpt = text[start:end].replace("\n", "\\n")
    if start > 0:
        excerpt = f"…{excerpt}"
    if end < len(text):
        excerpt = f"{excerpt}…"
    return excerpt


def merge_source_urls(
    source_urls: Optional[List[str]] = None,
    annotations: Optional[List[Dict[str, Any]]] = None,
) -> List[str]:
    """Merge explicit source URLs with OpenRouter citation annotations."""
    merged_urls: List[str] = []

    for url in source_urls or []:
        normalized = _normalize_source_url(url)
        if normalized and normalized not in merged_urls:
            merged_urls.append(normalized)

    for annotation in annotations or []:
        normalized = _normalize_source_url(_extract_annotation_url(annotation))
        if normalized and normalized not in merged_urls:
            merged_urls.append(normalized)

    return merged_urls


def build_equibase_card_overview_url(track_id: str, race_date: str, country: str = "USA") -> str:
    """Build the official Equibase card overview URL for a track/date.

    USA tracks use ``/static/entry/{track}{date}{country}-EQB.html``.
    International tracks use ``/static/foreign/entry/RaceCardIndex{track}{date}{country}-EQB.html``.
    """
    date_obj = datetime.strptime(race_date, "%Y-%m-%d")
    formatted_date = date_obj.strftime("%m%d%y")
    tid = track_id.upper()
    if country == "USA":
        return f"https://www.equibase.com/static/entry/{tid}{formatted_date}{country}-EQB.html?SAP=viewe2"
    return f"https://www.equibase.com/static/foreign/entry/RaceCardIndex{tid}{formatted_date}{country}-EQB.html"


def build_equibase_race_entry_url(track_id: str, race_date: str, race_number: int, country: str = "USA") -> str:
    """Build the Equibase individual race entry page URL.

    USA: ``/static/entry/{track}{date}{country}{race}-EQB.html``
    International: ``/static/foreign/entry/{track}{date}{country}{race}-EQB.html``
    """
    date_obj = datetime.strptime(race_date, "%Y-%m-%d")
    formatted_date = date_obj.strftime("%m%d%y")
    tid = track_id.upper()
    if country == "USA":
        return f"https://www.equibase.com/static/entry/{tid}{formatted_date}{country}{race_number}-EQB.html"
    return f"https://www.equibase.com/static/foreign/entry/{tid}{formatted_date}{country}{race_number}-EQB.html"


def build_equibase_smartpick_url(track_id: str, race_date: str, race_number: int, country: str = "USA") -> Optional[str]:
    """Build the Equibase SmartPick page URL for a specific race.

    Returns ``None`` for international tracks — SmartPicks are USA-only.
    """
    if country != "USA":
        return None
    date_obj = datetime.strptime(race_date, "%Y-%m-%d")
    formatted_date = date_obj.strftime("%m/%d/%Y")
    return (
        f"https://www.equibase.com/smartPick/smartPick.cfm/"
        f"?trackId={track_id.upper()}&raceDate={formatted_date}&country=USA&dayEvening=D&raceNumber={race_number}"
    )


def build_equibase_race_urls(
    track_id: str,
    race_date: str,
    race_numbers: List[int],
    country: str = "USA",
) -> Dict[int, Dict[str, str]]:
    """Build entry and SmartPick URLs for each race number.

    Returns ``{race_number: {"entry": url, "smartpick": url_or_none}}``.
    """
    urls: Dict[int, Dict[str, str]] = {}
    for race_number in race_numbers:
        urls[race_number] = {
            "entry": build_equibase_race_entry_url(track_id, race_date, race_number, country=country),
            "smartpick": build_equibase_smartpick_url(track_id, race_date, race_number, country=country),
        }
    return urls


def fetch_equibase_expected_race_numbers(
    track_id: str,
    race_date: str,
    timeout_seconds: float = 12.0,
    country: str = "USA",
) -> List[int]:
    """Fetch the official Equibase overview page and infer race numbers on the card."""
    html = _fetch_equibase_card_overview_html(track_id, race_date, timeout_seconds=timeout_seconds, country=country)
    if not html:
        return []

    expected_horses_by_race = _parse_equibase_expected_horses_by_race(html)
    if expected_horses_by_race:
        return sorted(expected_horses_by_race)

    return _extract_race_numbers_from_text(html)


def fetch_equibase_expected_horses_by_race(
    track_id: str,
    race_date: str,
    timeout_seconds: float = 12.0,
    country: str = "USA",
) -> Dict[int, List[str]]:
    """Fetch the official Equibase overview page and infer horse fields by race."""
    html = _fetch_equibase_card_overview_html(track_id, race_date, timeout_seconds=timeout_seconds, country=country)
    if not html:
        return {}

    return _parse_equibase_expected_horses_by_race(html)


def extract_structured_race_numbers(structured_card: Dict[str, Any]) -> List[int]:
    """Extract normalized race numbers from a structured card payload."""
    raw_races = structured_card.get("race_analyses") or structured_card.get("races") or []
    race_numbers: List[int] = []

    for index, race in enumerate(raw_races, start=1):
        race_number = _to_int(race.get("race_number") or race.get("number"), index)
        if race_number > 0:
            race_numbers.append(race_number)

    return sorted(set(race_numbers))


def find_missing_race_numbers(structured_card: Dict[str, Any], expected_race_numbers: List[int]) -> List[int]:
    """Return expected race numbers that are missing from the structured payload."""
    seen_numbers = set(extract_structured_race_numbers(structured_card))
    return [race_number for race_number in expected_race_numbers if race_number not in seen_numbers]


def extract_structured_horse_names_by_race(structured_card: Dict[str, Any]) -> Dict[int, List[str]]:
    """Extract normalized horse names by race from a structured card payload."""
    raw_races = structured_card.get("race_analyses") or structured_card.get("races") or []
    horses_by_race: Dict[int, List[str]] = {}

    for index, race in enumerate(raw_races, start=1):
        race_number = _to_int(race.get("race_number") or race.get("number"), index)
        raw_predictions = race.get("predictions") or race.get("entries") or race.get("horses") or []
        normalized_names: List[str] = []
        seen_names = set()
        for prediction in raw_predictions:
            horse_name = _normalize_horse_name(
                prediction.get("horse_name") or prediction.get("name") or prediction.get("horse")
            )
            horse_key = _horse_name_key(horse_name)
            if horse_key and horse_key not in seen_names:
                normalized_names.append(horse_name)
                seen_names.add(horse_key)
        if normalized_names:
            horses_by_race[race_number] = normalized_names

    return horses_by_race


def find_missing_horses_by_race(
    structured_card: Dict[str, Any],
    expected_horses_by_race: Dict[int, List[str]],
) -> Dict[int, List[str]]:
    """Return missing official horse names for each race in the structured payload."""
    if not expected_horses_by_race:
        return {}

    seen_horses_by_race = extract_structured_horse_names_by_race(structured_card)
    missing_horses_by_race: Dict[int, List[str]] = {}

    for race_number, expected_horses in sorted(expected_horses_by_race.items()):
        seen_keys = {
            _horse_name_key(name)
            for name in seen_horses_by_race.get(race_number, [])
            if _horse_name_key(name)
        }
        missing_horses: List[str] = []
        for horse_name in expected_horses:
            horse_key = _horse_name_key(horse_name)
            if horse_key and horse_key not in seen_keys:
                missing_horses.append(horse_name)
        if missing_horses:
            missing_horses_by_race[race_number] = missing_horses

    return missing_horses_by_race


_EMPTY_FIELD_VALUES = {"", "n/a", "na", "unknown", "tbd", "tba", "none", "-"}


def _is_empty_field(value: Any) -> bool:
    """Return True when a field value is missing, blank, or a known placeholder."""
    if not value:
        return True
    return str(value).strip().lower() in _EMPTY_FIELD_VALUES


def find_races_with_incomplete_fields(
    structured_card: Dict[str, Any],
    *,
    required_fields: tuple[str, ...] = ("jockey", "trainer"),
) -> Dict[int, List[str]]:
    """Find races where horses are missing required fields (e.g. jockey, trainer).

    Returns a dict mapping race number → list of missing field descriptions
    like ``["Horse A: jockey, trainer", "Horse B: jockey"]``.
    """
    raw_races = structured_card.get("race_analyses") or structured_card.get("races") or []
    incomplete: Dict[int, List[str]] = {}

    for index, race in enumerate(raw_races, start=1):
        race_number = _to_int(race.get("race_number") or race.get("number"), index)
        raw_predictions = race.get("predictions") or race.get("entries") or race.get("horses") or []

        race_gaps: List[str] = []
        for prediction in raw_predictions:
            horse_name = prediction.get("horse_name") or prediction.get("name") or prediction.get("horse") or "?"
            missing_fields = [
                field for field in required_fields if _is_empty_field(prediction.get(field))
            ]
            if missing_fields:
                race_gaps.append(f"{horse_name}: {', '.join(missing_fields)}")

        if race_gaps:
            incomplete[race_number] = race_gaps

    return incomplete


def merge_structured_race_cards(*structured_cards: Dict[str, Any]) -> Dict[str, Any]:
    """Merge multiple structured card payloads, keeping the strongest version of each race."""
    merged_card: Dict[str, Any] = {"card_overview": "", "race_analyses": []}
    merged_races: Dict[int, Dict[str, Any]] = {}

    for structured_card in structured_cards:
        if not isinstance(structured_card, dict):
            continue

        if not merged_card["card_overview"]:
            merged_card["card_overview"] = (
                structured_card.get("card_overview") or structured_card.get("overview") or ""
            )

        raw_races = structured_card.get("race_analyses") or structured_card.get("races") or []
        for index, race in enumerate(raw_races, start=1):
            race_number = _to_int(race.get("race_number") or race.get("number"), index)
            current = merged_races.get(race_number)
            if current is None:
                merged_races[race_number] = race
            else:
                merged_races[race_number] = _merge_race_payloads(current, race)

    merged_card["race_analyses"] = [merged_races[number] for number in sorted(merged_races)]
    return merged_card


def normalize_admin_results(
    structured_card: Dict[str, Any],
    *,
    race_date: str,
    track_id: str,
    llm_model: str,
    expected_horses_by_race: Optional[Dict[int, List[str]]] = None,
    source_urls: Optional[List[str]] = None,
    admin_notes: str = "",
    workflow: str = "admin_openrouter",
    analysis_duration_seconds: float = 0.0,
) -> Dict[str, Any]:
    """Normalize admin-created card data into the existing results contract."""
    raw_races = structured_card.get("race_analyses") or structured_card.get("races") or []
    race_analyses: List[Dict[str, Any]] = []

    for index, race in enumerate(raw_races, start=1):
        race_number = _to_int(race.get("race_number") or race.get("number"), index)
        predictions = _normalize_predictions(
            race.get("predictions") or race.get("entries") or race.get("horses") or []
        )
        if not predictions:
            continue

        expected_horses = (expected_horses_by_race or {}).get(race_number, [])
        missing_horses = _find_missing_expected_horses(predictions, expected_horses)

        race_analysis = {
            "race_number": race_number,
            "race_type": race.get("race_type") or race.get("type") or "",
            "distance": race.get("distance") or "",
            "surface": race.get("surface") or "",
            "predictions": predictions,
            "top_pick": predictions[0],
            "exotic_suggestions": race.get("exotic_suggestions") if isinstance(race.get("exotic_suggestions"), dict) else {},
            "field_size": len(predictions),
            "expected_field_size": len(expected_horses) if expected_horses else len(predictions),
            "field_complete": not missing_horses,
            "missing_horses": missing_horses,
        }
        race_analyses.append(race_analysis)

    race_analyses.sort(key=lambda race: race.get("race_number") or 0)

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
            "workflow": workflow,
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
            "horse_name": _normalize_horse_name(horse_name),
            "post_position": prediction.get("post_position") or prediction.get("post") or prediction.get("program_number"),
            "jockey": prediction.get("jockey") or "",
            "trainer": prediction.get("trainer") or "",
            "morning_line_odds": prediction.get("morning_line_odds") or prediction.get("morning_line") or "",
            "composite_rating": round(composite_rating, 1),
            "win_probability": 0.0,
            "factors": factors,
            "notes": prediction.get("notes") or prediction.get("analysis") or "",
        })

    normalized.sort(key=lambda item: item["composite_rating"], reverse=True)
    # Softmax win probability (T=15 balances spread vs. extreme compression)
    _SOFTMAX_T = 15.0
    _softmax_scores = [math.exp(item["composite_rating"] / _SOFTMAX_T) for item in normalized]
    _softmax_total = sum(_softmax_scores) or 1.0
    for item, _score in zip(normalized, _softmax_scores):
        item["win_probability"] = round((_score / _softmax_total) * 100, 1)

    return normalized


def _race_payload_quality(race: Dict[str, Any]) -> int:
    predictions = race.get("predictions") or race.get("entries") or race.get("horses") or []
    quality = len(predictions) * 10
    for key in ("race_type", "type", "distance", "surface", "exotic_suggestions"):
        if race.get(key):
            quality += 1
    return quality


def _merge_race_payloads(existing_race: Dict[str, Any], incoming_race: Dict[str, Any]) -> Dict[str, Any]:
    merged_race = dict(existing_race if _race_payload_quality(existing_race) >= _race_payload_quality(incoming_race) else incoming_race)

    for key in ("race_number", "number", "race_type", "type", "distance", "surface", "exotic_suggestions"):
        if not merged_race.get(key):
            merged_race[key] = existing_race.get(key) or incoming_race.get(key)

    existing_predictions = existing_race.get("predictions") or existing_race.get("entries") or existing_race.get("horses") or []
    incoming_predictions = incoming_race.get("predictions") or incoming_race.get("entries") or incoming_race.get("horses") or []
    merged_predictions = _merge_prediction_lists(existing_predictions, incoming_predictions)
    if merged_predictions:
        merged_race["predictions"] = merged_predictions

    return merged_race


def _merge_prediction_lists(*prediction_lists: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged_predictions: Dict[str, Dict[str, Any]] = {}

    for predictions in prediction_lists:
        for prediction in predictions or []:
            horse_name = prediction.get("horse_name") or prediction.get("name") or prediction.get("horse")
            horse_key = _horse_name_key(horse_name)
            if not horse_key:
                continue
            current = merged_predictions.get(horse_key)
            if current is None or _prediction_payload_quality(prediction) >= _prediction_payload_quality(current):
                merged_predictions[horse_key] = prediction

    return list(merged_predictions.values())


def _prediction_payload_quality(prediction: Dict[str, Any]) -> int:
    quality = 0
    for key in ("horse_name", "name", "horse", "post_position", "post", "program_number", "jockey", "trainer", "notes", "analysis"):
        if prediction.get(key):
            quality += 1
    if prediction.get("composite_rating") is not None or prediction.get("rating") is not None or prediction.get("confidence_score") is not None:
        quality += 2
    if prediction.get("factors"):
        quality += 2
    return quality


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


def _extract_annotation_url(annotation: Any) -> str:
    if not isinstance(annotation, dict):
        return ""

    citation = annotation.get("url_citation")
    if isinstance(citation, dict):
        return str(citation.get("url") or "").strip()

    return str(annotation.get("url") or "").strip()


def _extract_race_numbers_from_text(text: str) -> List[int]:
    if not text:
        return []

    matches = {int(value) for value in re.findall(r"\bRace\s*#?\s*([0-9]{1,2})\b", text, flags=re.IGNORECASE)}
    if not matches:
        return []
    if min(matches) == 1:
        return list(range(1, max(matches) + 1))
    return sorted(matches)


def _normalize_source_url(value: Any) -> str:
    if not value:
        return ""

    url = str(value).strip()
    if not url or not re.match(r"https?://", url, re.IGNORECASE):
        return ""
    return url


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


def _fetch_equibase_card_overview_html(track_id: str, race_date: str, timeout_seconds: float = 12.0, country: str = "USA") -> str:
    overview_url = build_equibase_card_overview_url(track_id, race_date, country=country)
    req = urllib_request.Request(
        overview_url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
        },
    )

    try:
        with urllib_request.urlopen(req, timeout=timeout_seconds) as response:
            return response.read().decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _extract_equibase_runner_refnos(html: str) -> set[str]:
    if not html:
        return set()

    return {
        match.group(1)
        for match in re.finditer(r"onVSAddClick\(\s*this\s*,\s*([0-9]+)\s*,", html, flags=re.IGNORECASE)
        if match.group(1)
    }


def _extract_equibase_refno(value: Any) -> str:
    if not value:
        return ""

    match = re.search(r"[?&]refno=([0-9]+)\b", str(value), flags=re.IGNORECASE)
    return match.group(1) if match else ""


def _parse_equibase_expected_horses_by_race(html: str) -> Dict[int, List[str]]:
    if not html:
        return {}

    valid_runner_refnos = _extract_equibase_runner_refnos(html)

    try:
        from race_entry_scraper import RaceEntryScraper

        parsed_races = RaceEntryScraper().parse_card_overview(html)
    except Exception:
        parsed_races = []

    expected_horses_by_race: Dict[int, List[str]] = {}
    for race in parsed_races or []:
        race_number = _to_int(race.get("race_number"), 0)
        if race_number <= 0:
            continue
        horses: List[str] = []
        seen_horses = set()
        for horse in race.get("horses") or []:
            horse_refno = _extract_equibase_refno(horse.get("profile_url") or horse.get("url"))
            if valid_runner_refnos and horse_refno and horse_refno not in valid_runner_refnos:
                continue

            horse_name = _normalize_horse_name(horse.get("name"))
            horse_key = _horse_name_key(horse_name)
            if horse_key and horse_key not in seen_horses:
                horses.append(horse_name)
                seen_horses.add(horse_key)
        if horses:
            expected_horses_by_race[race_number] = horses

    return expected_horses_by_race


def _find_missing_expected_horses(predictions: List[Dict[str, Any]], expected_horses: List[str]) -> List[str]:
    if not expected_horses:
        return []

    predicted_keys = {
        _horse_name_key(prediction.get("horse_name"))
        for prediction in predictions
        if _horse_name_key(prediction.get("horse_name"))
    }
    return [horse_name for horse_name in expected_horses if _horse_name_key(horse_name) not in predicted_keys]


def _normalize_horse_name(value: Any) -> str:
    if not value:
        return ""

    text = str(value).strip()
    text = re.sub(r"\s*\([A-Z]{2,3}\)\s*$", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _horse_name_key(value: Any) -> str:
    normalized = _normalize_horse_name(value).lower()
    return re.sub(r"[^a-z0-9]+", "", normalized)