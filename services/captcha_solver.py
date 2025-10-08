#!/usr/bin/env python3
"""
2Captcha integration service for solving hCaptcha challenges on Equibase.

This service handles:
- Solving hCaptcha challenges using 2Captcha API
- Managing API keys and configuration
- Retry logic and error handling
- Cost tracking and logging
"""
import os
import logging
from typing import Optional
from twocaptcha import TwoCaptcha

logger = logging.getLogger(__name__)


class CaptchaSolver:
    """Service for solving captchas using 2Captcha API"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize captcha solver
        
        Args:
            api_key: 2Captcha API key. If not provided, reads from TWOCAPTCHA_API_KEY env var
        """
        self.api_key = api_key or os.environ.get('TWOCAPTCHA_API_KEY')
        
        if not self.api_key:
            logger.warning("⚠️  No 2Captcha API key provided. Captcha solving will fail.")
            self.solver = None
        else:
            self.solver = TwoCaptcha(self.api_key)
            logger.info("✅ 2Captcha solver initialized")
        
        self.captchas_solved = 0
        self.total_cost = 0.0
    
    def solve_hcaptcha(
        self,
        sitekey: str,
        url: str,
        rqdata: Optional[str] = None,
        user_agent: Optional[str] = None,
        enterprise: Optional[bool] = None,
    ) -> Optional[str]:
        """
        Solve an hCaptcha challenge

        Args:
            sitekey: The hCaptcha site key from the page
            url: The URL where the captcha appears
            rqdata: Optional hCaptcha Enterprise rqdata value (if present in iframe src)
            user_agent: Optional user agent string to forward to solver
            enterprise: If True, explicitly mark as enterprise challenge

        Returns:
            The captcha solution token, or None if solving failed
        """
        if not self.solver:
            logger.error("❌ Cannot solve captcha: No API key configured")
            return None

        # Build extra kwargs supported by 2captcha for hCaptcha
        extra_kwargs = {}
        if rqdata:
            extra_kwargs['rqdata'] = rqdata
        if user_agent:
            # API expects 'userAgent'
            extra_kwargs['userAgent'] = user_agent
        if enterprise:
            extra_kwargs['enterprise'] = 1

        try:
            logger.info(f"🔐 Solving hCaptcha for {url}")
            logger.info(f"   Site key: {sitekey[:20]}...")
            if rqdata:
                logger.info("   Using rqdata param (enterprise)")

            # Primary attempt: use library wrapper (renames url->pageurl internally)
            result = self.solver.hcaptcha(
                sitekey=sitekey,
                url=url,
                **extra_kwargs,
            )

            token = result.get('code') if isinstance(result, dict) else None
            if token:
                self.captchas_solved += 1
                cost = 0.00299
                self.total_cost += cost
                logger.info(f"✅ Captcha solved! (#{self.captchas_solved}, cost: ${cost:.4f}, total: ${self.total_cost:.4f})")
                logger.info(f"   Token: {token[:50]}...")
                return token

            logger.error("❌ Captcha solving failed: No token returned")
            return None

        except Exception as e:
            # If method/params rejected, try explicit fallback with pageurl
            err_text = str(e)
            logger.error(f"❌ Error solving captcha via wrapper: {e}")
            logger.error(f"   Error type: {type(e).__name__}")
            logger.error(f"   Error details: {err_text}")

            try:
                logger.info("🔁 Retrying with explicit solve(method='hcaptcha', pageurl=...) and enterprise flags")
                fallback_kwargs = {**extra_kwargs}
                # Library expects 'pageurl' explicitly here; don't rely on rename
                result = self.solver.solve(
                    sitekey=sitekey,
                    pageurl=url,
                    method='hcaptcha',
                    **fallback_kwargs,
                )
                token = result.get('code') if isinstance(result, dict) else None
                if token:
                    self.captchas_solved += 1
                    cost = 0.00299
                    self.total_cost += cost
                    logger.info(f"✅ Captcha solved (fallback)! (#{self.captchas_solved}, cost: ${cost:.4f}, total: ${self.total_cost:.4f})")
                    logger.info(f"   Token: {token[:50]}...")
                    return token
                logger.error("❌ Fallback solve returned no token")
                return None
            except Exception as e2:
                logger.error(f"❌ Fallback error solving captcha: {e2}")
                logger.error(f"   Error type: {type(e2).__name__}")
                logger.error(f"   Error details: {str(e2)}")
                return None
    
    def get_balance(self) -> Optional[float]:
        """
        Get current 2Captcha account balance
        
        Returns:
            Account balance in USD, or None if check failed
        """
        if not self.solver:
            logger.error("❌ Cannot check balance: No API key configured")
            return None
        
        try:
            balance = self.solver.balance()
            logger.info(f"💰 2Captcha balance: ${balance:.2f}")
            return balance
        except Exception as e:
            logger.error(f"❌ Error checking balance: {e}")
            return None
    
    def get_stats(self) -> dict:
        """
        Get captcha solving statistics
        
        Returns:
            Dictionary with solving stats
        """
        return {
            'captchas_solved': self.captchas_solved,
            'total_cost': self.total_cost,
            'average_cost': self.total_cost / self.captchas_solved if self.captchas_solved > 0 else 0
        }


