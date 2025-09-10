#!/usr/bin/env python3
"""
Parse offline-saved Equibase horse profile HTML (Results + Workouts) and update real_equibase_horse_data.json.

Usage:
  python scripts/parse_offline_profile.py --horse "Curvino" \
      --results-html logs/html/Curvino_results.html \
      --workouts-html logs/html/Curvino_workouts.html

Notes:
- This bypasses WAF by parsing HTML you saved manually from your browser.
- It will merge/update the entry for the given horse in real_equibase_horse_data.json.
"""
from __future__ import annotations
import argparse
import json
import os
from typing import List, Dict

from bs4 import BeautifulSoup

# Reuse collectors' HTTP table parsers
from equibase_scraper import EquibaseDataCollector


def load_html(path: str) -> BeautifulSoup:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return BeautifulSoup(f.read(), "html.parser")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--horse", required=True, help="Horse name key to update")
    ap.add_argument("--results-html", required=True, help="Path to saved Results HTML file")
    ap.add_argument("--workouts-html", required=False, help="Path to saved Workouts HTML file (optional)")
    args = ap.parse_args()

    horse = args.horse
    dc = EquibaseDataCollector(headless=False)

    last3_results: List[Dict] = []
    workouts3: List[Dict] = []

    # Parse Results
    res_soup = load_html(args.results_html)
    try:
        results = dc.parse_results_table_http(res_soup)
    except Exception as e:
        print(f"Failed to parse results table: {e}")
        results = []
    for r in results[:3]:
        last3_results.append({
            "date": getattr(r, "date", None),
            "track": getattr(r, "track", None),
            "distance": getattr(r, "distance", None),
            "surface": getattr(r, "surface", None),
            "finish_position": getattr(r, "finish_position", None),
            "speed_score": getattr(r, "speed_score", None),
            "final_time": getattr(r, "final_time", None),
            "beaten_lengths": getattr(r, "beaten_lengths", None),
            "odds": getattr(r, "odds", None),
            "race_number": getattr(r, "race_number", None),
        })

    # Parse Workouts (optional)
    if args.workouts_html and os.path.exists(args.workouts_html):
        wk_soup = load_html(args.workouts_html)
        try:
            wlist = dc.parse_workouts_table_http(wk_soup)
        except Exception as e:
            print(f"Failed to parse workouts table: {e}")
            wlist = []
        for w in wlist[:3]:
            workouts3.append({
                "date": getattr(w, "date", None),
                "track": getattr(w, "track", None),
                "distance": getattr(w, "distance", None),
                "time": getattr(w, "time", None),
                "track_condition": getattr(w, "track_condition", None),
                "workout_type": getattr(w, "workout_type", None),
            })

    # Merge into real_equibase_horse_data.json
    out_path = "real_equibase_horse_data.json"
    data = {}
    if os.path.exists(out_path):
        try:
            with open(out_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}

    # Compute a simple quality rating like SmartPick does (fallback if none)
    def quality_rating(last3: List[Dict], w3: List[Dict]) -> float:
        score = 50.0
        # small boosts
        if last3:
            score += 1.0
        if w3:
            score += 1.0
        return round(score, 1)

    qr = quality_rating(last3_results, workouts3)
    data[horse] = {
        "smartpick": {"combo_win_pct": None},
        "last3_results": last3_results,
        "workouts_last3": workouts3,
        "quality_rating": qr,
        "results": last3_results,
        "workouts": workouts3,
        "profile_url": data.get(horse, {}).get("profile_url", ""),
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"Updated {out_path} for {horse}: last3={len(last3_results)}, workouts={len(workouts3)}")


if __name__ == "__main__":
    main()

