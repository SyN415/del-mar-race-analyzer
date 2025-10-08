#!/usr/bin/env python3
"""
Fix for SmartPick scraper - addresses the Angular/JavaScript rendering issue
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


class FixedPlaywrightSmartPickScraper:
    """Fixed SmartPick scraper that properly handles Angular/JavaScript rendering"""

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
                '--disable-blink-features=AutomationControlled',
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor',
                '--disable-infobars',
                '--window-size=1920,1080',
                '--start-maximized',
                '--disable-extensions',
                '--no-first-run',
                '--no-default-browser-check',
                '--disable-background-timer-throttling',
                '--disable-backgrounding-occluded-windows',
                '--disable-renderer-backgrounding'
            ]
        )
        self.context = await self.browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='en-US',
            timezone_id='America/Los_Angeles',
            # Add more realistic browser context
            extra_http_headers={
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Cache-Control': 'max-age=0'
            }
        )

        # Add stealth scripts to hide automation
        await self.context.add_init_script("""
            // Overwrite the `navigator.webdriver` property
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });

            // Overwrite the `plugins` property to use a custom getter
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });

            // Overwrite the `languages` property to use a custom getter
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });

            // Overwrite the `chrome` property
            window.chrome = {
                runtime: {}
            };

            // Add realistic permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
        """)

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
        Scrape SmartPick data for a single race using Playwright with proper Angular handling
        
        Args:
            track_id: Track code (e.g., 'DMR', 'SA')
            race_date: Date in MM/DD/YYYY format
            race_number: Race number (1-12)
            day: 'D' for day or 'E' for evening
        
        Returns:
            Dict mapping horse names to their data
        """
        # Validate date format
        from datetime import datetime, timedelta
        try:
            race_dt = datetime.strptime(race_date, '%m/%d/%Y')
            today = datetime.now()
            if race_dt > today + timedelta(days=30):
                logger.warning(f"⚠️  Race date {race_date} is more than 30 days in the future")
            elif race_dt < today - timedelta(days=365):
                logger.warning(f"⚠️  Race date {race_date} is more than 1 year in the past")
        except ValueError:
            logger.error(f"❌ Invalid date format: {race_date} (expected MM/DD/YYYY)")
            return {}

        # URL encode the date properly
        import urllib.parse
        encoded_date = urllib.parse.quote(race_date)
        url = f"https://www.equibase.com/smartPick/smartPick.cfm/?trackId={track_id}&raceDate={encoded_date}&country=USA&dayEvening={day}&raceNumber={race_number}"

        logger.info(f"🌐 Fetching SmartPick URL: {url}")
        
        try:
            page = await self.context.new_page()

            # Capture console messages and errors
            console_messages = []
            page.on('console', lambda msg: console_messages.append(f"[{msg.type}] {msg.text}"))
            page.on('pageerror', lambda exc: logger.error(f"🔴 JavaScript error: {exc}"))

            # CRITICAL: Visit homepage first to establish session
            if not self.session_established:
                logger.info("🏠 Visiting Equibase homepage to establish session...")
                try:
                    await page.goto('https://www.equibase.com', wait_until='domcontentloaded', timeout=30000)
                    await page.wait_for_timeout(3000)  # Increased wait time

                    # Simulate human behavior - scroll a bit
                    await page.evaluate('window.scrollTo(0, 300)')
                    await page.wait_for_timeout(500)
                    await page.evaluate('window.scrollTo(0, 0)')
                    await page.wait_for_timeout(500)

                    # Accept cookies
                    try:
                        cookie_button = await page.query_selector('#onetrust-accept-btn-handler')
                        if cookie_button:
                            await cookie_button.click()
                            logger.info("🍪 Accepted cookies")
                            await page.wait_for_timeout(1500)
                    except Exception as e:
                        logger.info(f"ℹ️  No cookie banner or already accepted: {e}")

                    # Wait a bit more to seem more human
                    await page.wait_for_timeout(2000)
                except Exception as e:
                    logger.warning(f"⚠️  Could not visit homepage: {e}")
                else:
                    self.session_established = True

            # Now navigate to SmartPick page
            logger.info(f"🎯 Navigating to SmartPick page...")

            # Add a small delay before navigation to seem more human
            await page.wait_for_timeout(1000)

            response = await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            logger.info(f"📡 HTTP Status: {response.status}")

            # Wait a bit after page load
            await page.wait_for_timeout(2000)

            # Wait for Angular app to initialize and load data
            logger.info("⏳ Waiting for Angular app to initialize...")
            await page.wait_for_timeout(5000)
            
            # Check if we're on an Incapsula challenge page
            page_content = await page.content()
            if 'incapsula' in page_content.lower() or 'imperva' in page_content.lower():
                logger.warning("🛡️  Challenge page detected - attempting to solve...")
                
                if CAPTCHA_SOLVER_AVAILABLE and self.captcha_solver:
                    captcha_solved = await solve_equibase_captcha(page, self.captcha_solver)
                    if not captcha_solved:
                        logger.error("❌ Failed to solve captcha")
                        return {}

                    # Wait for page to reload after captcha
                    logger.info("⏳ Waiting for page to reload after captcha...")
                    await page.wait_for_timeout(3000)

                    # Wait for network to settle after captcha
                    try:
                        await page.wait_for_load_state('networkidle', timeout=15000)
                        logger.info("✅ Network idle after captcha")
                    except Exception as e:
                        logger.warning(f"⚠️  Network idle timeout after captcha: {e}")

                    # Additional wait for Angular to fetch and render data
                    logger.info("⏳ Waiting for Angular to fetch race data...")
                    await page.wait_for_timeout(10000)  # Increased from 5s to 10s
                else:
                    logger.error("❌ Challenge page detected but no captcha solver available")
                    return {}

            # CRITICAL FIX: Wait for Angular app to render the horse data
            logger.info("⏳ Waiting for Angular app to render horse data...")

            # Wait for the app-root element to be present (don't require visible)
            try:
                await page.wait_for_selector('app-root', state='attached', timeout=10000)
                logger.info("✅ Found app-root element in DOM")

                # Check if it's hidden
                is_hidden = await page.evaluate('''
                    () => {
                        const appRoot = document.querySelector('app-root');
                        if (!appRoot) return true;
                        const style = window.getComputedStyle(appRoot);
                        return style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0';
                    }
                ''')
                if is_hidden:
                    logger.warning("⚠️  app-root element is hidden - Angular may not have rendered")
                else:
                    logger.info("✅ app-root element is visible")
            except Exception as e:
                logger.warning(f"⚠️  Could not find app-root: {e}")

            # Wait for Angular to finish rendering - this is the key fix
            try:
                await page.wait_for_load_state('networkidle', timeout=15000)
                logger.info("✅ Network idle state reached")
            except Exception as e:
                logger.warning(f"⚠️  Network idle timeout: {e}")
            
            # Additional wait for dynamic content
            await page.wait_for_timeout(8000)

            # Log console messages to help debug
            if console_messages:
                logger.info(f"📝 Console messages ({len(console_messages)} total):")
                for msg in console_messages[:10]:  # Show first 10
                    logger.info(f"  {msg}")

            # Check what's actually in the page
            page_title = await page.title()
            logger.info(f"📄 Page title: {page_title}")

            # Check for error messages in the page
            page_text = await page.evaluate('() => document.body.innerText')
            if 'no entries' in page_text.lower() or 'not available' in page_text.lower():
                logger.warning(f"⚠️  Page indicates no data available")

            # CRITICAL: Wait for horse data to actually appear in the DOM
            logger.info("⏳ Waiting for horse data to appear in DOM...")
            data_loaded = False
            for attempt in range(10):  # Try for up to 20 seconds (10 attempts x 2s)
                has_data = await page.evaluate('''
                    () => {
                        // Check if there are any horse-related elements
                        const horseElements = document.querySelectorAll(
                            '[class*="horse"], [class*="runner"], [class*="starter"], ' +
                            'table tr, .row, [data-horse]'
                        );

                        // Also check for text content that indicates horses
                        const bodyText = document.body.innerText || '';
                        const hasHorseNames = /[A-Z][a-z]+\\s+[A-Z][a-z]+/.test(bodyText);

                        return horseElements.length > 5 || hasHorseNames;
                    }
                ''')

                if has_data:
                    logger.info(f"✅ Horse data detected in DOM (attempt {attempt + 1})")
                    data_loaded = True
                    break
                else:
                    logger.info(f"⏳ Waiting for data... (attempt {attempt + 1}/10)")
                    await page.wait_for_timeout(2000)

            if not data_loaded:
                logger.warning("⚠️  No horse data detected after waiting - page may not have loaded correctly")

            # Try to extract data directly from Angular using JavaScript
            logger.info("🔍 Attempting to extract data from Angular app...")
            horse_data = None

            try:
                # Execute JavaScript to extract data from the Angular app
                horse_data = await page.evaluate('''
                    () => {
                        // Try multiple methods to extract horse data
                        
                        // Method 1: Look for horse data in window object
                        if (window.ng && window.ng.probe) {
                            const appRoot = document.querySelector('app-root');
                            if (appRoot) {
                                const component = window.ng.probe(appRoot).component;
                                if (component && component.horses) {
                                    return component.horses;
                                }
                            }
                        }
                        
                        // Method 2: Look for data in script tags
                        const scripts = document.querySelectorAll('script');
                        for (let script of scripts) {
                            if (script.textContent && script.textContent.includes('horses')) {
                                try {
                                    const match = script.textContent.match(/horses\s*:\s*(\[.*?\])/);
                                    if (match) {
                                        return JSON.parse(match[1]);
                                    }
                                } catch (e) {
                                    // Continue to next method
                                }
                            }
                        }
                        
                        // Method 3: Extract from DOM after Angular renders
                        const horseElements = document.querySelectorAll('[data-horse-name], .horse-name, .runner-name');
                        if (horseElements.length > 0) {
                            const horses = [];
                            horseElements.forEach(el => {
                                const name = el.textContent || el.getAttribute('data-horse-name');
                                if (name && name.trim()) {
                                    horses.push({
                                        name: name.trim(),
                                        element: el.outerHTML
                                    });
                                }
                            });
                            return horses;
                        }
                        
                        // Method 4: Look for any table rows with horse data
                        const tables = document.querySelectorAll('table');
                        for (let table of tables) {
                            const rows = table.querySelectorAll('tr');
                            if (rows.length > 1) {
                                const horses = [];
                                for (let row of rows) {
                                    const cells = row.querySelectorAll('td');
                                    if (cells.length > 0) {
                                        const firstCell = cells[0].textContent.trim();
                                        if (firstCell && firstCell.length > 0 && !firstCell.includes('Race') && !firstCell.includes('Horse')) {
                                            // Check if it's a horse name (not a header)
                                            const link = cells[0].querySelector('a[href*="Results.cfm"], a[href*="type=Horse"]');
                                            if (link) {
                                                horses.push({
                                                    name: firstCell,
                                                    url: link.href,
                                                    element: row.outerHTML
                                                });
                                            }
                                        }
                                    }
                                }
                                if (horses.length > 0) {
                                    return horses;
                                }
                            }
                        }
                        
                        // Method 5: Look for any links to horse profiles
                        const horseLinks = document.querySelectorAll('a[href*="Results.cfm"][href*="type=Horse"]');
                        if (horseLinks.length > 0) {
                            const horses = [];
                            horseLinks.forEach(link => {
                                const name = link.textContent.trim();
                                if (name) {
                                    horses.push({
                                        name: name,
                                        url: link.href,
                                        element: link.outerHTML
                                    });
                                }
                            });
                            return horses;
                        }
                        
                        return null;
                    }
                ''')
                
                if horse_data:
                    logger.info(f"✅ Found {len(horse_data)} horses via JavaScript extraction")
                else:
                    logger.warning("⚠️  JavaScript extraction returned null")
                    
            except Exception as e:
                logger.warning(f"⚠️  JavaScript extraction failed: {e}")
            
            # If JavaScript extraction worked, process the data
            if horse_data:
                horses = {}
                for horse in horse_data:
                    try:
                        name = horse.get('name', '').strip()
                        if not name:
                            continue
                        
                        # Extract additional data
                        url = horse.get('url', '')
                        refno, registry = self.parse_refno_registry(url) if url else (None, None)
                        
                        # Look for combo win percentage
                        combo_win_pct = None
                        element = horse.get('element', '')
                        if element:
                            match = re.search(r'Jockey\s*/\s*Trainer\s*Win\s*%\s*(\d{1,3})%', element, re.I)
                            if match:
                                combo_win_pct = int(match.group(1))
                        
                        horses[name] = {
                            'smartpick': {
                                'combo_win_pct': combo_win_pct
                            },
                            'profile_url': url,
                            'refno': refno,
                            'registry': registry
                        }
                        
                        logger.info(f"  ✅ Parsed: {name} (combo: {combo_win_pct}%)")
                        
                    except Exception as e:
                        logger.warning(f"⚠️  Error parsing horse data: {e}")
                
                logger.info(f"🐎 Total horses parsed: {len(horses)}")
                await page.close()
                return horses
            
            # Fallback: Try the original HTML parsing method
            logger.info("⚠️  JavaScript extraction failed, trying HTML parsing fallback...")
            html = await page.content()
            horses = self.parse_smartpick_html(html)
            logger.info(f"🐎 Found {len(horses)} horses via HTML parsing")
            
            await page.close()
            return horses
            
        except Exception as e:
            logger.error(f"❌ Error scraping race {race_number}: {e}")
            return {}
    
    def parse_smartpick_html(self, html: str) -> Dict[str, Dict]:
        """
        Parse SmartPick HTML to extract horse data (fallback method)
        
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

        # Look for horse profile links
        horse_links = soup.find_all('a', href=True)
        logger.info(f"🔍 Found {len(horse_links)} total links")

        # Look for Results.cfm links with type=Horse
        results_links = [a for a in horse_links if 'Results.cfm' in a.get('href', '') and 'type=Horse' in a.get('href', '')]
        logger.info(f"🐎 Found {len(results_links)} horse profile links")
        
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


async def scrape_smartpick_with_fixed_playwright(track_id: str, race_date: str, race_number: int, day: str = "D") -> Dict[str, Dict]:
    """
    Convenience function to scrape a single race with the fixed Playwright scraper

    Args:
        track_id: Track code (e.g., 'DMR', 'SA')
        race_date: Date in MM/DD/YYYY format
        race_number: Race number
        day: 'D' for day or 'E' for evening

    Returns:
        Dict mapping horse names to their data
    """
    async with FixedPlaywrightSmartPickScraper() as scraper:
        return await scraper.scrape_race(track_id, race_date, race_number, day)


async def scrape_multiple_races_playwright(track_id: str, race_date: str, num_races: int, day: str = "D") -> Dict[int, Dict[str, Dict]]:
    """
    Scrape SmartPick data for multiple races using a single browser instance

    Args:
        track_id: Track code (e.g., 'DMR', 'SA')
        race_date: Date in MM/DD/YYYY format
        num_races: Number of races to scrape
        day: 'D' for day or 'E' for evening

    Returns:
        Dict mapping race numbers to horse data
        {
            1: {'Horse Name': {'smartpick': {...}, 'profile_url': '...', ...}},
            2: {'Horse Name': {'smartpick': {...}, 'profile_url': '...', ...}},
            ...
        }
    """
    all_races_data = {}

    async with FixedPlaywrightSmartPickScraper() as scraper:
        for race_num in range(1, num_races + 1):
            logger.info(f"📊 Scraping race {race_num}/{num_races}")
            try:
                race_data = await scraper.scrape_race(track_id, race_date, race_num, day)
                all_races_data[race_num] = race_data
                logger.info(f"✅ Race {race_num}: Found {len(race_data)} horses")
            except Exception as e:
                logger.error(f"❌ Error scraping race {race_num}: {e}")
                all_races_data[race_num] = {}

    return all_races_data


if __name__ == "__main__":
    # Test the fixed scraper
    async def test():
        result = await scrape_smartpick_with_fixed_playwright('SA', '10/05/2025', 1, 'D')
        print(f"Found {len(result)} horses")
        for name, data in result.items():
            print(f"  {name}: {data}")

    asyncio.run(test())