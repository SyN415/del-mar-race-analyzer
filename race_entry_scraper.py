#!/usr/bin/env python3
"""
Race Entry Scraper for Equibase
Scrapes individual race entry pages to get jockey/trainer names and odds
URL format: https://www.equibase.com/static/entry/DMR082425USA1-EQB.html
"""

import json
import re
from datetime import datetime
from typing import Dict, List, Optional
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import requests

class RaceEntryScraper:
    def __init__(self):
        self.base_url = "https://www.equibase.com/static/entry/"

    def build_race_entry_url(self, track_code: str, date: str, country: str, race_number: int) -> str:
        """
        Build race entry URL
        Format: DMR082425USA1-EQB.html
        """
        # Convert date from MM/DD/YYYY to MMDDYY format
        date_obj = datetime.strptime(date, "%m/%d/%Y")
        formatted_date = date_obj.strftime("%m%d%y")

        filename = f"{track_code}{formatted_date}{country}{race_number}-EQB.html"
        return f"{self.base_url}{filename}"

    def build_card_overview_url(self, track_code: str, date: str, country: str) -> str:
        """Build the all-races card overview URL using ?SAP=viewe2 suffix."""
        date_obj = datetime.strptime(date, "%m/%d/%Y")
        formatted_date = date_obj.strftime("%m%d%y")
        # Example: https://www.equibase.com/static/entry/DMR082425USA-EQB.html?SAP=viewe2
        return f"{self.base_url}{track_code}{formatted_date}{country}-EQB.html?SAP=viewe2"

    async def _accept_cookies(self, page) -> None:
        try:
            btn = await page.query_selector('#onetrust-accept-btn-handler')
            if btn:
                await btn.click()
        except Exception:
            pass

    def parse_card_overview(self, html: str) -> List[Dict]:
        """
        Parse the card overview HTML to extract per-race horse lists and profile URLs.
        Strategy: Walk DOM in order, track the current race when encountering text 'Race N',
        and collect anchors to horse Results.cfm links under that race section.
        Returns: [{ 'race_number': N, 'horses': [{'name': n, 'profile_url': u}], 'horse_count': k }]
        """
        soup = BeautifulSoup(html or "", 'html.parser')
        races: Dict[int, List[Tuple[str, str]]] = {}
        current_race = None
        # Iterate all elements in document order
        for el in soup.find_all(True):
            txt = el.get_text(" ", strip=True) if el else ""
            if txt:
                m = re.search(r"\bRace\s+(\d{1,2})\b", txt, re.I)
                if m:
                    try:
                        rn = int(m.group(1))
                        current_race = rn
                        races.setdefault(rn, [])
                        continue
                    except Exception:
                        pass
            if el.name == 'a' and el.has_attr('href') and 'Results.cfm' in el['href'] and 'type=Horse' in el['href']:
                name = el.get_text(strip=True) or ''
                href = el['href']
                url = href if href.startswith('http') else f"https://www.equibase.com{href if href.startswith('/') else '/' + href}"
                if current_race is not None and name:
                    races.setdefault(current_race, [])
                    races[current_race].append((name, url))
        # Build structured list
        out: List[Dict] = []
        for rn in sorted(races.keys()):
            pairs = races[rn]
            # Deduplicate per name preserving order
            seen = set()
            horses = []
            for n, u in pairs:
                if n not in seen:
                    horses.append({'name': n, 'profile_url': u})
                    seen.add(n)
            out.append({'race_number': rn, 'horses': horses, 'horse_count': len(horses)})
        return out

    def fetch_overview_requests(self, url: str) -> str:
        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36"}, timeout=25)
            if r.status_code == 200 and r.text and 'incapsula' not in r.text.lower():
                return r.text
        except Exception:
            pass
        return ""

    async def scrape_card_overview(self, track_code: str, date: str, country: str) -> Dict:
        """Fetch and parse the ?SAP=viewe2 overview page into per-race lists."""
        url = self.build_card_overview_url(track_code, date, country)
        html = self.fetch_overview_requests(url)
        if not html:
            # Fallback to Playwright rendering
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36",
                    locale="en-US",
                    timezone_id="America/Los_Angeles",
                )
                page = await context.new_page()
                try:
                    await page.goto("https://www.equibase.com", wait_until="domcontentloaded", timeout=30000)
                    await self._accept_cookies(page)
                    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    try:
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight/2);")
                    except Exception:
                        pass
                    html = await page.content()
                finally:
                    await browser.close()
        per_race = self.parse_card_overview(html)
        return {'track': track_code, 'date': date, 'url': url, 'races': per_race, 'total_races': len(per_race)}

    async def scrape_race_entry(self, track_code: str, date: str, country: str, race_number: int) -> Dict:
        """Scrape a single race entry page (with cookie accept and resilient waits)."""
        url = self.build_race_entry_url(track_code, date, country, race_number)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36",
                locale="en-US",
                timezone_id="America/Los_Angeles",
            )
            page = await context.new_page()

            try:
                print(f"Scraping race {race_number}: {url}")
                # Visit base to accept cookies first
                await page.goto("https://www.equibase.com", wait_until="domcontentloaded", timeout=30000)
                await self._accept_cookies(page)
                # Navigate to entry URL with a more permissive wait
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                try:
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight/2);")
                except Exception:
                    pass

                # Extract race information and entries
                race_info = await self.extract_race_info(page)
                entries = await self.extract_entries(page)

                return {
                    "race_number": race_number,
                    "url": url,
                    "race_info": race_info,
                    "entries": entries,
                    "scraped_at": datetime.now().isoformat()
                }

            except Exception as e:
                print(f"Error scraping race {race_number}: {str(e)}")
                return {
                    "race_number": race_number,
                    "url": url,
                    "error": str(e),
                    "scraped_at": datetime.now().isoformat()
                }
            finally:
                await browser.close()

    async def extract_race_info(self, page) -> Dict:
        """Extract general race information"""
        race_info = {}
        
        try:
            # Race title and conditions
            title_element = await page.query_selector('h1, .race-title, .race-header')
            if title_element:
                race_info['title'] = await title_element.text_content()
            
            # Race conditions/description
            conditions_element = await page.query_selector('.race-conditions, .conditions')
            if conditions_element:
                race_info['conditions'] = await conditions_element.text_content()
                
        except Exception as e:
            print(f"Error extracting race info: {str(e)}")
            
        return race_info
    
    async def extract_entries(self, page) -> List[Dict]:
        """Extract horse entries with jockey, trainer, and odds"""
        entries = []
        
        try:
            # Look for the main entries table
            table_rows = await page.query_selector_all('tr')
            
            for row in table_rows:
                entry = await self.extract_entry_from_row(row)
                if entry and entry.get('program_number'):
                    entries.append(entry)
                    
        except Exception as e:
            print(f"Error extracting entries: {str(e)}")
            
        return entries
    
    async def extract_entry_from_row(self, row) -> Optional[Dict]:
        """Extract entry data from a table row"""
        try:
            cells = await row.query_selector_all('td')
            if len(cells) < 4:  # Need at least program number, horse, jockey, trainer
                return None
            
            entry = {}
            
            # Try to extract program number (usually first cell)
            program_cell = cells[0] if cells else None
            if program_cell:
                program_text = await program_cell.text_content()
                program_match = re.search(r'\d+', program_text.strip())
                if program_match:
                    entry['program_number'] = program_match.group()
            
            # Extract horse name (usually second cell or has horse link)
            for cell in cells:
                horse_link = await cell.query_selector('a[href*="horse"]')
                if horse_link:
                    entry['horse_name'] = await horse_link.text_content()
                    break
            
            # Extract jockey name
            for cell in cells:
                jockey_link = await cell.query_selector('a[href*="jockey"], a[href*="People"][href*="J"]')
                if jockey_link:
                    entry['jockey'] = await jockey_link.text_content()
                    break
            
            # Extract trainer name  
            for cell in cells:
                trainer_link = await cell.query_selector('a[href*="trainer"], a[href*="People"][href*="T"]')
                if trainer_link:
                    entry['trainer'] = await trainer_link.text_content()
                    break
            
            # Extract odds (look for patterns like 5-1, 3/2, etc.)
            for cell in cells:
                cell_text = await cell.text_content()
                odds_match = re.search(r'\d+[-/]\d+|\d+\.\d+', cell_text)
                if odds_match:
                    entry['odds'] = odds_match.group()
                    break
            
            # Extract weight
            for cell in cells:
                cell_text = await cell.text_content()
                weight_match = re.search(r'1\d{2}', cell_text)  # Weight usually 110-126
                if weight_match:
                    entry['weight'] = weight_match.group()
                    break
            
            return entry if entry.get('program_number') else None
            
        except Exception as e:
            print(f"Error extracting entry from row: {str(e)}")
            return None

async def scrape_del_mar_race_entries(date: str = "08/24/2025", num_races: int = 11):
    """Scrape all race entries for Del Mar on a given date"""
    scraper = RaceEntryScraper()
    all_races = []
    
    for race_num in range(1, num_races + 1):
        race_data = await scraper.scrape_race_entry("DMR", date, "USA", race_num)
        all_races.append(race_data)
        
        # Small delay between requests
        await asyncio.sleep(1)
    
    # Save to file
    filename = f"del_mar_race_entries_{date.replace('/', '_')}.json"
    with open(filename, 'w') as f:
        json.dump(all_races, f, indent=2)
    
    print(f"Scraped {len(all_races)} races and saved to {filename}")
    return all_races

if __name__ == "__main__":
    asyncio.run(scrape_del_mar_race_entries())
