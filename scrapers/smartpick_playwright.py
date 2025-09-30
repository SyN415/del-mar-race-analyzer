#!/usr/bin/env python3
"""
Playwright-based SmartPick scraper to bypass Incapsula WAF.
Replaces the requests-based SmartPickRaceScraper with Playwright.
Includes 2Captcha integration for solving hCaptcha challenges.
"""
import asyncio
import logging
import re
from typing import Dict, List, Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Import captcha solver
try:
    from services.captcha_solver import get_captcha_solver, solve_equibase_captcha
    CAPTCHA_SOLVER_AVAILABLE = True
except ImportError:
    logger.warning("⚠️  Captcha solver not available - captcha challenges will fail")
    CAPTCHA_SOLVER_AVAILABLE = False


class PlaywrightSmartPickScraper:
    """Playwright-based SmartPick scraper that bypasses WAF and solves captchas"""

    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.captcha_solver = get_captcha_solver() if CAPTCHA_SOLVER_AVAILABLE else None
        self.session_established = False
    
    async def __aenter__(self):
        """Async context manager entry"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled'
            ]
        )
        self.context = await self.browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='en-US',
            timezone_id='America/Los_Angeles'
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
    
    async def scrape_race(self, track_id: str, race_date: str, race_number: int, day: str = "D") -> Dict[str, Dict]:
        """
        Scrape SmartPick data for a single race using Playwright

        Args:
            track_id: Track code (e.g., 'DMR', 'SA')
            race_date: Date in MM/DD/YYYY format
            race_number: Race number (1-12)
            day: 'D' for day or 'E' for evening

        Returns:
            Dict mapping horse names to their data
        """
        # Validate date format and check if it's not too far in the future
        from datetime import datetime, timedelta
        try:
            race_dt = datetime.strptime(race_date, '%m/%d/%Y')
            today = datetime.now()
            if race_dt > today + timedelta(days=30):
                logger.warning(f"⚠️  Race date {race_date} is more than 30 days in the future - data may not be available")
            elif race_dt < today - timedelta(days=365):
                logger.warning(f"⚠️  Race date {race_date} is more than 1 year in the past - data may not be available")
        except ValueError:
            logger.error(f"❌ Invalid date format: {race_date} (expected MM/DD/YYYY)")
            return {}

        # URL encode the date properly
        import urllib.parse
        encoded_date = urllib.parse.quote(race_date)
        url = f"https://www.equibase.com/smartPick/smartPick.cfm/?trackId={track_id}&raceDate={encoded_date}&country=USA&dayEvening={day}&raceNumber={race_number}"

        logger.info(f"🌐 Fetching SmartPick URL: {url}")
        logger.info(f"📅 Race date: {race_date} (encoded: {encoded_date})")
        
        try:
            page = await self.context.new_page()

            # CRITICAL: Visit homepage first to establish session and solve captcha
            if not self.session_established:
                logger.info("🏠 Visiting Equibase homepage to establish session...")
                try:
                    await page.goto('https://www.equibase.com', wait_until='domcontentloaded', timeout=30000)
                    await page.wait_for_timeout(2000)

                    # Solve captcha if present
                    if CAPTCHA_SOLVER_AVAILABLE and self.captcha_solver:
                        captcha_solved = await solve_equibase_captcha(page, self.captcha_solver)
                        if captcha_solved:
                            logger.info("✅ Session established with captcha solved")
                            self.session_established = True
                        else:
                            logger.error("❌ Failed to solve captcha on homepage")
                            return {}
                    else:
                        logger.warning("⚠️  No captcha solver available - proceeding without solving")

                    # Accept cookies
                    try:
                        cookie_button = await page.query_selector('#onetrust-accept-btn-handler')
                        if cookie_button:
                            await cookie_button.click()
                            logger.info("🍪 Accepted cookies")
                            await page.wait_for_timeout(1000)
                    except Exception as e:
                        logger.info(f"ℹ️  No cookie banner or already accepted: {e}")
                except Exception as e:
                    logger.warning(f"⚠️  Could not visit homepage: {e}")
            else:
                logger.info("ℹ️  Session already established, skipping homepage visit")

            # Now navigate to SmartPick page
            logger.info(f"🎯 Navigating to SmartPick page...")
            response = await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            logger.info(f"📡 HTTP Status: {response.status}")

            # Wait a bit for page to load
            await page.wait_for_timeout(3000)

            # Check page content for Incapsula/captcha challenges
            page_content = await page.content()
            page_title = await page.title()

            # Detect if we're on a challenge page
            is_challenge_page = (
                'incapsula' in page_content.lower() or
                'imperva' in page_content.lower() or
                'additional security check' in page_content.lower() or
                page_title == '' or
                'Request unsuccessful' in page_content
            )

            if is_challenge_page:
                logger.warning("🛡️  Challenge page detected - attempting to solve...")

                # Check for captcha on SmartPick page
                if CAPTCHA_SOLVER_AVAILABLE and self.captcha_solver:
                    await page.wait_for_timeout(2000)
                    captcha_solved = await solve_equibase_captcha(page, self.captcha_solver)
                    if not captcha_solved:
                        logger.error("❌ Failed to solve captcha on SmartPick page")
                        return {}

                    # Wait for page to reload after captcha
                    logger.info("⏳ Waiting for page to reload after captcha...")
                    await page.wait_for_timeout(5000)
                    await page.wait_for_load_state('domcontentloaded', timeout=30000)
                else:
                    logger.error("❌ Challenge page detected but no captcha solver available")
                    return {}
            else:
                logger.info("✅ No challenge page detected, proceeding with scraping")

            # Wait for network to be idle after captcha solving
            try:
                await page.wait_for_load_state('networkidle', timeout=10000)
            except Exception as e:
                logger.warning(f"⚠️  Network did not reach idle state: {e}")

            # Wait for Angular/React to render - much longer timeout
            logger.info("⏳ Waiting for JavaScript to render horse data...")
            await page.wait_for_timeout(8000)

            # Try multiple selectors that might contain horse data
            horse_data_loaded = False
            selectors_to_try = [
                'a[href*="Results.cfm"]',
                'a[href*="type=Horse"]',
                'table tr:nth-child(2)',  # Wait for data rows in tables
                '[ng-repeat]',  # Angular
                '[data-horse]',  # Common data attribute
                '.horse-name',
                '.runner'
            ]

            for selector in selectors_to_try:
                try:
                    await page.wait_for_selector(selector, timeout=3000)
                    logger.info(f"✅ Found content with selector: {selector}")
                    horse_data_loaded = True
                    break
                except Exception:
                    continue

            if not horse_data_loaded:
                logger.warning("⚠️  No horse data selectors found - trying longer wait")
                # Wait even longer for AJAX to complete
                await page.wait_for_timeout(10000)

                # Check network activity
                logger.info("🌐 Checking for AJAX requests...")
                await page.wait_for_load_state('networkidle', timeout=10000)
            
            # Try to extract data via JavaScript before getting HTML
            logger.info("🔍 Attempting to extract data via JavaScript...")
            try:
                # Check if Angular is present
                angular_data = await page.evaluate('''
                    () => {
                        // Try to find Angular scope
                        const angularElement = document.querySelector('[ng-controller], [ng-app]');
                        if (angularElement && window.angular) {
                            const scope = window.angular.element(angularElement).scope();
                            if (scope && scope.horses) {
                                return { source: 'angular', horses: scope.horses };
                            }
                        }

                        // Try to find horse links in DOM
                        const horseLinks = Array.from(document.querySelectorAll('a[href*="Results.cfm"]'));
                        if (horseLinks.length > 0) {
                            return {
                                source: 'dom',
                                count: horseLinks.length,
                                samples: horseLinks.slice(0, 5).map(a => ({
                                    text: a.textContent.trim(),
                                    href: a.href
                                }))
                            };
                        }

                        return { source: 'none', message: 'No horse data found' };
                    }
                ''')
                logger.info(f"📊 JavaScript extraction result: {angular_data}")
            except Exception as e:
                logger.warning(f"⚠️  JavaScript extraction failed: {e}")

            # Get HTML content
            html = await page.content()
            logger.info(f"📄 Response length: {len(html)} bytes")

            # Get page title and URL for debugging
            title = await page.title()
            current_url = page.url
            logger.info(f"📰 Page title: {title}")
            logger.info(f"🔗 Current URL: {current_url}")

            # Check if we were redirected
            if current_url != url:
                logger.warning(f"⚠️  Page was redirected from {url} to {current_url}")

            # Re-check for challenge page after potential reload
            page_content = await page.content()
            page_title = await page.title()

            is_still_challenge = (
                'incapsula' in page_content.lower() or
                'imperva' in page_content.lower() or
                'additional security check' in page_content.lower() or
                page_title == '' or
                'Request unsuccessful' in page_content
            )

            if is_still_challenge:
                logger.error("❌ Still on challenge page after captcha attempt - scraping failed")
                logger.info(f"📰 Page title: {page_title}")
                logger.info(f"📝 First 500 chars: {page_content[:500]}")
                await page.close()
                return {}

            # Check for specific text that indicates the page loaded correctly
            page_text = await page.evaluate('() => document.body.innerText')
            if 'SmartPick' in page_text or 'smartpick' in page_text.lower():
                logger.info("✅ SmartPick content detected in page")
            else:
                logger.warning("⚠️  No SmartPick content detected - page may not have loaded correctly")
                logger.info(f"📝 First 500 chars of page text: {page_text[:500]}")

            # Check for "no data" messages
            page_text_lower = page_text.lower()
            no_data_messages = [
                'no entries', 'no races', 'not available', 'no data', 'no results',
                'no race card', 'no racing', 'not found', 'does not exist',
                'no information available', 'no smartpick data'
            ]
            if any(msg in page_text_lower for msg in no_data_messages):
                logger.warning(f"⚠️  Page indicates no race data available for {track_id} on {race_date}")
                logger.info(f"📝 Page text snippet: {page_text[:1000]}")
                await page.close()
                return {}

            # Check if the page shows a different date or track
            date_variations = [
                race_date,  # 09/28/2025
                race_date.replace('/', ''),  # 09282025
                race_date.replace('/', '-'),  # 09-28-2025
            ]
            date_found = any(d in page_text for d in date_variations)

            if not date_found:
                logger.warning(f"⚠️  Expected date {race_date} not found in page content")
                # Look for any dates in the page
                import re
                dates_in_page = re.findall(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', page_text[:2000])
                if dates_in_page:
                    logger.info(f"📅 Dates found in page: {dates_in_page[:5]}")
                else:
                    logger.warning("📅 No dates found in page content")

            if track_id not in page_text:
                logger.warning(f"⚠️  Expected track {track_id} not found in page content")
                # Look for track codes in the page
                track_codes = re.findall(r'\b[A-Z]{2,3}\b', page_text[:2000])
                logger.info(f"🏇 Track codes found in page: {list(set(track_codes))[:10]}")

            # Try scrolling to trigger lazy loading
            try:
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await page.wait_for_timeout(2000)
                logger.info("📜 Scrolled page to trigger lazy loading")
            except Exception as e:
                logger.warning(f"⚠️  Could not scroll page: {e}")

            # Look for specific SmartPick table or container
            try:
                smartpick_container = await page.query_selector('.smartpick-container, #smartpick, [class*="smartpick"], [id*="smartpick"]')
                if smartpick_container:
                    logger.info("✅ Found SmartPick container element")
                else:
                    logger.warning("⚠️  No SmartPick container element found")
            except Exception as e:
                logger.warning(f"⚠️  Error looking for SmartPick container: {e}")
            
            # Save HTML and screenshot for debugging
            try:
                import os
                os.makedirs('logs/html', exist_ok=True)
                with open(f'logs/html/smartpick_playwright_{track_id}_r{race_number}.html', 'w', encoding='utf-8') as f:
                    f.write(html)
                logger.info(f"📝 Saved HTML to logs/html/smartpick_playwright_{track_id}_r{race_number}.html")

                # Take screenshot
                await page.screenshot(path=f'logs/html/smartpick_playwright_{track_id}_r{race_number}.png', full_page=True)
                logger.info(f"📸 Saved screenshot to logs/html/smartpick_playwright_{track_id}_r{race_number}.png")
            except Exception as e:
                logger.warning(f"⚠️  Could not save HTML/screenshot: {e}")
            
            await page.close()
            
            # Parse the HTML
            horses = self.parse_smartpick_html(html)
            logger.info(f"🐎 Found {len(horses)} horses in race {race_number}")
            
            return horses
            
        except Exception as e:
            logger.error(f"❌ Error scraping race {race_number}: {e}")
            return {}
    
    def parse_smartpick_html(self, html: str) -> Dict[str, Dict]:
        """
        Parse SmartPick HTML to extract horse data
        
        Returns:
            Dict mapping horse names to their SmartPick data
        """
        horses = {}
        
        if not html:
            logger.warning("⚠️  No HTML content to parse")
            return horses
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Check for blocked/error pages
        page_text = soup.get_text().lower()
        if 'incapsula' in page_text or 'access denied' in page_text:
            logger.error("🚫 Page appears to be blocked by WAF")
            return horses

        # Check for various "no data" messages
        no_data_indicators = [
            'no entries', 'not available', 'no data', 'no results',
            'no race card', 'no racing', 'not found', 'does not exist',
            'no information available', 'no smartpick data', 'no races scheduled'
        ]
        if any(indicator in page_text for indicator in no_data_indicators):
            logger.info(f"ℹ️  Page indicates no race data available (found: {[i for i in no_data_indicators if i in page_text]})")
            return horses
        
        # Find all horse profile links
        horse_links = soup.find_all('a', href=True)
        logger.info(f"🔍 Found {len(horse_links)} total links")

        # Debug: Show sample of link hrefs to understand structure
        sample_hrefs = [a.get('href', '')[:100] for a in horse_links[:20]]
        logger.info(f"📋 Sample hrefs: {sample_hrefs}")

        # Look for Results.cfm links
        results_links = [a for a in horse_links if 'Results.cfm' in a.get('href', '')]
        logger.info(f"🔗 Found {len(results_links)} Results.cfm links")

        # Look for type=Horse links
        horse_type_links = [a for a in horse_links if 'type=Horse' in a.get('href', '')]
        logger.info(f"🐴 Found {len(horse_type_links)} type=Horse links")

        # Look for any horse-related patterns
        horse_patterns = ['horse', 'Horse', 'HORSE', 'refno=', 'registry=']
        pattern_links = [a for a in horse_links if any(p in a.get('href', '') for p in horse_patterns)]
        logger.info(f"🔍 Found {len(pattern_links)} links with horse-related patterns")
        if pattern_links:
            logger.info(f"📋 Sample horse-pattern hrefs: {[a.get('href', '')[:100] for a in pattern_links[:5]]}")

        # Combined filter
        results_links = [a for a in horse_links if 'Results.cfm' in a.get('href', '') and 'type=Horse' in a.get('href', '')]
        logger.info(f"🐎 Found {len(results_links)} horse profile links (Results.cfm + type=Horse)")

        # Check for tables with horse data
        tables = soup.find_all('table')
        logger.info(f"📊 Found {len(tables)} tables on page")
        if tables:
            for i, table in enumerate(tables[:3]):  # Check first 3 tables
                rows = table.find_all('tr')
                logger.info(f"  Table {i+1}: {len(rows)} rows")
                if rows:
                    first_row_text = rows[0].get_text(strip=True)[:100]
                    logger.info(f"    First row: {first_row_text}")
        
        for link in results_links:
            try:
                horse_name = link.get_text(strip=True)
                if not horse_name:
                    continue
                
                href = link['href']
                profile_url = href if href.startswith('http') else f"https://www.equibase.com{href if href.startswith('/') else '/' + href}"
                
                # Extract refno and registry from URL
                refno, registry = self.parse_refno_registry(profile_url)
                
                # Look for Jockey/Trainer combo win percentage
                combo_win_pct = None
                parent = link.parent
                for _ in range(3):  # Check up to 3 parent levels
                    if parent:
                        text = parent.get_text(' ', strip=True)
                        match = re.search(r'Jockey\s*/\s*Trainer\s*Win\s*%\s*(\d{1,3})%', text, re.I)
                        if match:
                            combo_win_pct = int(match.group(1))
                            break
                        parent = parent.parent
                
                horses[horse_name] = {
                    'smartpick': {
                        'combo_win_pct': combo_win_pct
                    },
                    'profile_url': profile_url,
                    'refno': refno,
                    'registry': registry
                }
                
                logger.info(f"  ✅ Parsed: {horse_name} (combo: {combo_win_pct}%)")
                
            except Exception as e:
                logger.warning(f"⚠️  Error parsing horse link: {e}")
                continue
        
        logger.info(f"📊 Total horses parsed: {len(horses)}")
        return horses
    
    def parse_refno_registry(self, url: str) -> tuple:
        """Extract refno and registry from profile URL"""
        if not url:
            return None, None
        match = re.search(r'refno=(\d+).*?registry=([A-Za-z])', url)
        if match:
            return match.group(1), match.group(2)
        return None, None


async def scrape_smartpick_with_playwright(track_id: str, race_date: str, race_number: int, day: str = "D") -> Dict[str, Dict]:
    """
    Convenience function to scrape a single race with Playwright
    
    Args:
        track_id: Track code (e.g., 'DMR', 'SA')
        race_date: Date in MM/DD/YYYY format
        race_number: Race number
        day: 'D' for day or 'E' for evening
        
    Returns:
        Dict mapping horse names to their data
    """
    async with PlaywrightSmartPickScraper() as scraper:
        return await scraper.scrape_race(track_id, race_date, race_number, day)


async def scrape_multiple_races_playwright(track_id: str, race_date: str, num_races: int, day: str = "D") -> Dict[int, Dict[str, Dict]]:
    """
    Scrape multiple races efficiently with a single browser instance
    
    Args:
        track_id: Track code
        race_date: Date in MM/DD/YYYY format
        num_races: Number of races to scrape
        day: 'D' for day or 'E' for evening
        
    Returns:
        Dict mapping race numbers to horse data
    """
    all_races = {}
    
    async with PlaywrightSmartPickScraper() as scraper:
        for race_num in range(1, num_races + 1):
            logger.info(f"📊 Scraping SmartPick Race {race_num}...")
            horses = await scraper.scrape_race(track_id, race_date, race_num, day)
            if horses:
                all_races[race_num] = horses
                logger.info(f"  ✅ Found {len(horses)} horses in race {race_num}")
            else:
                logger.warning(f"  ⚠️  No data found for race {race_num}")
            
            # Small delay between races
            await asyncio.sleep(2)
    
    return all_races


if __name__ == "__main__":
    # Test the scraper
    async def test():
        result = await scrape_smartpick_with_playwright('SA', '09/28/2025', 1, 'D')
        print(f"Found {len(result)} horses")
        for name, data in result.items():
            print(f"  {name}: {data}")
    
    asyncio.run(test())

