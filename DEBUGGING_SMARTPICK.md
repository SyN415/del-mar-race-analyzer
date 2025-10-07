# 🎯 SmartPick Scraping - Comprehensive Debugging Guide

## 📋 **Table of Contents**
1. [Current Status & Fixes](#current-status--fixes)
2. [Root Cause Analysis](#root-cause-analysis)
3. [SmartPick Fix Implementation](#smartpick-fix-implementation)
4. [Debugging Tools](#debugging-tools)
5. [Step-by-Step Debugging](#step-by-step-debugging)
6. [Common Issues & Solutions](#common-issues--solutions)
7. [Advanced Troubleshooting](#advanced-troubleshooting)

## 🚀 **Current Status & Fixes**

### ✅ **Issues Resolved (October 2025)**
1. **Angular/JavaScript Rendering**: Fixed SmartPick scraper to handle dynamic content
2. **Frontend CSS**: Resolved dark theme and cache-busting issues
3. **Captcha Detection**: Enhanced Incapsula/Imperva challenge handling
4. **URL Format**: Corrected date encoding in SmartPick URLs

### 🔧 **Current Scraper Capabilities**
- ✅ Navigating to Equibase pages (HTTP 200)
- ✅ Solving hCaptcha challenges via 2Captcha
- ✅ Handling Incapsula/Imperva WAF challenges
- ✅ Extracting data from Angular-rendered content
- ✅ Multiple fallback extraction methods
- ✅ Enhanced error handling and logging

### ⚠️ **Known Limitations**
- SmartPick data only available for upcoming races (not finished races)
- Requires 2Captcha API key for automated solving
- Some race dates may not have data available

## 🔍 **Root Cause Analysis**

### **Primary Issue: Angular/JavaScript Rendering**
The SmartPick scraper was failing because:
1. **Dynamic Content**: Equibase SmartPick pages use Angular to render horse data
2. **Timing Issues**: Data loads after initial page load via JavaScript
3. **Traditional Parsing**: HTML-only parsing couldn't see dynamically rendered content

### **Secondary Issues Identified**
1. **URL Format**: Date encoding was incorrect (MMDDYYYY vs MM/DD/YYYY)
2. **Captcha Detection**: Nested iframe hCaptcha challenges were missed
3. **Wait Strategies**: Insufficient wait times for Angular initialization

## 🛠️ **SmartPick Fix Implementation**

### **Core Fix Components**

#### 1. **Angular App Detection & Waiting**
```python
# Wait for Angular app to initialize
await page.wait_for_selector('app-root', timeout=10000)
await page.wait_for_load_state('networkidle', timeout=15000)
await page.wait_for_timeout(8000)  # Additional wait for dynamic content
```

#### 2. **Multi-Method JavaScript Extraction**
The fix implements 5 different extraction methods:
- **Method 1**: Angular component data extraction via `window.ng.probe`
- **Method 2**: Script tag data parsing
- **Method 3**: DOM element selection with horse-specific selectors
- **Method 4**: Table row parsing for traditional layouts
- **Method 5**: Horse profile link extraction

#### 3. **Enhanced Captcha Handling**
```python
# Detect Incapsula/Imperva challenges
if 'incapsula' in page_content.lower() or 'imperva' in page_content.lower():
    logger.warning("🛡️  Challenge page detected - attempting to solve...")
    captcha_solved = await solve_equibase_captcha(page, self.captcha_solver)
```

#### 4. **Improved URL Construction**
```python
# Proper URL encoding
encoded_date = urllib.parse.quote(race_date)  # "09/07/2025" → "09%2F07%2F2025"
url = f"https://www.equibase.com/smartPick/smartPick.cfm/?trackId={track_id}&raceDate={encoded_date}&country=USA&dayEvening={day}&raceNumber={race_number}"
```

### **Key Log Messages After Fix**
```
✅ "🛡️  Incapsula/Imperva challenge detected"
✅ "🔍 Found hCaptcha in nested iframe"
✅ "🔐 Solving hCaptcha for..."
✅ "✅ Captcha solved!"
✅ "✅ Found app-root element"
✅ "✅ Found 8 horses via JavaScript extraction"
```

## 🛠️ **Debugging Tools**

### **1. debug_smartpick_url.py**
**Purpose**: Comprehensive SmartPick URL and content testing
**Features**:
- Tests multiple URL formats
- Captures screenshots and HTML
- Detects redirects and challenges
- Analyzes page content for horse data

**Usage**:
```bash
python debug_smartpick_url.py SA 09/28/2024 1
```

**Output**:
- Detailed URL testing results
- HTML files saved to `debug_output/`
- Screenshots for visual inspection
- Content analysis with link counts

### **2. test_smartpick_urls_simple.py**
**Purpose**: Quick URL validation without Playwright
**Features**:
- Tests URL formats with requests library
- Fast validation of URL construction
- Error indicator detection
- Content length analysis

**Usage**:
```bash
python test_smartpick_urls_simple.py SA 09/28/2024 1
```

### **3. smartpick_fix.py**
**Purpose**: Complete SmartPick fix implementation
**Features**:
- Fixed Angular handling
- Multiple extraction methods
- Enhanced captcha detection
- Improved error handling

### **4. smartpick_scraper_patch.py**
**Purpose**: Easy patch application
**Features**:
- Backs up original file
- Applies fix automatically
- Verifies patch application

**Usage**:
```bash
python smartpick_scraper_patch.py
```

## 📋 **Step-by-Step Debugging**

### **Step 1: Verify Prerequisites**
```bash
# Check 2Captcha API key is set
echo $TWOCAPTCHA_API_KEY

# Verify 2Captcha balance
curl "https://2captcha.com/res.php?key=$TWOCAPTCHA_API_KEY&action=getbalance"
```

### **Step 2: Run Comprehensive Debug Test**
```bash
# Full debugging with Playwright
python debug_smartpick_url.py SA 09/28/2024 1

# Quick URL validation
python test_smartpick_urls_simple.py SA 09/28/2024 1
```

### **Step 3: Analyze Debug Output**
Check these files in `debug_output/`:
- `smartpick_test_1_SA_r1.html` - Page HTML content
- `smartpick_test_1_SA_r1.png` - Visual screenshot
- Look for Angular app elements and horse data

### **Step 4: Manual Browser Verification**
1. Open the SmartPick URL manually:
   ```
   https://www.equibase.com/smartPick/smartPick.cfm/?trackId=SA&raceDate=09%2F28%2F2024&country=USA&dayEvening=D&raceNumber=1
   ```

2. Verify:
   - Page loads without errors
   - Horse data is visible
   - No captcha challenges (or they're solvable)
   - Date and track match expectations

### **Step 5: Check Application Logs**
Look for these key messages:
```
✅ "🛡️  Incapsula/Imperva challenge detected"
✅ "🔍 Found hCaptcha in nested iframe"
✅ "✅ Found app-root element"
✅ "✅ Found X horses via JavaScript extraction"
```

### **Step 6: Test with Different Dates**
Try multiple dates to identify patterns:
```bash
# Test recent past dates (more likely to have data)
python debug_smartpick_url.py SA 08/24/2024 1
python debug_smartpick_url.py DMR 08/24/2024 1

# Test different race numbers
python debug_smartpick_url.py SA 08/24/2024 3
```

## ⚠️ **Common Issues & Solutions**

### **Issue 1: No Horse Data Found**
**Symptoms**:
```
⚠️  JavaScript extraction returned null
🐎 Found 0 horses via HTML parsing
```

**Solutions**:
1. **Check Date**: Use past dates, not future dates
2. **Verify Race Number**: Some races may be finished/cancelled
3. **Check 2Captcha**: Ensure API key is valid and has balance
4. **Wait Longer**: Increase timeout values in environment

### **Issue 2: Captcha Challenges**
**Symptoms**:
```
🛡️  Challenge page detected
❌ Failed to solve captcha
```

**Solutions**:
1. **Verify 2Captcha Key**: Check `TWOCAPTCHA_API_KEY` environment variable
2. **Check Balance**: Ensure sufficient 2Captcha credits
3. **Manual Solve**: Try solving captcha manually in browser first

### **Issue 3: Angular App Not Loading**
**Symptoms**:
```
⚠️  Could not find app-root
⚠️  JavaScript extraction failed
```

**Solutions**:
1. **Network Issues**: Check internet connectivity
2. **Browser Detection**: Ensure user-agent is not blocked
3. **Wait Times**: Increase wait timeouts for slow connections

### **Issue 4: Redirect Loops**
**Symptoms**:
```
⚠️  Redirected from: [URL]
⚠️  To: [different URL]
```

**Solutions**:
1. **Session Issues**: Visit homepage first to establish session
2. **Geo-blocking**: May need VPN for some regions
3. **Rate Limiting**: Reduce request frequency

## 🔧 **Advanced Troubleshooting**

### **Enable Debug Logging**
```python
import logging
logging.getLogger('scrapers.smartpick_playwright').setLevel(logging.DEBUG)
```

### **Manual Patch Application**
If the fix needs to be reapplied:
```bash
# Apply the SmartPick fix
python smartpick_scraper_patch.py

# Verify the fix was applied
grep -n "Angular app" scrapers/smartpick_playwright.py
```

### **Performance Optimization**
```bash
# Reduce concurrent scraping
export MAX_CONCURRENT_RACES=2

# Increase timeouts
export SCRAPER_TIMEOUT=60

# Use fallback scraper
export USE_FALLBACK_SCRAPER=true
```

### **Testing Different Extraction Methods**
The fix includes 5 extraction methods. To test specific methods:
```python
# Modify smartpick_fix.py to test individual methods
# Comment out methods 1-4 to test only method 5, etc.
```

## 📊 **Success Indicators**

### **✅ Successful SmartPick Scraping**
```
🌐 Fetching SmartPick URL: https://www.equibase.com/smartPick/...
🏠 Visiting Equibase homepage to establish session...
🍪 Accepted cookies
🎯 Navigating to SmartPick page...
📡 HTTP Status: 200
⏳ Waiting for Angular app to initialize...
✅ Found app-root element
✅ Found 8 horses via JavaScript extraction
🐎 Total horses parsed: 8
```

### **✅ Successful Captcha Handling**
```
🛡️  Challenge page detected - attempting to solve...
🔍 Found hCaptcha in nested iframe
🔐 Solving hCaptcha for...
✅ Captcha solved!
⏳ Waiting for page to reload after captcha...
✅ No challenge page detected, proceeding with scraping
```

## 🚀 **Production Deployment**

### **Environment Variables Required**
```bash
OPENROUTER_API_KEY=your_key_here
TWOCAPTCHA_API_KEY=your_2captcha_key_here
ENVIRONMENT=production
LOG_LEVEL=INFO
```

### **Monitoring in Production**
1. **Check Logs**: Monitor for success indicators above
2. **2Captcha Balance**: Set up alerts for low balance
3. **Error Rates**: Track failed vs successful scrapes
4. **Performance**: Monitor scraping times and timeouts

## 📞 **Getting Help**

### **Debug Information to Collect**
1. **Full Log Output**: Include all scraper messages
2. **Debug Files**: HTML and screenshots from `debug_output/`
3. **Environment Variables**: Verify all required variables are set
4. **Test Results**: Output from debugging tools

### **Contact Support**
- Include all debug information when reporting issues
- Specify track, date, and race number
- Mention any error messages seen
- Provide steps to reproduce the issue

---

**Last Updated**: October 7, 2025
**Version**: 2.0.0 (SmartPick Angular Fix)
**Status**: Production Ready ✅

