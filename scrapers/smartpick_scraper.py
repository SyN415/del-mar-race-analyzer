#!/usr/bin/env python3
"""
SmartPick-centered scraper for Equibase.

- Fetch SmartPick page for a given race (trackId, date, raceNumber)
- Parse horses, including a Results.cfm profile link with refno/registry and
  the Jockey/Trainer combo win percentage when available
- Derive the Workouts URL from refno/registry and fetch last-3 workouts via
  existing BeautifulSoup-based parser in equibase_scraper. Falls back gently.
- Fetch Results.cfm via HTTP to get last-3 results (date/track/race/speed/finish/odds)
  using existing HTTP parser in equibase_scraper.
- Compute a quality rating from: combo win %, last-3 results (finish vs odds + figs),
  and last-3 workouts.

Notes:
- We intentionally avoid Search.cfm and rely on SmartPick + direct profile pages.
- If requests is blocked by Incapsula, caller can provide page_html captured via
  Selenium/UC; we also provide a light UC fallback when requested.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

# from equibase_scraper import # EquibaseDataCollector  # reuse HTTP helpers and parsers

BASE = "https://www.equibase.com"
HDR = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36"}


def normalize_profile_url(url: str) -> str:
    # Equibase sometimes obfuscates 'registry' as the registered sign sequence
    try:
        return url.replace("\u00aeistry=","registry=").replace("®istry=","registry=")
    except Exception:
        return url


@dataclass
class SmartPickHorse:
    name: str
    program: Optional[str] = None
    combo_win_pct: Optional[int] = None
    profile_url: Optional[str] = None
    refno: Optional[str] = None
    registry: Optional[str] = None


def smartpick_url(track_id: str, race_date_mmddyyyy: str, race_number: int, day: str = "D") -> str:
    return (
        f"{BASE}/smartPick/smartPick.cfm/?trackId={track_id}&raceDate={race_date_mmddyyyy}"
        f"&country=USA&dayEvening={day}&raceNumber={race_number}"
    )


def workouts_url(refno: str, registry: str) -> str:
    return f"{BASE}/profiles/workouts.cfm?refno={refno}&registry={registry}"


def is_block_page(text: str) -> bool:
    t = (text or "").lower()
    return "incapsula" in t or "requested content could not be located" in t or "system error" in t


def parse_refno_registry(url: str) -> Tuple[Optional[str], Optional[str]]:
    if not url:
        return None, None
    m = re.search(r"refno=(\d+).*?registry=([A-Za-z])", url)
    if m:
        return m.group(1), m.group(2)
    return None, None


class SmartPickRaceScraper:
    def __init__(self, headless: bool = True):
        self.session = requests.Session()
        self.session.headers.update(HDR)
        self.headless = headless
        # Reuse equibase collector for HTTP parsers
        # self.collector = # EquibaseDataCollector(headless=headless)
        # Optionally import cookies from a cookies.txt Netscape file
        try:
            import os
            ck_path = os.environ.get('EQUIBASE_COOKIES_TXT', '')
            if ck_path and os.path.exists(ck_path):
                self._load_cookies_txt(ck_path)
        except Exception:
            pass

    def fetch_html(self, url: str) -> Optional[str]:
        print(f"🌐 Fetching URL: {url}")
        # First try requests
        try:
            r = self.session.get(url, timeout=25)
            print(f"📡 HTTP Status: {r.status_code}")
            if r.status_code == 200:
                txt = r.text
                print(f"📄 Response length: {len(txt)} bytes")

                if is_block_page(txt):
                    print("🚫 Response appears to be blocked (Incapsula/error page)")
                else:
                    # Only accept requests path if we see actual horse profile links
                    if ('Results.cfm' in txt and 'type=Horse' in txt):
                        print("✅ Found horse profile links in response")
                        try:
                            import os
                            os.makedirs('logs/html', exist_ok=True)
                            with open('logs/html/smartpick_debug_requests.html', 'w', encoding='utf-8') as f:
                                f.write(txt)
                            print("📝 Saved HTML to logs/html/smartpick_debug_requests.html")
                        except Exception as e:
                            print(f"⚠️  Could not save HTML: {e}")
                        return txt
                    else:
                        print("⚠️  No horse profile links found in response, trying UC fallback")
                # Otherwise, fall through to UC to render dynamic content / pass WAF
        except Exception as e:
            print(f"❌ Request failed: {e}")
        # Fallback to UC to get page source
        print("🔄 Trying undetected_chromedriver fallback...")
        try:
            import undetected_chromedriver as uc
            from selenium.webdriver.common.by import By
            options = uc.ChromeOptions()
            if self.headless:
                options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            try:
                options.page_load_strategy = 'eager'
            except Exception:
                pass
            print("🚗 Starting Chrome driver...")
            driver = uc.Chrome(options=options, headless=self.headless)
            try:
                # Visit home to accept cookies first
                print("🏠 Visiting homepage to accept cookies...")
                driver.get(BASE)
                time.sleep(2)
                try:
                    btns = driver.find_elements(By.ID, 'onetrust-accept-btn-handler')
                    if btns:
                        print("🍪 Accepting cookies...")
                        btns[0].click(); time.sleep(1)
                except Exception:
                    pass
                # Now open target SmartPick URL
                print(f"🎯 Loading SmartPick page...")
                driver.get(url)
                time.sleep(6)
                html = driver.page_source
                print(f"📄 Got page source: {len(html)} bytes")
                # Save debug snapshot
                try:
                    import os
                    os.makedirs('logs/html', exist_ok=True)
                    with open('logs/html/smartpick_debug_uc.html', 'w', encoding='utf-8') as f:
                        f.write(html)
                    print("📝 Saved HTML to logs/html/smartpick_debug_uc.html")
                except Exception as e:
                    print(f"⚠️  Could not save HTML: {e}")
                return html
            finally:
                driver.quit()
                print("🛑 Chrome driver closed")
        except Exception as e:
            print(f"❌ UC fallback failed: {e}")
            return None

    def _load_cookies_txt(self, path: str):
        """Load Netscape cookies.txt into both requests session and Selenium driver."""
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = [ln.strip() for ln in f if ln.strip() and not ln.startswith('#')]
        except Exception as e:
            print(f"Failed to read cookies file: {e}")
            return
        # Load into requests
        req_count = 0
        try:
            import http.cookiejar as cookiejar
            cj = cookiejar.MozillaCookieJar()
            # Manually parse lines to avoid writing temp file
            for ln in lines:
                parts = ln.split('\t')
                if len(parts) < 7:
                    continue
                domain, flag, path, secure, expiry, name, value = parts[:7]
                secure = (secure.upper() == 'TRUE')
                # Add to requests session cookie jar
                self.session.cookies.set(name, value, domain=domain, path=path)
                req_count += 1
        except Exception as e:
            print(f"Cookie load (requests) error: {e}")
        # Load into selenium
        sel_count = 0
        try:
            # Must open base domain before add_cookie
            self.collector.driver.get(BASE)
            time.sleep(2)
            for ln in lines:
                parts = ln.split('\t')
                if len(parts) < 7:
                    continue
                domain, flag, path, secure, expiry, name, value = parts[:7]
                cookie = {
                    'name': name,
                    'value': value,
                    'path': path,
                    'domain': domain if domain.startswith('.') else domain,
                }
                try:
                    self.collector.driver.add_cookie(cookie)
                    sel_count += 1
                except Exception:
                    continue
        except Exception as e:
            print(f"Failed to load cookies into Selenium: {e}")
        print(f"Loaded cookies from {path}: requests={req_count}, selenium={sel_count}")

    def parse_smartpick(self, html: str) -> List[SmartPickHorse]:
        horses: List[SmartPickHorse] = []
        if not html:
            print("⚠️  No HTML content to parse")
            return horses

        # Save HTML for debugging
        try:
            import os
            os.makedirs('logs/html', exist_ok=True)
            with open('logs/html/smartpick_last_parse.html', 'w', encoding='utf-8') as f:
                f.write(html)
            print(f"📝 Saved HTML to logs/html/smartpick_last_parse.html ({len(html)} bytes)")
        except Exception as e:
            print(f"⚠️  Could not save HTML: {e}")

        soup = BeautifulSoup(html, "html.parser")

        # Check if page is blocked or has error
        page_text = soup.get_text().lower()
        if 'incapsula' in page_text or 'access denied' in page_text:
            print("🚫 Page appears to be blocked by WAF")
            return horses
        if 'no entries' in page_text or 'not available' in page_text:
            print("ℹ️  Page indicates no entries available")
            return horses

        # Strategy:
        # - Look for all Results.cfm horse profile links; around each link, extract name and combo win %
        results_links = soup.find_all("a", href=True)
        print(f"🔍 Found {len(results_links)} total links in HTML")

        horse_links = [a for a in results_links if "Results.cfm" in a.get("href", "") and "type=Horse" in a.get("href", "")]
        print(f"🐎 Found {len(horse_links)} horse profile links")

        for a in horse_links:
            href = a["href"]
            name = a.get_text(strip=True)
            if not name:
                continue
            full = href if href.startswith("http") else f"{BASE}{href if href.startswith('/') else '/' + href}"
            # Climb up a couple of parents to capture surrounding text for combo %
            combo = None
            node = a
            for _ in range(3):
                node = node.parent if node and node.parent else node
                if not node:
                    break
                txt = node.get_text(" ", strip=True)
                m = re.search(r"Jockey\s*\/\s*Trainer\s*Win\s*%\s*(\d{1,3})%", txt, re.I)
                if m:
                    combo = int(m.group(1))
                    break
            refno, reg = parse_refno_registry(full)
            horses.append(SmartPickHorse(name=name, combo_win_pct=combo, profile_url=full, refno=refno, registry=reg))
            print(f"  ✅ Parsed horse: {name} (combo: {combo}%)")

        # Deduplicate by name, prefer entries with combo %
        dedup: Dict[str, SmartPickHorse] = {}
        for h in horses:
            if h.name not in dedup or (h.combo_win_pct is not None and dedup[h.name].combo_win_pct is None):
                dedup[h.name] = h

        print(f"📊 Total unique horses after dedup: {len(dedup)}")
        return list(dedup.values())

    def fetch_results_http(self, results_url: str) -> Optional[BeautifulSoup]:
        try:
            soup = self.collector._http_get(results_url)
            if soup:
                return soup
        except Exception:
            pass
        # UC fallback to get profile page source
        try:
            import undetected_chromedriver as uc
            options = uc.ChromeOptions()
            if self.headless:
                options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            try:
                options.page_load_strategy = 'eager'
            except Exception:
                pass
            driver = uc.Chrome(options=options, headless=self.headless)
            try:
                from bs4 import BeautifulSoup as BS
                from selenium.webdriver.common.by import By
                def render_and_get_html():
                    driver.get(results_url)
                    time.sleep(4)
                    try:
                        btns = driver.find_elements(By.ID, 'onetrust-accept-btn-handler')
                        if btns:
                            btns[0].click(); time.sleep(1)
                    except Exception:
                        pass
                    try:
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/3);")
                        time.sleep(2)
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/1.2);")
                        time.sleep(2)
                    except Exception:
                        pass
                    return driver.page_source
                # First attempt
                html = render_and_get_html()
                soup = BS(html, 'html.parser')
                if not soup.find('table'):
                    # Retry once with extra wait and a second scroll cycle
                    time.sleep(3)
                    try:
                        driver.execute_script("window.scrollTo(0, 0);")
                        time.sleep(1)
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(3)
                    except Exception:
                        pass
                    html = driver.page_source
                    soup = BS(html, 'html.parser')
                # Save debug snapshot
                try:
                    import os
                    os.makedirs('logs/html', exist_ok=True)
                    with open('logs/html/profile_uc_render.html', 'w') as f:
                        f.write(html)
                except Exception:
                    pass
                return soup
            finally:
                driver.quit()
        except Exception:
            return None

    def fetch_workouts_http(self, refno: str, registry: str) -> Optional[BeautifulSoup]:
        url = workouts_url(refno, registry)
        try:
            soup = self.collector._http_get(url)
            if soup:
                return soup
        except Exception:
            pass
        try:
            import undetected_chromedriver as uc
            options = uc.ChromeOptions()
            if self.headless:
                options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            try:
                options.page_load_strategy = 'eager'
            except Exception:
                pass
            driver = uc.Chrome(options=options, headless=self.headless)
            try:
                from bs4 import BeautifulSoup as BS
                from selenium.webdriver.common.by import By
                def render_and_get_html():
                    driver.get(url)
                    time.sleep(4)
                    try:
                        btns = driver.find_elements(By.ID, 'onetrust-accept-btn-handler')
                        if btns:
                            btns[0].click(); time.sleep(1)
                    except Exception:
                        pass
                    try:
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/3);")
                        time.sleep(2)
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/1.2);")
                        time.sleep(2)
                    except Exception:
                        pass
                    return driver.page_source
                html = render_and_get_html()
                soup = BS(html, 'html.parser')
                if not soup.find('table'):
                    time.sleep(3)
                    try:
                        driver.execute_script("window.scrollTo(0, 0);")
                        time.sleep(1)
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(3)
                    except Exception:
                        pass
                    html = driver.page_source
                    soup = BS(html, 'html.parser')
                # Save debug snapshot
                try:
                    import os
                    os.makedirs('logs/html', exist_ok=True)
                    with open('logs/html/workouts_uc_render.html', 'w') as f:
                        f.write(html)
                except Exception:
                    pass
                return soup
            finally:
                driver.quit()
        except Exception:
            return None

    def compute_workout_score(self, workouts: List[Dict]) -> float:
        # Simple heuristic: average of last 3 ranks (lower is better) + freshness bump
        if not workouts:
            return 0.0
        score = 0.0
        n = min(3, len(workouts))
        for i in range(n):
            w = workouts[i]
            # Favor faster times implicitly by shorter textual times; fallback 0.33
            seg = 0.33
            if w.get("time"):
                # crude normalization: shorter mm:ss.xx yields higher score
                ttxt = w["time"]
                m = re.search(r"(\d{1,2}):(\d{2}\.\d)", ttxt)
                if m:
                    total = int(m.group(1))*60 + float(m.group(2))
                    seg = max(0.1, min(0.5, 90.0/total))
            score += seg
        return min(1.0, score / n)

    def finish_score(self, pos: Optional[int]) -> float:
        if not pos:
            return 0.0
        if pos == 1:
            return 1.0
        if pos == 2:
            return 0.6
        if pos == 3:
            return 0.45
        # decay after 3rd
        return max(0.0, 0.4 - 0.05 * (pos - 3))

    def implied_prob_from_odds(self, odds_text: Optional[str]) -> float:
        if not odds_text:
            return 0.0
        # Equibase odds often like 3.50 or 5.00 (decimal) or 7/2
        t = odds_text.strip()
        if re.match(r"^\d+(?:\.\d+)?$", t):
            dec = float(t)
            if dec <= 1e-6:
                return 0.0
            return 1.0 / dec
        m = re.match(r"^(\d+)\s*\/\s*(\d+)$", t)
        if m:
            num, den = int(m.group(1)), int(m.group(2))
            dec = 1.0 + num / den
            return 1.0 / dec
        return 0.0

    def quality_rating(self, combo_win_pct: Optional[int], last3_results: List[Dict], workouts_last3: List[Dict]) -> float:
        # Compute components
        # 1) Speed figs (from results): average of last 3 speed_score normalized to 100
        fig_vals = [r.get("speed_score") for r in last3_results if isinstance(r.get("speed_score"), (int, float))]
        fig_avg = (sum(fig_vals[:3]) / min(3, len(fig_vals))) if fig_vals else 0.0
        fig_comp = min(1.0, max(0.0, fig_avg / 100.0))
        # 2) Finish vs implied prob from odds
        q_parts = []
        for r in last3_results[:3]:
            pos = r.get("finish_position")
            odds = r.get("odds")
            imp = self.implied_prob_from_odds(str(odds) if odds is not None else None)
            q = self.finish_score(int(pos)) - imp if pos else -imp
            q_parts.append(q)
        fin_comp = 0.0 if not q_parts else sum(q_parts) / len(q_parts)
        fin_comp = max(-1.0, min(1.0, 0.5 + 0.5 * fin_comp))  # scale to 0..1 around 0.5
        # 3) Combo win %
        c_comp = 0.0 if combo_win_pct is None else max(0.0, min(1.0, combo_win_pct / 100.0))
        # 4) Workouts
        w_comp = self.compute_workout_score(workouts_last3)
        # Weights
        x = 0.35 * fig_comp + 0.30 * fin_comp + 0.20 * c_comp + 0.15 * w_comp
        return round(max(0.0, min(100.0, 100.0 * x)), 1)

    def scrape_race(self, track_id: str, race_date_mmddyyyy: str, race_number: int, day: str = "D") -> Dict[str, Dict]:
        url = smartpick_url(track_id, race_date_mmddyyyy, race_number, day)
        html = self.fetch_html(url)
        horses = self.parse_smartpick(html or "")
        out: Dict[str, Dict] = {}
        for h in horses:
            horse_data = {"smartpick": {"combo_win_pct": h.combo_win_pct}}
            last3_results: List[Dict] = []
            workouts3: List[Dict] = []
            all_results: List = []
            # Results via HTTP parser
            if h.profile_url:
                soup = self.fetch_results_http(normalize_profile_url(h.profile_url))
                if soup:
                    try:
                        results = self.collector.parse_results_table_http(soup)
                        all_results = results or []
                        for r in (results[:3] if results else []):
                            last3_results.append({
                                "date": r.date,
                                "track": r.track,
                                "distance": r.distance,
                                "surface": r.surface,
                                "finish_position": r.finish_position,
                                "speed_score": r.speed_score,
                                "final_time": r.final_time,
                                "beaten_lengths": r.beaten_lengths,
                                "odds": r.odds,
                                "race_number": r.race_number if hasattr(r, 'race_number') else None,
                            })
                    except Exception:
                        pass
            # Workouts via HTTP parser
            if h.refno and h.registry:
                w_soup = self.fetch_workouts_http(h.refno, h.registry)
                if w_soup:
                    try:
                        ws = self.collector.parse_workouts_table_http(w_soup)
                        for w in ws[:3]:
                            workouts3.append({
                                "date": w.date,
                                "track": w.track,
                                "distance": w.distance,
                                "time": w.time,
                                "track_condition": w.track_condition,
                                "workout_type": w.workout_type,
                            })
                    except Exception:
                        pass
            # Compute SmartPick-style figures
            # bestSpeedFigure as lifetime max E from all parsed results
            best_fig = None
            try:
                vals = [getattr(r, 'speed_score', None) for r in all_results]
                vals = [float(v) for v in vals if isinstance(v, (int, float)) and v > 0]
                if vals:
                    best_fig = max(vals)
            except Exception:
                best_fig = None
            last3_e = [x.get('speed_score') for x in last3_results if isinstance(x.get('speed_score'), (int, float))]
            avg_last3 = round(sum(last3_e) / len(last3_e), 1) if last3_e else None
            our_sf = None
            if isinstance(best_fig, (int, float)) and isinstance(avg_last3, (int, float)):
                our_sf = round((best_fig + avg_last3) / 2.0, 1)
            elif isinstance(best_fig, (int, float)):
                our_sf = float(best_fig)
            qr = self.quality_rating(h.combo_win_pct, last3_results, workouts3)
            # Merge all
            horse_data.update({
                "last3_results": last3_results,
                "workouts_last3": workouts3,
                "quality_rating": qr,
                "profile_url": h.profile_url,
                "workouts_url": workouts_url(h.refno, h.registry) if (h.refno and h.registry) else None,
                # Engine compatibility
                "results": last3_results,
                "workouts": workouts3,
            })
            # Enrich smartpick block
            spb = horse_data.setdefault("smartpick", {})
            if best_fig is not None:
                spb["bestSpeedFigure"] = best_fig
            if avg_last3 is not None:
                spb["avgLast3Speed"] = avg_last3
            if last3_e:
                spb["last3E"] = last3_e
            if isinstance(our_sf, (int, float)):
                spb["our_speed_figure"] = our_sf
                horse_data["our_speed_figure"] = our_sf  # top-level for engine
            out[h.name] = horse_data
        return out

    def scrape_via_profile_url(self, horse_name: str, profile_url: str) -> Dict[str, Dict]:
        """Parse a known Results.cfm profile URL; then parse workouts via link on page."""
        out: Dict[str, Dict] = {}
        last3_results: List[Dict] = []
        workouts3: List[Dict] = []
        soup = self.fetch_results_http(normalize_profile_url(profile_url))
        if soup:
            try:
                results = self.collector.parse_results_table_http(soup)
                for r in results[:3]:
                    last3_results.append({
                        "date": r.date, "track": r.track, "distance": r.distance, "surface": r.surface,
                        "finish_position": r.finish_position, "speed_score": r.speed_score,
                        "final_time": r.final_time, "beaten_lengths": r.beaten_lengths, "odds": r.odds,
                    })
                # Prefer canonical workouts URL via refno/registry when available
                refno, reg = parse_refno_registry(profile_url)
                w_soup = None
                if refno and reg:
                    w_soup = self.fetch_workouts_http(refno, reg)
                if not w_soup:
                    # Fallback: find workouts link on page
                    w_link = None
                    for a in soup.find_all('a', href=True):
                        if 'Workouts' in a.get_text(strip=True):
                            w_link = a['href']; break
                    if w_link:
                        w_url = w_link if w_link.startswith('http') else (BASE + w_link if w_link.startswith('/') else f"{BASE}/{w_link}")
                        # Try UC render path for workouts as well (reuse results fetcher)
                        w_soup = self.fetch_results_http(w_url) or self.collector._http_get(w_url)
                if w_soup:
                    ws = self.collector.parse_workouts_table_http(w_soup)
                    for w in ws[:3]:
                        workouts3.append({
                            "date": w.date, "track": w.track, "distance": w.distance, "time": w.time,
                            "track_condition": w.track_condition, "workout_type": w.workout_type,
                        })
            except Exception:
                pass
        # If HTTP/UC path yielded nothing, use Selenium DOM parser directly
        if not last3_results:
            try:
                self.collector.driver.get(profile_url)
                time.sleep(4)
                try:
                    # Ensure we are on Results tab; click if present
                    from selenium.webdriver.common.by import By
                    from selenium.webdriver.support.ui import WebDriverWait
                    from selenium.webdriver.support import expected_conditions as EC
                    try:
                        tab = WebDriverWait(self.collector.driver, 10).until(
                            EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Results')]"))
                        )
                        tab.click(); time.sleep(1)
                    except Exception:
                        pass
                except Exception:
                    pass
                res = self.collector.parse_results_table()
                for r in res[:3]:
                    last3_results.append({
                        "date": r.date, "track": r.track, "distance": r.distance, "surface": r.surface,
                        "finish_position": r.finish_position, "speed_score": r.speed_score,
                        "final_time": r.final_time, "beaten_lengths": r.beaten_lengths, "odds": r.odds,
                    })
            except Exception:
                pass
        if not workouts3:
            try:
                # Try direct workouts URL first
                refno, reg = parse_refno_registry(profile_url)
                if refno and reg:
                    w_soup = self.fetch_workouts_http(refno, reg)
                    if w_soup:
                        ws = self.collector.parse_workouts_table_http(w_soup)
                        for w in ws[:3]:
                            workouts3.append({
                                "date": w.date, "track": w.track, "distance": w.distance, "time": w.time,
                                "track_condition": w.track_condition, "workout_type": w.workout_type,
                            })
                if not workouts3:
                    # Selenium: click Workouts tab
                    from selenium.webdriver.common.by import By
                    from selenium.webdriver.support.ui import WebDriverWait
                    from selenium.webdriver.support import expected_conditions as EC
                    try:
                        self.collector.driver.get(profile_url)
                        time.sleep(3)
                        tab = WebDriverWait(self.collector.driver, 10).until(
                            EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Workouts')]"))
                        )
                        tab.click(); time.sleep(1)
                    except Exception:
                        pass
                    ws_dom = self.collector.parse_workouts_table()
                    for w in ws_dom[:3]:
                        workouts3.append({
                            "date": w.date, "track": w.track, "distance": w.distance, "time": w.time,
                            "track_condition": w.track_condition, "workout_type": w.workout_type,
                        })
            except Exception:
                pass
        qr = self.quality_rating(None, last3_results, workouts3)
        out[horse_name] = {
            "smartpick": {"combo_win_pct": None},
            "last3_results": last3_results,
            "workouts_last3": workouts3,
            "quality_rating": qr,
            "profile_url": profile_url,
            "results": last3_results,
            "workouts": workouts3,
        }
        return out

    def scrape_horse_by_name(self, horse_name: str) -> Dict[str, Dict]:
        """Fallback path: resolve Results.cfm via HTTP search, then parse results and workouts.
        Avoids SmartPick entirely when blocked. Returns {name: data} or {} if not found.
        """
        out: Dict[str, Dict] = {}
        try:
            results_url = self.collector.search_horse_profile_requests(horse_name)
        except Exception:
            results_url = None
        last3_results: List[Dict] = []
        workouts3: List[Dict] = []
        if results_url:
            soup = self.fetch_results_http(normalize_profile_url(results_url))
            if soup:
                try:
                    results = self.collector.parse_results_table_http(soup)
                    for r in results[:3]:
                        last3_results.append({
                            "date": r.date,
                            "track": r.track,
                            "distance": r.distance,
                            "surface": r.surface,
                            "finish_position": r.finish_position,
                            "speed_score": r.speed_score,
                            "final_time": r.final_time,
                            "beaten_lengths": r.beaten_lengths,
                            "odds": r.odds,
                            "race_number": getattr(r, 'race_number', None),
                        })
                    # Find workouts link from page
                    w_link = None
                    for a in soup.find_all('a', href=True):
                        if 'Workouts' in a.get_text(strip=True):
                            w_link = a['href']; break
                    if w_link:
                        w_url = w_link if w_link.startswith('http') else (BASE + w_link if w_link.startswith('/') else f"{BASE}/{w_link}")
                        w_soup = self.collector._http_get(w_url)
                        if w_soup:
                            ws = self.collector.parse_workouts_table_http(w_soup)
                            for w in ws[:3]:
                                workouts3.append({
                                    "date": w.date,
                                    "track": w.track,
                                    "distance": w.distance,
                                    "time": w.time,
                                    "track_condition": w.track_condition,
                                    "workout_type": w.workout_type,
                                })
                except Exception:
                    pass
        # If HTTP path failed to yield data, attempt Selenium-based fallback via collector
        if not last3_results:
            try:
                sel_results = self.collector.search_horse_results(horse_name)
                for r in sel_results[:3]:
                    last3_results.append({
                        "date": r.date,
                        "track": r.track,
                        "distance": r.distance,
                        "surface": r.surface,
                        "finish_position": r.finish_position,
                        "speed_score": r.speed_score,
                        "final_time": r.final_time,
                        "beaten_lengths": r.beaten_lengths,
                        "odds": r.odds,
                    })
                sel_workouts = self.collector.search_horse_workouts(horse_name)
                for w in sel_workouts[:3]:
                    workouts3.append({
                        "date": w.date,
                        "track": w.track,
                        "distance": w.distance,
                        "time": w.time,
                        "track_condition": w.track_condition,
                        "workout_type": w.workout_type,
                    })
            except Exception:
                pass
        qr = self.quality_rating(None, last3_results, workouts3)
        out[horse_name] = {
            "smartpick": {"combo_win_pct": None},
            "last3_results": last3_results,
            "workouts_last3": workouts3,
            "quality_rating": qr,
            "profile_url": results_url,
            # Engine compatibility
            "results": last3_results,
            "workouts": workouts3,
        }
        return out

    def close(self):
        try:
            self.collector.close()
        except Exception:
            pass

if __name__ == "__main__":
    s = SmartPickRaceScraper(headless=False)
    try:
        print("Quick self-test disabled by default.")
    finally:
        s.close()

