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
    
    def solve_hcaptcha(self, sitekey: str, url: str) -> Optional[str]:
        """
        Solve an hCaptcha challenge
        
        Args:
            sitekey: The hCaptcha site key from the page
            url: The URL where the captcha appears
            
        Returns:
            The captcha solution token, or None if solving failed
        """
        if not self.solver:
            logger.error("❌ Cannot solve captcha: No API key configured")
            return None
        
        try:
            logger.info(f"🔐 Solving hCaptcha for {url}")
            logger.info(f"   Site key: {sitekey[:20]}...")
            
            result = self.solver.hcaptcha(
                sitekey=sitekey,
                url=url
            )
            
            token = result.get('code')
            
            if token:
                self.captchas_solved += 1
                # 2Captcha hCaptcha cost is ~$2.99 per 1000 solves
                cost = 0.00299
                self.total_cost += cost
                
                logger.info(f"✅ Captcha solved! (#{self.captchas_solved}, cost: ${cost:.4f}, total: ${self.total_cost:.4f})")
                logger.info(f"   Token: {token[:50]}...")
                
                return token
            else:
                logger.error("❌ Captcha solving failed: No token returned")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error solving captcha: {e}")
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
        if 'incapsula' in page_content.lower() or 'imperva' in page_content.lower():
            logger.warning("🛡️  Incapsula/Imperva challenge detected")

            # Wait a bit for the challenge to fully load
            await page.wait_for_timeout(2000)

        # Check if hCaptcha is present (including nested iframes)
        captcha_frame = await page.query_selector('iframe[src*="hcaptcha"]')

        # Also check for hCaptcha in nested iframes (Incapsula wrapper)
        if not captcha_frame:
            # Try to find hCaptcha in all iframes
            all_frames = page.frames
            for frame in all_frames:
                try:
                    frame_url = frame.url
                    if 'hcaptcha' in frame_url.lower():
                        logger.info("🔍 Found hCaptcha in nested iframe")
                        captcha_frame = True
                        break
                except:
                    pass

        if not captcha_frame:
            logger.info("ℹ️  No hCaptcha detected on page")
            return True
        
        logger.info("🔍 hCaptcha detected, attempting to solve...")
        
        # Get the hCaptcha sitekey from the page
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
        
        if not sitekey:
            logger.error("❌ Could not find hCaptcha sitekey on page")
            return False
        
        logger.info(f"✅ Found sitekey: {sitekey[:20]}...")
        
        # Solve the captcha
        url = page.url
        token = captcha_solver.solve_hcaptcha(sitekey, url)
        
        if not token:
            logger.error("❌ Failed to solve captcha")
            return False
        
        # Inject the captcha solution into the page
        logger.info("💉 Injecting captcha solution into page...")
        
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
                    
                    // Try to submit the form
                    const form = responseArea.closest('form');
                    if (form) {{
                        form.submit();
                        return true;
                    }}
                    
                    // Try to find and click submit button
                    const submitBtn = document.querySelector('button[type="submit"]') ||
                                     document.querySelector('input[type="submit"]');
                    if (submitBtn) {{
                        submitBtn.click();
                        return true;
                    }}
                    
                    return true;
                }}
                
                return false;
            }}
        ''', token)
        
        if success:
            logger.info("✅ Captcha solution injected successfully")
            # Wait for page to process the solution
            await page.wait_for_timeout(3000)
            
            # Check if we're still on the captcha page
            still_captcha = await page.query_selector('iframe[src*="hcaptcha"]')
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

