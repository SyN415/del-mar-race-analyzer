#!/usr/bin/env python3
"""
Fetch Equibase profile pages using provided cookies.txt (Netscape format),
then parse Results + Workouts tables and update real_equibase_horse_data.json.

Usage:
  EQUIBASE_COOKIES_TXT=equibase_cookies.txt \
  .venv/bin/python scripts/parse_with_cookies.py \
      --horse "Curvino" \
      --profile-url "https://www.equibase.com/profiles/Results.cfm?type=Horse&refno=11171854&registry=T"

This avoids Selenium; it relies on cookies you exported from a real browser session.
"""
from __future__ import annotations
import argparse
import json
import os
import re
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

from equibase_scraper import EquibaseDataCollector

BASE = "https://www.equibase.com"


def parse_refno_registry(url: str) -> Tuple[Optional[str], Optional[str]]:
    m = re.search(r"refno=(\d+).*?registry=([A-Za-z])", url)
    if m:
        return m.group(1), m.group(2)
    return None, None


def load_netscape_cookies_to_session(path: str, session: requests.Session) -> int:
    count = 0
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        for ln in f:
            if not ln or ln.startswith('#'):
                continue
            ln = ln.strip()
            if not ln:
                continue
            parts = ln.split('\t')
            if len(parts) < 7:
                continue
            domain, flag, cookie_path, secure, expiry, name, value = parts[:7]
            session.cookies.set(name, value, domain=domain, path=cookie_path)
            count += 1
    return count


def fetch_with_cookies(session: requests.Session, url: str) -> Optional[str]:
    try:
        r = session.get(url, timeout=30)
        if r.status_code == 200 and r.text and 'Incapsula' not in r.text:
            return r.text
        # Try one follow-up GET without fragments
        if '#results' in url or '#workouts' in url:
            clean = url.split('#', 1)[0]
            r2 = session.get(clean, timeout=30)
            if r2.status_code == 200 and r2.text and 'Incapsula' not in r2.text:
                return r2.text
    except Exception:
        pass
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--horse', required=True)
    ap.add_argument('--profile-url', required=True)
    args = ap.parse_args()

    cookies_path = os.environ.get('EQUIBASE_COOKIES_TXT')
    if not cookies_path or not os.path.exists(cookies_path):
        raise SystemExit('EQUIBASE_COOKIES_TXT not set or file not found')

    sess = requests.Session()
    # Common headers
    sess.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
    })
    n = load_netscape_cookies_to_session(cookies_path, sess)
    print(f'Loaded {n} cookies into requests session from {cookies_path}')

    # Fetch results HTML
    res_html = fetch_with_cookies(sess, args.profile_url)
    if not res_html:
        raise SystemExit('Failed to fetch Results page with provided cookies (Incapsula likely still blocking)')

    # Save snapshot
    os.makedirs('logs/html', exist_ok=True)
    with open('logs/html/Curvino_results_fetched.html', 'w', encoding='utf-8') as f:
        f.write(res_html)

    soup = BeautifulSoup(res_html, 'html.parser')

    # Try to find workouts URL on the page, else build canonical
    workouts_url = None
    for a in soup.find_all('a', href=True):
        if 'workouts.cfm' in a['href']:
            href = a['href']
            workouts_url = href if href.startswith('http') else (BASE + href if href.startswith('/') else f'{BASE}/{href}')
            break
    if not workouts_url:
        refno, registry = parse_refno_registry(args.profile_url)
        if refno and registry:
            workouts_url = f'{BASE}/profiles/workouts.cfm?refno={refno}&registry={registry}'

    wk_html = None
    if workouts_url:
        wk_html = fetch_with_cookies(sess, workouts_url)
        if wk_html:
            with open('logs/html/Curvino_workouts_fetched.html', 'w', encoding='utf-8') as f:
                f.write(wk_html)

    # Parse tables via existing HTTP parsers
    dc = EquibaseDataCollector(headless=True)  # won't launch pages; we just use its parsers

    last3_results: List[Dict] = []
    workouts3: List[Dict] = []

    try:
        res_list = dc.parse_results_table_http(BeautifulSoup(res_html, 'html.parser'))
    except Exception as e:
        print('parse_results_table_http failed:', e)
        res_list = []
    for r in res_list[:3]:
        last3_results.append({
            'date': getattr(r, 'date', None),
            'track': getattr(r, 'track', None),
            'distance': getattr(r, 'distance', None),
            'surface': getattr(r, 'surface', None),
            'finish_position': getattr(r, 'finish_position', None),
            'speed_score': getattr(r, 'speed_score', None),
            'final_time': getattr(r, 'final_time', None),
            'beaten_lengths': getattr(r, 'beaten_lengths', None),
            'odds': getattr(r, 'odds', None),
            'race_number': getattr(r, 'race_number', None),
        })

    if wk_html:
        try:
            wk_list = dc.parse_workouts_table_http(BeautifulSoup(wk_html, 'html.parser'))
        except Exception as e:
            print('parse_workouts_table_http failed:', e)
            wk_list = []
        for w in wk_list[:3]:
            workouts3.append({
                'date': getattr(w, 'date', None),
                'track': getattr(w, 'track', None),
                'distance': getattr(w, 'distance', None),
                'time': getattr(w, 'time', None),
                'track_condition': getattr(w, 'track_condition', None),
                'workout_type': getattr(w, 'workout_type', None),
            })

    # Merge into real_equibase_horse_data.json
    out_path = 'real_equibase_horse_data.json'
    data: Dict[str, Dict] = {}
    if os.path.exists(out_path):
        try:
            with open(out_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            data = {}

    # Simple quality rating fallback
    def quality_rating(last3: List[Dict], w3: List[Dict]) -> float:
        score = 50.0
        if last3:
            score += 1.5
        if w3:
            score += 1.0
        return round(score, 1)

    qr = quality_rating(last3_results, workouts3)
    entry = data.get(args.horse, {})
    entry.update({
        'last3_results': last3_results,
        'workouts_last3': workouts3,
        'results': last3_results,
        'workouts': workouts3,
        'quality_rating': qr,
        'profile_url': args.profile_url,
    })
    data[args.horse] = entry

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

    print(f'Updated {out_path} for {args.horse}: last3={len(last3_results)}, workouts={len(workouts3)}')


if __name__ == '__main__':
    main()

