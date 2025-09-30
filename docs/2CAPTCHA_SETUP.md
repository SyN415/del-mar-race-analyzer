# 2Captcha Integration Setup Guide

## Overview

Equibase has implemented hCaptcha protection on all pages, making automated scraping impossible without solving captcha challenges. This guide explains how to set up 2Captcha integration to automatically solve these challenges.

## Why 2Captcha?

- **Affordable**: ~$2.99 per 1000 hCaptcha solves
- **Reliable**: High success rate for hCaptcha
- **Fast**: Average solve time 10-20 seconds
- **Easy Integration**: Simple API with Python SDK

## Cost Estimation

For a typical race card scrape (10 races, 80+ horses):

| Scenario | Captchas Needed | Cost per Scrape |
|----------|----------------|-----------------|
| **Best Case** | 1-2 | $0.003 - $0.006 |
| **Typical** | 3-5 | $0.009 - $0.015 |
| **Worst Case** | 10-20 | $0.030 - $0.060 |

**Expected: ~$0.01 per race card** (3-5 captchas)

## Setup Instructions

### Step 1: Create 2Captcha Account

1. Go to https://2captcha.com/
2. Click "Sign Up" and create an account
3. Verify your email address

### Step 2: Add Funds

1. Log in to your 2Captcha account
2. Go to "Add Funds" in the top menu
3. Choose payment method (PayPal, Bitcoin, etc.)
4. Add funds (minimum $3, recommended $10-20 to start)

### Step 3: Get API Key

1. Go to https://2captcha.com/enterpage
2. Your API key is displayed at the top of the page
3. Copy the API key (format: `32-character hexadecimal string`)

### Step 4: Configure Environment Variable

#### For Local Development:

1. Copy `.env.example` to `.env` if you haven't already:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and add your API key:
   ```bash
   TWOCAPTCHA_API_KEY=your_actual_api_key_here
   ```

#### For Render.com Deployment:

1. Go to your Render.com dashboard
2. Select your web service
3. Go to "Environment" tab
4. Click "Add Environment Variable"
5. Add:
   - **Key**: `TWOCAPTCHA_API_KEY`
   - **Value**: Your 2Captcha API key
6. Click "Save Changes"
7. Render will automatically redeploy with the new variable

### Step 5: Install Dependencies

The 2Captcha Python package is already in `requirements.txt`. If you're setting up locally:

```bash
pip install -r requirements.txt
```

For Render.com, this happens automatically during deployment.

### Step 6: Test the Integration

Run a test scrape to verify captcha solving works:

```bash
python -c "from services.captcha_solver import get_captcha_solver; solver = get_captcha_solver(); print(f'Balance: ${solver.get_balance()}')"
```

This should display your 2Captcha account balance.

## How It Works

### Captcha Detection & Solving Flow

1. **Homepage Visit**: Scraper visits Equibase homepage
2. **Captcha Detection**: Checks for hCaptcha iframe
3. **Sitekey Extraction**: Extracts hCaptcha sitekey from page
4. **API Request**: Sends sitekey + URL to 2Captcha API
5. **Worker Solving**: 2Captcha worker solves the captcha (10-20 seconds)
6. **Token Return**: 2Captcha returns solution token
7. **Token Injection**: Scraper injects token into page
8. **Session Established**: Cookies saved for subsequent requests
9. **Reuse Session**: All subsequent pages use the same session (no more captchas!)

### Session Persistence

Once a captcha is solved on the homepage:
- Session cookies are saved in the browser context
- All subsequent requests (SmartPick pages, horse profiles) reuse the session
- **No additional captchas needed** for the same scraping session
- New session required only if cookies expire or browser restarts

## Monitoring & Cost Tracking

### Check Balance

```python
from services.captcha_solver import get_captcha_solver

solver = get_captcha_solver()
balance = solver.get_balance()
print(f"Current balance: ${balance:.2f}")
```

### View Statistics

```python
from services.captcha_solver import get_captcha_solver

solver = get_captcha_solver()
stats = solver.get_stats()
print(f"Captchas solved: {stats['captchas_solved']}")
print(f"Total cost: ${stats['total_cost']:.4f}")
print(f"Average cost: ${stats['average_cost']:.4f}")
```

### Logs

The scraper logs all captcha-related activity:

```
🔐 Solving hCaptcha for https://www.equibase.com
✅ Captcha solved! (#1, cost: $0.0030, total: $0.0030)
💉 Injecting captcha solution into page...
🎉 Successfully bypassed captcha!
```

## Troubleshooting

### "No API key configured"

**Problem**: `TWOCAPTCHA_API_KEY` environment variable not set

**Solution**: 
- Check `.env` file has the correct key
- For Render.com, verify environment variable is set in dashboard
- Restart application after adding the key

### "Insufficient balance"

**Problem**: 2Captcha account has no funds

**Solution**: Add funds to your 2Captcha account

### "Captcha solving failed"

**Possible causes**:
1. Invalid API key - verify key is correct
2. Network issues - check internet connection
3. 2Captcha service down - check https://2captcha.com/status
4. Sitekey not found - page structure may have changed

**Solution**: Check logs for specific error message

### "Still on captcha page after solving"

**Problem**: Token injection failed or captcha not accepted

**Possible causes**:
1. Page structure changed
2. Token expired before injection
3. Additional verification required

**Solution**: 
- Check screenshot saved in `logs/html/`
- May need to update token injection logic
- Contact support if persistent

## Best Practices

### 1. Monitor Your Balance

Set up alerts when balance drops below $5:
- Check balance before large scraping jobs
- Add funds proactively to avoid interruptions

### 2. Optimize Session Reuse

- Keep browser context alive between races
- Scrape multiple races in one session
- Minimize new browser instances

### 3. Handle Failures Gracefully

- Implement retry logic for failed captcha solves
- Fall back to manual notification if captcha fails
- Log all captcha attempts for debugging

### 4. Cost Management

- Track captcha costs per scraping session
- Set daily/monthly budget limits
- Alert if costs exceed expected range

## API Reference

### CaptchaSolver Class

```python
from services.captcha_solver import CaptchaSolver

# Initialize
solver = CaptchaSolver(api_key="your_key")  # or reads from env

# Solve hCaptcha
token = solver.solve_hcaptcha(sitekey="...", url="https://...")

# Check balance
balance = solver.get_balance()

# Get stats
stats = solver.get_stats()
```

### Helper Function

```python
from services.captcha_solver import solve_equibase_captcha

# Solve captcha on current page
success = await solve_equibase_captcha(page, solver)
```

## Support

### 2Captcha Support
- Website: https://2captcha.com/support
- Email: support@2captcha.com
- Documentation: https://2captcha.com/2captcha-api

### Application Support
- Check logs in `logs/` directory
- Review HTML snapshots in `logs/html/`
- Check screenshots for visual debugging

## Security Notes

- **Never commit API keys** to version control
- Use environment variables for all sensitive data
- Rotate API keys periodically
- Monitor for unauthorized usage
- Set up 2Captcha IP restrictions if possible

## Additional Resources

- 2Captcha Pricing: https://2captcha.com/2captcha-api#rates
- hCaptcha Documentation: https://docs.hcaptcha.com/
- Playwright Documentation: https://playwright.dev/python/

