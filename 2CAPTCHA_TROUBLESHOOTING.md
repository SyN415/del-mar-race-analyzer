# 2Captcha Troubleshooting Guide

## Error: ERROR_METHOD_CALL

This error from 2Captcha API typically means one of the following:

---

## 1. Check API Key Format

### Verify Your Key
```bash
# Your API key should be 32 characters, alphanumeric
# Example format: 1abc234de56fab7c89012d34e56fa7b8

# Check length
echo -n "YOUR_KEY_HERE" | wc -c
# Should output: 32
```

### Common Issues
- ❌ Key has spaces or newlines
- ❌ Key is truncated
- ❌ Using wrong key (test vs production)

---

## 2. Check Account Balance

### Via Web Dashboard
1. Go to: https://2captcha.com/enterpage
2. Login with your credentials
3. Check balance in top-right corner
4. Minimum needed: $0.50 for testing

### Via API
```bash
# Replace YOUR_API_KEY with your actual key
curl "https://2captcha.com/res.php?key=YOUR_API_KEY&action=getbalance"

# Expected response:
# OK|12.34  (where 12.34 is your balance in USD)

# Error responses:
# ERROR_WRONG_USER_KEY - Invalid API key
# ERROR_KEY_DOES_NOT_EXIST - Key not found
```

### Add Balance
If balance is low:
1. Go to: https://2captcha.com/pay
2. Minimum deposit: $3.00
3. Accepts: PayPal, Bitcoin, Alipay, etc.

---

## 3. Check API Key Permissions

### hCaptcha Must Be Enabled
1. Login to 2Captcha dashboard
2. Go to Settings → API Settings
3. Verify "hCaptcha" is enabled
4. Some keys are restricted to specific captcha types

### Create New Key (if needed)
1. Go to Settings → API Keys
2. Click "Create New Key"
3. Enable all captcha types
4. Copy the new key
5. Update `TWOCAPTCHA_API_KEY` in Render

---

## 4. Test Your API Key

### Quick Test Script
```python
from twocaptcha import TwoCaptcha

# Replace with your actual key
solver = TwoCaptcha('YOUR_API_KEY_HERE')

try:
    # Test with a simple captcha
    result = solver.normal('https://2captcha.com/demo/normal')
    print(f"✅ API key works! Result: {result}")
except Exception as e:
    print(f"❌ Error: {e}")
```

### Test hCaptcha Specifically
```python
from twocaptcha import TwoCaptcha

solver = TwoCaptcha('YOUR_API_KEY_HERE')

try:
    result = solver.hcaptcha(
        sitekey='10000000-ffff-ffff-ffff-000000000001',
        url='https://2captcha.com/demo/hcaptcha'
    )
    print(f"✅ hCaptcha works! Token: {result['code'][:50]}...")
except Exception as e:
    print(f"❌ Error: {e}")
    print(f"Error type: {type(e).__name__}")
```

---

## 5. Common Error Codes

| Error Code | Meaning | Solution |
|------------|---------|----------|
| ERROR_WRONG_USER_KEY | Invalid API key format | Check key format, no spaces |
| ERROR_KEY_DOES_NOT_EXIST | Key not found | Verify key is correct |
| ERROR_ZERO_BALANCE | Insufficient funds | Add balance |
| ERROR_METHOD_CALL | Invalid method/params | Check hCaptcha is enabled |
| ERROR_IP_NOT_ALLOWED | IP restriction | Check IP whitelist settings |
| ERROR_PAGEURL | Invalid URL parameter | Check URL format |

---

## 6. Alternative Solutions

### Option A: Use Different 2Captcha Account
If your current account has issues:
1. Create new account at https://2captcha.com/auth/register
2. Add $3 minimum balance
3. Get new API key
4. Update Render environment variable

### Option B: Try Alternative Service
If 2Captcha continues to fail:

**Capsolver** (Recommended)
- Better hCaptcha success rate
- Similar pricing (~$0.003/solve)
- Website: https://www.capsolver.com/

**Anti-Captcha**
- Reliable alternative
- Slightly more expensive (~$0.004/solve)
- Website: https://anti-captcha.com/

### Option C: Disable SmartPick Temporarily
If you just want to test other features:
```bash
# In Render environment variables
SMARTPICK_CIRCUIT_BREAKER=1
SMARTPICK_CB_THRESHOLD=0  # Skip SmartPick entirely
```

---

## 7. Update Render Environment Variable

Once you have a working key:

1. Go to Render Dashboard
2. Select your service
3. Go to "Environment" tab
4. Find `TWOCAPTCHA_API_KEY`
5. Click "Edit"
6. Paste new key (no quotes, no spaces)
7. Click "Save Changes"
8. Service will auto-redeploy

---

## 8. Verify Fix

After updating the key, check logs for:

### Success Indicators
```
✅ 2Captcha solver initialized
🔐 Solving hCaptcha for https://...
✅ Captcha solved! (#1, cost: $0.0030, total: $0.0030)
```

### Still Failing
```
❌ Error solving captcha via wrapper: ERROR_METHOD_CALL
```
If you still see this, try:
1. Check balance again
2. Verify key was saved correctly (no trailing spaces)
3. Try creating a completely new 2Captcha account

---

## 9. Cost Estimation

### Per Analysis Run
- 10 races × 1 captcha each = 10 captchas
- 10 × $0.003 = **$0.03 per full card**
- With circuit breaker: **$0.003 per run** (stops after first failure)

### Monthly Budget
- 100 analyses/month = $3.00
- 1000 analyses/month = $30.00

### Current Behavior
With circuit breaker enabled:
- Attempts race 1 captcha
- If fails, stops immediately
- Cost: $0.003 per attempt (even if it fails)

---

## 10. Contact Support

If nothing works:

**2Captcha Support**
- Email: support@2captcha.com
- Telegram: @twocaptcha_support
- Response time: Usually within 24 hours

**Include in Support Request**:
- Your API key (first 8 characters only)
- Error message: "ERROR_METHOD_CALL"
- What you're trying to solve: "hCaptcha on Equibase.com"
- Your account email

---

## Quick Checklist

- [ ] API key is 32 characters, no spaces
- [ ] Balance is > $0.50
- [ ] hCaptcha is enabled in settings
- [ ] Key is correctly set in Render
- [ ] Tested key with simple script
- [ ] Checked 2Captcha service status
- [ ] Verified no IP restrictions

If all checked and still failing → Contact 2Captcha support or try alternative service.

