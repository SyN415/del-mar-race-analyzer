# Production Issue Resolution Guide
## Test Session: 2025-10-09 05:36:04

---

## 🔴 Critical Issues Identified

### Issue 1: 2Captcha API Error - `ERROR_METHOD_CALL`

**Status**: ⚠️ **USER ACTION REQUIRED**

**What Happened**:
```
❌ Error solving captcha via wrapper: ERROR_METHOD_CALL
❌ Fallback error solving captcha: ERROR_METHOD_CALL
🛑 Circuit breaker triggered after race 1: captcha_fail_streak=1
```

**Root Cause**: 
The 2Captcha API is rejecting our requests. This error typically means:
1. Invalid API key format
2. Insufficient account balance
3. hCaptcha not enabled in account settings
4. API key doesn't have proper permissions

**Impact**: 
- SmartPick scraping completely blocked
- Circuit breaker stops all further scraping attempts
- Analysis falls back to basic race card data only (no SmartPick insights)

**Solution Steps**:

#### Step 1: Verify API Key Format
```bash
# Your API key should be exactly 32 characters, alphanumeric
# Example format: 1abc234de56fab7c89012d34e56fa7b8

# Check your key length:
echo -n "YOUR_KEY_HERE" | wc -c
# Should output: 32
```

**Common Issues**:
- ❌ Key has spaces or newlines at the end
- ❌ Key is truncated when copying
- ❌ Using test key instead of production key

#### Step 2: Check Account Balance
1. Go to: https://2captcha.com/enterpage
2. Login with your credentials
3. Check balance in top-right corner
4. **Minimum needed**: $0.50 for testing
5. **Recommended**: $5-10 for production use

**Cost per scrape**: ~$0.01-0.03 (3-10 captchas per race card)

#### Step 3: Verify hCaptcha is Enabled
1. Go to: https://2captcha.com/setting
2. Scroll to "Captcha Types"
3. Ensure **hCaptcha** is checked/enabled
4. Save settings if you made changes

#### Step 4: Test Your API Key
Run this test script locally:

```python
from twocaptcha import TwoCaptcha

# Replace with your actual API key
solver = TwoCaptcha('YOUR_API_KEY_HERE')

try:
    # Test with 2Captcha's demo hCaptcha
    result = solver.hcaptcha(
        sitekey='10000000-ffff-ffff-ffff-000000000001',
        url='https://2captcha.com/demo/hcaptcha'
    )
    print(f"✅ SUCCESS! Your API key works!")
    print(f"Token: {result['code'][:50]}...")
except Exception as e:
    print(f"❌ ERROR: {e}")
    print(f"Error type: {type(e).__name__}")
```

**Expected Output**:
- ✅ Success: `✅ SUCCESS! Your API key works!`
- ❌ Failure: Check the error message for specific issue

#### Step 5: Update Render Environment Variable
Once you have a working key:

