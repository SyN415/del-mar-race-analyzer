# 🚨 Quick Fix Guide - Production Issues

## TL;DR - What You Need to Do NOW

### 🔴 Critical: Fix 2Captcha API Key

Your 2Captcha API key is not working. This is blocking all SmartPick scraping.

**Quick Test**:
```python
from twocaptcha import TwoCaptcha
solver = TwoCaptcha('YOUR_API_KEY_HERE')
result = solver.hcaptcha(
    sitekey='10000000-ffff-ffff-ffff-000000000001',
    url='https://2captcha.com/demo/hcaptcha'
)
print(f"✅ Works! Token: {result['code'][:50]}...")
```

**If it fails**:
1. Check balance: https://2captcha.com/enterpage
2. Verify hCaptcha enabled: https://2captcha.com/setting
3. Get new key if needed: https://2captcha.com/enterpage

**Update Render**:
1. Go to: https://dashboard.render.com
2. Select: `del-mar-race-analyzer`
3. Environment → Edit `TWOCAPTCHA_API_KEY`
4. Paste key (no quotes, no spaces)
5. Save → Auto-redeploys

---

## 🟡 Code Fixes Applied

I've already fixed the code issues:

✅ **Database Persistence** - Now logs path and verifies creation
✅ **Session Recovery** - Interrupted sessions marked clearly
✅ **Error Messages** - Helpful troubleshooting for 2Captcha errors
✅ **Health Checks** - Increased timeout to prevent restarts

**You need to**:
1. Commit and push these changes
2. Fix your 2Captcha API key
3. Test with a new analysis

---

## 📋 Quick Checklist

### Before Testing:
- [ ] 2Captcha API key is valid (32 chars)
- [ ] 2Captcha balance > $0.50
- [ ] hCaptcha enabled in 2Captcha settings
- [ ] Code changes committed and pushed
- [ ] Render deployed latest code

### After Deployment:
- [ ] Check logs for: `✅ Database initialized successfully`
- [ ] Check logs for: `✅ No interrupted sessions found`
- [ ] Start test analysis with valid past date
- [ ] Verify: `✅ Captcha solved!` in logs
- [ ] Confirm: SmartPick data scraped successfully

---

## 🔍 What to Look For in Logs

### ✅ Good Signs:
```
📁 SessionManager initialized with database path: /app/data/sessions.db
✅ Database initialized successfully
✅ No interrupted sessions found
✅ 2Captcha solver initialized
🔐 Solving hCaptcha for https://...
✅ Captcha solved! (#1, cost: $0.0030)
```

### ❌ Bad Signs:
```
❌ Error solving captcha via wrapper: ERROR_METHOD_CALL
   ⚠️  ERROR_METHOD_CALL typically means:
      1. Invalid API key format
      2. Insufficient account balance
      3. hCaptcha not enabled
```

**If you see this** → Fix 2Captcha API key (steps above)

---

## 🚀 Deploy Commands

```bash
# Commit the fixes
git add .
git commit -m "Fix: Database persistence, session recovery, enhanced error handling"
git push origin master

# Render will auto-deploy
# Or manually trigger from dashboard
```

---

## 📞 Need Help?

1. **2Captcha Issues**: See `PRODUCTION_ISSUE_RESOLUTION.md`
2. **Detailed Fixes**: See `FIXES_APPLIED.md`
3. **2Captcha Support**: https://2captcha.com/support

---

## ⏱️ Time Estimate

- Fix 2Captcha API key: **5 minutes**
- Deploy code changes: **2 minutes**
- Test analysis: **5-10 minutes**
- **Total: ~15 minutes**

---

## 🎯 Success = All These Working:

1. ✅ 2Captcha solving captchas
2. ✅ SmartPick data being scraped
3. ✅ No server restarts during scraping
4. ✅ Sessions persist across restarts
5. ✅ Complete race card analysis with predictions

