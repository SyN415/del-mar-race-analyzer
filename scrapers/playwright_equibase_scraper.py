#!/usr/bin/env python3
"""
Playwright-based Equibase scraper with WAF evasion.

Key improvements over Selenium approach:
- Playwright has better stealth capabilities
- Residential proxy rotation
- Randomized browser fingerprints
- Human-like timing and behavior
- Better error handling and retries
"""
from __future__ import annotations

import asyncio
import json
import random
import re
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from playwright.async_api import async_playwright, Browser, BrowserContext, Page
import requests
from bs4 import BeautifulSoup


@dataclass
class ProxyConfig:
    server: str
    username: Optional[str] = None
    password: Optional[str] = None


@dataclass
class WorkoutData:
    """Structure for workout information"""
    date: str
    track: str
    distance: str
    time: str
    track_condition: str
    workout_type: str  # 'b' for breeze, 'h' for handily, etc.


@dataclass
class ResultData:
    """Structure for past performance results"""
    date: str
    track: str
    distance: str
    surface: str
    finish_position: int
    speed_score: int  # E column speed figure
    final_time: str
    beaten_lengths: float
    odds: str


class PlaywrightEquibaseScraper:
    def __init__(self, proxy_list: List[ProxyConfig] = None):
        self.proxy_list = proxy_list or []
        self.current_proxy_index = 0
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        
    async def __aenter__(self):
        self.playwright = await async_playwright().start()
        self.context = await self.create_stealth_context()
        self.page = await self.context.new_page()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        await self.playwright.stop()

    def get_random_user_agent(self) -> str:
        """Return a random realistic user agent"""
        agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ]
        return random.choice(agents)

    def get_random_viewport(self) -> Tuple[int, int]:
        """Return a random realistic viewport size"""
        viewports = [
            (1920, 1080), (1366, 768), (1536, 864), (1440, 900),
            (1280, 720), (1600, 900), (2560, 1440)
        ]
        return random.choice(viewports)

    async def create_stealth_context(self) -> BrowserContext:
        """Create a browser context with stealth settings"""
        proxy = None
        if self.proxy_list:
            proxy_config = self.proxy_list[self.current_proxy_index % len(self.proxy_list)]
            proxy = {
                "server": proxy_config.server,
                "username": proxy_config.username,
                "password": proxy_config.password,
            }
            self.current_proxy_index += 1

        # Launch browser with stealth settings
        self.browser = await self.playwright.chromium.launch(
            headless=True,  # Run headless for production
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-features=VizDisplayCompositor",
                "--disable-extensions",
                "--no-first-run",
                "--disable-default-apps",
                "--disable-component-extensions-with-background-pages",
            ]
        )

        width, height = self.get_random_viewport()
        
        self.context = await self.browser.new_context(
            viewport={"width": width, "height": height},
            user_agent=self.get_random_user_agent(),
            proxy=proxy,
            locale="en-US",
            timezone_id="America/New_York",
            permissions=["geolocation"],
            geolocation={"latitude": 40.7128, "longitude": -74.0060},  # NYC
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Cache-Control": "max-age=0",
            }
        )

        # Add stealth scripts
        await self.context.add_init_script("""
            // Remove webdriver property
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
            });
            
            // Mock chrome runtime
            window.chrome = {
                runtime: {},
            };
            
            // Mock permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
        """)

        return self.context

    async def human_like_delay(self, min_ms: int = 1000, max_ms: int = 3000):
        """Add human-like delays"""
        delay = random.uniform(min_ms, max_ms) / 1000
        await asyncio.sleep(delay)

    def fix_profile_url(self, profile_url: str) -> str:
        """Fix common URL formatting issues"""
        # Fix registry parameter encoding
        clean_url = profile_url.replace('\u00aeistry=', 'registry=').replace('®istry=', 'registry=')

        # Fix missing ampersands in URL parameters
        # Pattern: refno=12345registry=T should be refno=12345&registry=T
        clean_url = re.sub(r'refno=(\d+)registry=', r'refno=\1&registry=', clean_url)
        clean_url = re.sub(r'registry=([A-Za-z])rbt=', r'registry=\1&rbt=', clean_url)

        return clean_url

    async def fetch_profile_page(self, profile_url: str, tab_fragment: str = "") -> Optional[str]:
        """Fetch a horse profile page with stealth techniques"""
        try:
            if not self.context:
                await self.create_stealth_context()

            page = await self.context.new_page()

            # Navigate with human-like behavior
            await page.goto("https://www.equibase.com", wait_until="domcontentloaded")
            await self.human_like_delay(2000, 4000)

            # Accept cookies if present
            try:
                cookie_btn = page.locator("#onetrust-accept-btn-handler")
                if await cookie_btn.is_visible(timeout=3000):
                    await cookie_btn.click()
                    await self.human_like_delay(1000, 2000)
            except:
                pass

            # Fix URL formatting issues
            clean_url = self.fix_profile_url(profile_url)

            # Add tab fragment if specified
            if tab_fragment:
                clean_url = f"{clean_url}#{tab_fragment}"

            # Navigate to profile page
            await page.goto(clean_url, wait_until="domcontentloaded")
            await self.human_like_delay(3000, 5000)
            
            # Scroll to trigger content loading
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 3)")
            await self.human_like_delay(1000, 2000)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await self.human_like_delay(2000, 3000)
            
            # Get page content
            content = await page.content()
            await page.close()
            
            # Check if we got blocked
            if "incapsula" in content.lower() or "access denied" in content.lower():
                return None
                
            return content
            
        except Exception as e:
            print(f"Error fetching profile page: {e}")
            return None

    async def scrape_horse_profile(self, horse_name: str, profile_url: str) -> Dict:
        """Scrape a complete horse profile with results and workouts"""
        # Fetch results page with #results fragment
        results_html = await self.fetch_profile_page(profile_url, "results")
        if not results_html:
            return {"error": "Failed to fetch results page"}

        # Parse results
        soup = BeautifulSoup(results_html, 'html.parser')
        last3_results = self.parse_results_table(soup)

        # Fetch workouts page with #workouts fragment
        workouts_html = await self.fetch_profile_page(profile_url, "workouts")
        workouts3 = []

        if workouts_html:
            workouts_soup = BeautifulSoup(workouts_html, 'html.parser')
            workouts3 = self.parse_workouts_table(workouts_soup)
        
        return {
            "horse_name": horse_name,
            "profile_url": profile_url,
            "last3_results": last3_results[:3],  # Limit to last 3
            "workouts_last3": workouts3[:3],    # Limit to last 3
            "results": last3_results[:3],       # Engine compatibility
            "workouts": workouts3[:3],          # Engine compatibility
            "quality_rating": self.calculate_quality_rating(last3_results, workouts3),
            "smartpick": {"combo_win_pct": None}  # Will be populated by SmartPick scraper
        }

    def parse_results_table(self, soup: BeautifulSoup) -> List[Dict]:
        """Parse results table from HTML"""
        results = []
        try:
            # Try multiple strategies to find the results table
            table = None

            # Strategy 1: Look for results-specific table classes
            table = soup.find('table', class_=re.compile(r'(results|PastPerformance|race)', re.I))

            # Strategy 2: Look for table with results-specific headers
            if not table:
                tables = soup.find_all('table')
                for t in tables:
                    headers = [th.get_text(strip=True).upper() for th in t.find_all(['th', 'td'])[:10]]
                    if any(h in ['DATE', 'TRACK', 'FINISH', 'FIN', 'DISTANCE', 'TIME'] for h in headers):
                        table = t
                        break

            # Strategy 3: Look for any table with date-like content
            if not table:
                for t in tables:
                    text = t.get_text()
                    if re.search(r'\d{1,2}/\d{1,2}/\d{4}', text):  # Date pattern
                        table = t
                        break

            if not table:
                return results

            rows = table.find_all('tr')
            if not rows:
                return results

            headers = [c.get_text(strip=True).upper() for c in rows[0].find_all(['th','td'])]
            hidx = {h: i for i, h in enumerate(headers)}

            def idx(*cands, default=None):
                for c in cands:
                    u = c.upper()
                    if u in hidx:
                        return hidx[u]
                return default

            date_i = idx('DATE', default=0)
            track_i = idx('TRACK', default=1)
            dist_i = idx('DISTANCE','DIST', default=2)
            surf_i = idx('SURFACE','S', default=3)
            fin_i = idx('FIN','FINISH','POS', default=4)
            time_i = idx('FINAL TIME','TIME', default=6)
            beat_i = idx('BEATEN','MARGIN', default=7)
            e_i = idx('E','SPEED','SPEED FIGURE','SPEED RATING','FIG','SR','S/R','SPD','EQUIBASE SPEED FIGURE', default=8)
            odds_i = idx('ODDS', default=9)

            for row in rows[1:]:
                cells = row.find_all('td')
                if not cells:
                    continue
                try:
                    def get(i):
                        return cells[i].get_text(strip=True) if i is not None and len(cells) > i else ''
                    def as_int(s):
                        try:
                            return int(re.sub(r"[^0-9]","", s))
                        except Exception:
                            return 0
                    def as_float(s):
                        try:
                            return float(re.sub(r"[^0-9\.]","", s))
                        except Exception:
                            return 0.0

                    results.append({
                        "date": get(date_i),
                        "track": get(track_i),
                        "distance": get(dist_i),
                        "surface": get(surf_i).lower(),
                        "finish_position": as_int(get(fin_i)),
                        "speed_score": as_int(get(e_i)),
                        "final_time": get(time_i),
                        "beaten_lengths": as_float(get(beat_i)),
                        "odds": get(odds_i),
                        "race_number": None,
                    })
                except Exception:
                    continue
        except Exception as e:
            print(f"Parse results failed: {e}")
        return results

    def parse_workouts_table(self, soup: BeautifulSoup) -> List[Dict]:
        """Parse workouts table from HTML"""
        workouts = []
        try:
            table = soup.find('table', class_=re.compile(r'(workouts|Workouts)', re.I))
            if not table:
                # Try finding any table with workout data
                tables = soup.find_all('table')
                for t in tables:
                    if any('workout' in str(th).lower() or 'time' in str(th).lower() for th in t.find_all(['th', 'td'])):
                        table = t
                        break

            if not table:
                return workouts

            rows = table.find_all('tr')
            if not rows:
                return workouts

            headers = [c.get_text(strip=True).upper() for c in rows[0].find_all(['th','td'])]
            hidx = {h: i for i, h in enumerate(headers)}

            def idx(*cands, default=None):
                for c in cands:
                    u = c.upper()
                    if u in hidx:
                        return hidx[u]
                return default

            date_i = idx('DATE', default=0)
            track_i = idx('TRACK', default=1)
            dist_i = idx('DISTANCE','DIST', default=2)
            time_i = idx('TIME','FINAL TIME', default=3)
            cond_i = idx('COND','CONDITION','TRACK CONDITION', default=4)
            type_i = idx('TYPE','WORKOUT TYPE', default=5)

            for row in rows[1:]:
                cells = row.find_all('td')
                if not cells:
                    continue
                def get(i):
                    return cells[i].get_text(strip=True) if i is not None and len(cells) > i else ''

                workouts.append({
                    "date": get(date_i),
                    "track": get(track_i),
                    "distance": get(dist_i),
                    "time": get(time_i),
                    "track_condition": get(cond_i),
                    "workout_type": get(type_i)
                })
        except Exception as e:
            print(f"Parse workouts failed: {e}")
        return workouts

    def find_workouts_url(self, soup: BeautifulSoup, profile_url: str) -> Optional[str]:
        """Find workouts URL from profile page"""
        try:
            # Look for workouts link
            for a in soup.find_all('a', href=True):
                if 'workouts.cfm' in a['href'].lower() or 'workouts' in a.get_text(strip=True).lower():
                    href = a['href']
                    if href.startswith('http'):
                        return href
                    elif href.startswith('/'):
                        return f"https://www.equibase.com{href}"
                    else:
                        return f"https://www.equibase.com/{href}"

            # Fallback: construct workouts URL from profile URL
            if 'refno=' in profile_url and 'registry=' in profile_url:
                refno_match = re.search(r'refno=(\d+)', profile_url)
                registry_match = re.search(r'registry=([A-Za-z])', profile_url)
                if refno_match and registry_match:
                    refno = refno_match.group(1)
                    registry = registry_match.group(1)
                    return f"https://www.equibase.com/profiles/workouts.cfm?refno={refno}&registry={registry}"
        except Exception as e:
            print(f"Error finding workouts URL: {e}")
        return None

    def calculate_quality_rating(self, results: List[Dict], workouts: List[Dict]) -> float:
        """Calculate quality rating based on results and workouts"""
        try:
            score = 50.0

            # Boost for having recent results
            if results:
                score += 5.0

                # Analyze finish positions vs odds
                for r in results[:3]:
                    finish = r.get('finish_position', 0)
                    speed = r.get('speed_score', 0)

                    if finish == 1:
                        score += 10.0
                    elif finish <= 3:
                        score += 5.0

                    if speed >= 90:
                        score += 8.0
                    elif speed >= 80:
                        score += 4.0

            # Boost for recent workouts
            if workouts:
                score += 3.0

                # Analyze workout times (basic heuristic)
                for w in workouts[:3]:
                    time_str = w.get('time', '')
                    if ':' in time_str:
                        try:
                            parts = time_str.split(':')
                            if len(parts) == 2:
                                minutes = int(parts[0])
                                seconds = float(parts[1])
                                total_seconds = minutes * 60 + seconds

                                # Good workout times get bonus
                                if total_seconds < 60:  # Under 1 minute for short distances
                                    score += 2.0
                        except:
                            pass

            return round(min(100.0, max(0.0, score)), 1)
        except Exception:
            return 50.0


    async def scrape_smartpick_data(self, track_id: str, race_date: str, race_number: int) -> Dict:
        """
        Scrape SmartPick data for a specific race

        Args:
            track_id: Track ID (e.g., 'DMR' for Del Mar)
            race_date: Date in MM/DD/YYYY format
            race_number: Race number
        """
        try:
            # Format the date for URL (MM%2FDD%2FYYYY)
            formatted_date = race_date.replace('/', '%2F')

            # Construct SmartPick URL
            smartpick_url = (
                f"https://www.equibase.com/smartPick/smartPick.cfm/"
                f"?trackId={track_id}&raceDate={formatted_date}&country=USA&dayEvening=D&raceNumber={race_number}"
            )

            if not self.context:
                await self.create_stealth_context()

            page = await self.context.new_page()

            # Navigate to SmartPick page
            await page.goto(smartpick_url, wait_until="domcontentloaded")
            await self.human_like_delay(3000, 5000)

            # Get page content
            content = await page.content()
            await page.close()

            # Parse SmartPick data
            soup = BeautifulSoup(content, 'html.parser')
            smartpick_data = self.parse_smartpick_data(soup)

            return smartpick_data

        except Exception as e:
            print(f"Error scraping SmartPick data: {e}")
            return {}

    async def extract_smartpick_data_from_page(self, page) -> Dict:
        """Extract SmartPick data from Angular-rendered page using JavaScript"""
        try:
            # Wait for Angular to render content
            await page.wait_for_timeout(3000)

            # Extract data using JavaScript execution
            smartpick_data = await page.evaluate('''
                () => {
                    const data = {};

                    // Look for tables with horse data
                    const tables = document.querySelectorAll('table');

                    for (const table of tables) {
                        const rows = table.querySelectorAll('tr');
                        if (rows.length < 2) continue;

                        // Check if this looks like a horse data table
                        const headerRow = rows[0];
                        const headerText = headerRow.textContent.toLowerCase();

                        if (headerText.includes('horse') || headerText.includes('selection') || headerText.includes('name')) {
                            // Parse data rows
                            for (let i = 1; i < rows.length; i++) {
                                const row = rows[i];
                                const cells = row.querySelectorAll('td, th');

                                if (cells.length < 2) continue;

                                const horseName = cells[0].textContent.trim();
                                if (!horseName || horseName.toLowerCase().includes('horse')) continue;

                                const horseData = { horse_name: horseName };

                                // Extract data from other cells
                                for (let j = 1; j < cells.length; j++) {
                                    const cellText = cells[j].textContent.trim();

                                    // Look for percentages
                                    if (cellText.includes('%')) {
                                        const pct = parseFloat(cellText.replace('%', ''));
                                        if (!isNaN(pct)) {
                                            if (j === 1) horseData.win_pct = pct;
                                            else if (!horseData.combo_win_pct) horseData.combo_win_pct = pct;
                                        }
                                    }
                                    // Look for odds
                                    else if (cellText.includes('/') || cellText.includes('-')) {
                                        horseData.odds = cellText;
                                    }
                                    // Look for numerical ratings
                                    else {
                                        const rating = parseFloat(cellText);
                                        if (!isNaN(rating) && !horseData.rating) {
                                            horseData.rating = rating;
                                        }
                                    }
                                }

                                if (Object.keys(horseData).length > 1) {
                                    data[horseName] = horseData;
                                }
                            }
                        }
                    }

                    // Also look for any div elements with horse data
                    const horseElements = document.querySelectorAll('[class*="horse"], [class*="selection"], [class*="pick"]');
                    for (const element of horseElements) {
                        const text = element.textContent;
                        // Extract horse names and associated data
                        // This would need to be customized based on actual HTML structure
                    }

                    return data;
                }
            ''')

            return smartpick_data

        except Exception as e:
            print(f"Error extracting SmartPick data: {e}")
            return {}

    def parse_smartpick_data(self, soup: BeautifulSoup) -> Dict:
        """Parse SmartPick data from HTML (fallback method)"""
        try:
            smartpick_data = {}

            # Look for tables with SmartPick data
            tables = soup.find_all('table')

            for table in tables:
                # Check if this table has horse data
                rows = table.find_all('tr')
                if not rows:
                    continue

                # Look for header row to identify the table structure
                header_row = rows[0] if rows else None
                if not header_row:
                    continue

                headers = [th.get_text(strip=True).upper() for th in header_row.find_all(['th', 'td'])]

                # Look for tables with horse names and ratings
                if any(h in ['HORSE', 'NAME', 'SELECTION'] for h in headers):
                    # Parse data rows
                    for row in rows[1:]:
                        cells = row.find_all(['td', 'th'])
                        if len(cells) < 2:
                            continue

                        horse_name = cells[0].get_text(strip=True)
                        if not horse_name or horse_name.upper() in ['HORSE', 'NAME', 'SELECTION']:
                            continue

                        # Extract various data points
                        horse_data = {'horse_name': horse_name}

                        # Look for numerical data in subsequent cells
                        for i, cell in enumerate(cells[1:], 1):
                            cell_text = cell.get_text(strip=True)

                            # Try to extract percentages
                            if '%' in cell_text:
                                try:
                                    pct = float(cell_text.replace('%', ''))
                                    if i == 1:  # First data column might be win %
                                        horse_data['win_pct'] = pct
                                    elif 'combo_win_pct' not in horse_data:
                                        horse_data['combo_win_pct'] = pct
                                except:
                                    pass

                            # Try to extract odds
                            elif '/' in cell_text or '-' in cell_text:
                                horse_data['odds'] = cell_text

                            # Try to extract numerical ratings
                            else:
                                try:
                                    rating = float(cell_text)
                                    if 'rating' not in horse_data:
                                        horse_data['rating'] = rating
                                except:
                                    pass

                        if horse_data and len(horse_data) > 1:  # More than just horse name
                            smartpick_data[horse_name] = horse_data

            return smartpick_data

        except Exception as e:
            print(f"Error parsing SmartPick data: {e}")
            return {}

    async def scrape_multiple_horses(self, horses_data: List[Tuple[str, str]]) -> Dict[str, Dict]:
        """Scrape multiple horses with rate limiting"""
        results = {}

        for i, (horse_name, profile_url) in enumerate(horses_data):
            print(f"Scraping {horse_name} ({i+1}/{len(horses_data)})...")

            result = await self.scrape_horse_profile(horse_name, profile_url)
            if "error" not in result:
                results[horse_name] = result
            else:
                print(f"Failed to scrape {horse_name}: {result['error']}")

            # Rate limiting between requests
            if i < len(horses_data) - 1:
                await self.human_like_delay(3000, 8000)

        return results


# Usage example
async def main():
    # Example with residential proxies (you'd need to configure these)
    proxies = [
        # ProxyConfig("http://proxy1.example.com:8080", "user", "pass"),
        # ProxyConfig("http://proxy2.example.com:8080", "user", "pass"),
    ]

    async with PlaywrightEquibaseScraper(proxies) as scraper:
        result = await scraper.scrape_horse_profile(
            "Curvino",
            "https://www.equibase.com/profiles/Results.cfm?type=Horse&refno=11171854&registry=T"
        )
        print(json.dumps(result, indent=2))


# Integration function for existing pipeline
async def scrape_horses_playwright(horses_with_urls: List[Tuple[str, str]]) -> Dict[str, Dict]:
    """
    Integration function for existing pipeline.

    Args:
        horses_with_urls: List of (horse_name, profile_url) tuples

    Returns:
        Dict mapping horse names to their scraped data
    """
    async with PlaywrightEquibaseScraper() as scraper:
        return await scraper.scrape_multiple_horses(horses_with_urls)


if __name__ == "__main__":
    asyncio.run(main())