async def solve_equibase_captcha(page, captcha_solver: CaptchaSolver) -> bool:
    """
    Detect and solve hCaptcha on an Equibase page

    Args:
        page: Playwright page object
        captcha_solver: CaptchaSolver instance

    Returns:
        True if captcha was solved (or not present), False if solving failed
    """
    try:
        # First check if we're on an Incapsula challenge page
        page_content = await page.content()

        # Check for Incapsula challenge indicators
        is_incapsula_challenge = 'incapsula' in page_content.lower() or 'imperva' in page_content.lower()

        if is_incapsula_challenge:
            logger.warning("🛡️  Incapsula/Imperva challenge detected")

            # Wait a bit for the challenge to fully load
            await page.wait_for_timeout(3000)

        # Check if hCaptcha is present (including nested iframes)
        captcha_frame = None
        hcaptcha_iframe = None

        # First try direct detection
        captcha_frame = await page.query_selector('iframe[src*="hcaptcha"]')
        if captcha_frame:
            logger.info("🔍 Found hCaptcha iframe directly")
            hcaptcha_iframe = captcha_frame

        # If not found, search recursively in all frames
        if not captcha_frame:
            logger.info("🔍 Searching for hCaptcha in nested iframes...")
            all_frames = page.frames

            for frame in all_frames:
                try:
                    # Check frame URL
                    frame_url = frame.url
                    if 'hcaptcha' in frame_url.lower():
                        logger.info(f"🔍 Found hCaptcha in frame by URL: {frame_url[:100]}")
                        captcha_frame = True
                        hcaptcha_iframe = frame
                        break

                    # Check frame content for hCaptcha elements
                    try:
                        # Look for hCaptcha checkbox or iframe inside this frame
                        has_hcaptcha = await frame.evaluate('''
                            () => {
                                // Check for hCaptcha checkbox
                                const checkbox = document.querySelector('[data-hcaptcha-widget-id]') ||
                                               document.querySelector('.h-captcha') ||
                                               document.querySelector('iframe[src*="hcaptcha"]');
                                return checkbox !== null;
                            }
                        ''')

                        if has_hcaptcha:
                            logger.info(f"🔍 Found hCaptcha elements in frame: {frame.name or 'unnamed'}")
                            captcha_frame = True
                            hcaptcha_iframe = frame
                            break
                    except Exception as e:
                        # Frame might not be accessible, skip it
                        pass

                except Exception as e:
                    # Frame might be detached or inaccessible
                    pass

        if not captcha_frame:
            # If we detected Incapsula but no hCaptcha, this is suspicious
            if is_incapsula_challenge:
                logger.warning("⚠️  Incapsula challenge detected but no hCaptcha found - page may still be loading")
                # Wait a bit more and try again
                await page.wait_for_timeout(3000)

                # Try one more time
                all_frames = page.frames
                for frame in all_frames:
                    try:
                        frame_url = frame.url
                        if 'hcaptcha' in frame_url.lower():
                            logger.info(f"🔍 Found hCaptcha on retry: {frame_url[:100]}")
                            captcha_frame = True
                            hcaptcha_iframe = frame
                            break
                    except:
                        pass

                if not captcha_frame:
                    logger.warning("⚠️  Incapsula challenge present but hCaptcha not found")
                    logger.info("🔄 Attempting to bypass by waiting and checking page state...")

                    # Sometimes Incapsula just needs time to verify the browser
                    await page.wait_for_timeout(5000)

                    # Check if page has loaded content now
                    page_content_after = await page.content()

                    # Check if we're still on challenge page
                    still_blocked = 'incapsula' in page_content_after.lower() or 'imperva' in page_content_after.lower()

                    if not still_blocked:
                        logger.info("✅ Incapsula challenge passed automatically")
                        return True
                    else:
                        logger.error("❌ Still blocked by Incapsula - cannot proceed")
                        # Save page content for debugging
                        try:
                            import os
                            os.makedirs('debug_output', exist_ok=True)
                            with open('debug_output/incapsula_block.html', 'w', encoding='utf-8') as f:
                                f.write(page_content_after)
                            logger.info("💾 Saved blocked page to debug_output/incapsula_block.html")
                        except:
                            pass
                        return False
            else:
                logger.info("ℹ️  No hCaptcha detected on page")
                return True

        logger.info("🔍 hCaptcha detected, attempting to solve...")

        # Get the hCaptcha sitekey from the page or frames
        sitekey = None

        # Try to get sitekey from main page first
        try:
            sitekey = await page.evaluate('''
                () => {
                    const hcaptchaDiv = document.querySelector('[data-sitekey]');
                    if (hcaptchaDiv) {
                        return hcaptchaDiv.getAttribute('data-sitekey');
                    }

                    // Try to find it in iframe src
                    const iframe = document.querySelector('iframe[src*="hcaptcha"]');
                    if (iframe) {
                        const src = iframe.src;
                        const match = src.match(/sitekey=([^&]+)/);
                        if (match) {
                            return match[1];
                        }
                    }

                    return null;
                }
            ''')
        except Exception as e:
            logger.warning(f"⚠️  Could not extract sitekey from main page: {e}")

        # If not found in main page, search in all frames
        if not sitekey:
            logger.info("🔍 Searching for sitekey in frames...")
            all_frames = page.frames

            for frame in all_frames:
                try:
                    frame_sitekey = await frame.evaluate('''
                        () => {
                            const hcaptchaDiv = document.querySelector('[data-sitekey]');
                            if (hcaptchaDiv) {
                                return hcaptchaDiv.getAttribute('data-sitekey');
                            }

                            const iframe = document.querySelector('iframe[src*="hcaptcha"]');
                            if (iframe) {
                                const src = iframe.src;
                                const match = src.match(/sitekey=([^&]+)/);
                                if (match) {
                                    return match[1];
                                }
                            }

                            return null;
                        }
                    ''')

                    if frame_sitekey:
                        sitekey = frame_sitekey
                        logger.info(f"✅ Found sitekey in frame: {frame.name or 'unnamed'}")
                        break
                except Exception as e:
                    # Frame might not be accessible
                    pass

        if not sitekey:
            logger.error("❌ Could not find hCaptcha sitekey on page or in any frame")
            return False

        logger.info(f"✅ Found sitekey: {sitekey[:20]}...")

        # Try to extract rqdata (hCaptcha Enterprise) from iframe src or attributes
        rqdata = None
        try:
            rqdata = await page.evaluate('''
                () => {
                    const iframe = document.querySelector('iframe[src*="hcaptcha"]');
                    if (iframe && iframe.src) {
                        try {
                            const u = new URL(iframe.src);
                            return u.searchParams.get('rqdata');
                        } catch (e) {}
                    }
                    const el = document.querySelector('[data-rqdata]');
                    if (el) return el.getAttribute('data-rqdata');
                    return null;
                }
            ''')
        except Exception:
            pass

        if not rqdata:
            for frame in page.frames:
                try:
                    frame_rq = await frame.evaluate('''
                        () => {
                            const iframe = document.querySelector('iframe[src*="hcaptcha"]');
                            if (iframe && iframe.src) {
                                try {
                                    const u = new URL(iframe.src);
                                    return u.searchParams.get('rqdata');
                                } catch (e) {}
                            }
                            const el = document.querySelector('[data-rqdata]');
                            if (el) return el.getAttribute('data-rqdata');
                            return null;
                        }
                    ''')
                    if frame_rq:
                        rqdata = frame_rq
                        break
                except Exception:
                    continue

        # Get user agent for solver context
        user_agent = None
        try:
            user_agent = await page.evaluate('() => navigator.userAgent')
        except Exception:
            pass

        # Solve the captcha
        url = page.url
        token = captcha_solver.solve_hcaptcha(sitekey, url, rqdata=rqdata, user_agent=user_agent, enterprise=True)

        if not token:
            logger.error("❌ Failed to solve captcha")
            return False

        # Inject the captcha solution into the page
        logger.info("💉 Injecting captcha solution into page...")

        # Try to inject in main page first
        success = False
        try:
            success = await page.evaluate(f'''
                (token) => {{
                    // Try to find the hCaptcha response textarea
                    const responseArea = document.querySelector('[name="h-captcha-response"]') ||
                                       document.querySelector('[name="g-recaptcha-response"]');

                    if (responseArea) {{
                        responseArea.value = token;
                        responseArea.innerHTML = token;

                        // Trigger change event
                        const event = new Event('change', {{ bubbles: true }});
                        responseArea.dispatchEvent(event);

                        return true;
                    }}

                    return false;
                }}
            ''', token)
        except Exception as e:
            logger.warning(f"⚠️  Could not inject in main page: {e}")

        # If injection in main page failed, try all frames
        if not success:
            logger.info("🔍 Trying to inject solution in frames...")
            all_frames = page.frames

            for frame in all_frames:
                try:
                    frame_success = await frame.evaluate(f'''
                        (token) => {{
                            const responseArea = document.querySelector('[name="h-captcha-response"]') ||
                                               document.querySelector('[name="g-recaptcha-response"]');

                            if (responseArea) {{
                                responseArea.value = token;
                                responseArea.innerHTML = token;

                                const event = new Event('change', {{ bubbles: true }});
                                responseArea.dispatchEvent(event);

                                return true;
                            }}

                            return false;
                        }}
                    ''', token)

                    if frame_success:
                        logger.info(f"✅ Injected solution in frame: {frame.name or 'unnamed'}")
                        success = True
                        break
                except Exception as e:
                    # Frame might not be accessible
                    pass

        if success:
            logger.info("✅ Captcha solution injected successfully")

            # Try to submit the form or click the checkbox
            try:
                # Look for submit button in all frames
                for frame in page.frames:
                    try:
                        submit_clicked = await frame.evaluate('''
                            () => {
                                const submitBtn = document.querySelector('button[type="submit"]') ||
                                                 document.querySelector('input[type="submit"]') ||
                                                 document.querySelector('[id*="submit"]');
                                if (submitBtn) {
                                    submitBtn.click();
                                    return true;
                                }

                                // Try to submit form
                                const form = document.querySelector('form');
                                if (form) {
                                    form.submit();
                                    return true;
                                }

                                return false;
                            }
                        ''')

                        if submit_clicked:
                            logger.info("✅ Clicked submit button")
                            break
                    except:
                        pass
            except Exception as e:
                logger.warning(f"⚠️  Could not click submit: {e}")

            # Wait for page to process the solution
            logger.info("⏳ Waiting for captcha to be processed...")
            await page.wait_for_timeout(5000)

            # Check if we're still on the captcha page
            still_captcha = False
            try:
                page_content_after = await page.content()
                still_captcha = 'incapsula' in page_content_after.lower() or 'hcaptcha' in page_content_after.lower()
            except:
                pass

            if still_captcha:
                logger.warning("⚠️  Still on captcha page after solving - may need manual intervention")
                return False

            logger.info("🎉 Successfully bypassed captcha!")
            return True
        else:
            logger.error("❌ Failed to inject captcha solution")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error solving Equibase captcha: {e}")
        return False


# Global captcha solver instance
_captcha_solver: Optional[CaptchaSolver] = None


def get_captcha_solver() -> CaptchaSolver:
    """
    Get or create the global captcha solver instance
    
    Returns:
        CaptchaSolver instance
    """
    global _captcha_solver
    
    if _captcha_solver is None:
        _captcha_solver = CaptchaSolver()
    
    return _captcha_solver