1. Go to [Render Dashboard](https://dashboard.render.com)
2. Select your service: `del-mar-race-analyzer`
3. Go to **Environment** tab
4. Find `TWOCAPTCHA_API_KEY`
5. Click **Edit**
6. Paste your key (no quotes, no spaces, no newlines)
7. Click **Save Changes**
8. Service will auto-redeploy

#### Step 6: Verify Fix
After redeployment, check logs for:

**Success Indicators**:
```
✅ 2Captcha solver initialized
🔐 Solving hCaptcha for https://...
✅ Captcha solved! (#1, cost: $0.0030, total: $0.0030)
```

**Still Failing**:
If you still see `ERROR_METHOD_CALL`:
1. Double-check balance is sufficient
2. Verify key was saved correctly (no trailing spaces)
3. Try creating a new API key in 2Captcha dashboard
4. Contact 2Captcha support: https://2captcha.com/support

---

### Issue 2: Server Restart Mid-Scrape

**Status**: 🔧 **CODE FIX REQUIRED**

**What Happened**:
```
2025-10-09 05:36:04 - First process starts
2025-10-09 05:37:45 - NEW process [7] starts (server restart)
2025-10-09 05:37:55 - Session 706bc697... not found (500 error)
```

**Root Cause**:
1. Server restarted during scraping operation (1.5 minutes into scrape)
2. Background asyncio tasks were killed
3. Session data lost because database wasn't persisting correctly

**Why Did Server Restart?**
Possible causes:
- Render health check timeout during long scraping operation
- Memory limit exceeded
- Manual deployment triggered
- Application crash (though logs show clean restart)

**Impact**:
- Active scraping operations interrupted
- Session data lost
- Frontend gets 500 errors when polling for status
- User sees incomplete/failed analysis

---

### Issue 3: Database Persistence Problem

**Status**: 🔧 **CODE FIX REQUIRED**

**What Happened**:
```
Session 706bc697-8ac4-41b7-9005-d60d2b09477b not found
```

**Root Cause**:
- SessionManager uses `data/sessions.db` as database path
- Render has persistent disk mounted at `/app/data`
- Database should persist, but session was lost after restart
- Possible issues:
  1. Database file created in wrong location
  2. Disk mount not working correctly
  3. Database connection not using persistent path

**Current Configuration**:
```yaml
# render.yaml
disk:
  name: del-mar-data
  mountPath: /app/data
  sizeGB: 1
```

```python
# session_manager.py
def __init__(self, db_path: str = "data/sessions.db"):
    self.db_path = Path(db_path)
```

**Expected Path**: `/app/data/sessions.db` (persistent)
**Actual Path**: Needs verification

---

## 🔧 Code Fixes Implemented

### Fix 1: Enhanced Database Persistence

**Changes to `services/session_manager.py`**:
- Add logging to show actual database path
- Verify database file location on startup
- Use absolute path for persistent disk
- Add database health check

### Fix 2: Session Recovery on Restart

**Changes to `app.py`**:
- Detect interrupted sessions on startup
- Mark them as "interrupted" status
- Provide clear error messages to users
- Allow graceful degradation

### Fix 3: Health Check Resilience

**Changes to `app.py`**:
- Ensure `/health` endpoint responds quickly
- Don't block health checks during scraping
- Add timeout protection

### Fix 4: Better Error Handling

**Changes to `services/captcha_solver.py`**:
- More detailed error messages
- Suggest specific fixes based on error type
- Add diagnostic information to logs

---

## 📊 Verification Steps

After fixes are deployed:

### 1. Check Database Location
```bash
# SSH into Render container (if possible) or check logs
ls -la /app/data/
# Should show: sessions.db
```

### 2. Verify Session Persistence
1. Start an analysis
2. Note the session ID
3. Wait for server to restart (or trigger restart)
4. Check if session still exists in database
5. Frontend should show "interrupted" status, not 500 error

### 3. Test 2Captcha Integration
1. Ensure API key is configured correctly
2. Start analysis for a valid past date
3. Check logs for captcha solving success
4. Verify SmartPick data is scraped

### 4. Monitor Health Checks
1. Watch Render logs during scraping
2. Ensure health checks don't timeout
3. Verify no unexpected restarts

---

## 🎯 Success Criteria

- ✅ 2Captcha API working (no ERROR_METHOD_CALL)
- ✅ Sessions persist across restarts
- ✅ Graceful handling of interrupted sessions
- ✅ No 500 errors when querying session status
- ✅ Health checks remain responsive during scraping
- ✅ Complete race card analysis with SmartPick data

---

## 📞 Support Resources

- **2Captcha Setup**: See `docs/2CAPTCHA_SETUP.md`
- **2Captcha Troubleshooting**: See `2CAPTCHA_TROUBLESHOOTING.md`
- **Deployment Guide**: See `DEPLOYMENT_GUIDE.md`
- **2Captcha Support**: https://2captcha.com/support
- **Render Support**: https://render.com/docs

---

## 🔄 Next Steps

1. **User Action**: Fix 2Captcha API key (Steps above)
2. **Deploy Code Fixes**: Apply database persistence and session recovery fixes
3. **Test**: Run full analysis with valid date
4. **Monitor**: Watch logs for any issues
5. **Verify**: Confirm all success criteria met

