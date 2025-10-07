# 🛠️ Debugging Tools Guide - Del Mar Race Analyzer

## 📋 **Overview**

This guide documents the debugging and fix tools created to resolve SmartPick scraping issues and frontend CSS problems. These tools were developed during the October 2025 fix cycle to address Angular/JavaScript rendering challenges and deployment issues.

## 🗂️ **New Files Created**

### **Core Debugging Tools**

| File | Purpose | Key Features |
|------|---------|--------------|
| [`debug_smartpick_url.py`](#debug_smartpick_urlpy) | Comprehensive SmartPick testing | Playwright-based, screenshots, HTML capture |
| [`test_smartpick_urls_simple.py`](#test_smartpick_urls_simplepy) | Quick URL validation | Requests-based, fast testing |
| [`smartpick_fix.py`](#smartpick_fixpy) | Complete fix implementation | Angular handling, 5 extraction methods |
| [`smartpick_scraper_patch.py`](#smartpick_scraper_patchpy) | Easy patch application | Backup, apply, verify |

---

## 🔍 **debug_smartpick_url.py**

### **Purpose**
Comprehensive SmartPick URL construction and content testing tool using Playwright browser automation.

### **Key Features**
- **Multiple URL Format Testing**: Tests 4 different URL formats
- **Browser Automation**: Full Playwright integration with real browser
- **Session Management**: Visits homepage first to establish session
- **Content Analysis**: Detailed page content parsing and analysis
- **Visual Debugging**: Captures screenshots and saves HTML
- **Cookie Handling**: Automatically accepts cookie banners
- **Redirect Detection**: Identifies and logs URL redirects

### **Usage**
```bash
# Basic usage
python debug_smartpick_url.py SA 09/28/2024 1

# With different parameters
python debug_smartpick_url.py DMR 08/24/2024 3

# Help
python debug_smartpick_url.py --help
```

### **Parameters**
- `track_id`: Track code (SA, DMR, etc.)
- `race_date`: Date in MM/DD/YYYY format
- `race_number`: Race number (1-12)

### **Output Files**
Creates files in `debug_output/` directory:
- `smartpick_test_1_SA_r1.html` - Page HTML content
- `smartpick_test_1_SA_r1.png` - Full page screenshot
- `smartpick_test_2_SA_r1.html` - Alternative URL test
- `smartpick_test_2_SA_r1.png` - Alternative URL screenshot

### **Sample Output**
```
============================================================
Testing SmartPick URL Construction
============================================================
Track: SA
Date: 09/28/2024
Race: 1
============================================================

--- Test 1: Testing URL ---
URL: https://www.equibase.com/smartPick/smartPick.cfm/?trackId=SA&raceDate=09%2F28%2F2024&country=USA&dayEvening=D&raceNumber=1
Visiting Equibase homepage...
Accepted cookies
🎯 Navigating to SmartPick page...
HTTP Status: 200
Final URL: https://www.equibase.com/smartPick/smartPick.cfm/?trackId=SA&raceDate=09%2F28%2F2024&country=USA&dayEvening=D&raceNumber=1
Page title: SmartPick
Expected date found: True
Track ID found: True
SmartPick content found: True
Total links found: 267
Results.cfm links: 12
type=Horse links: 8
Dates found in page: ['09/28/2024', '09/27/2024', '09/29/2024']
Track codes found: page: ['SA', 'DMR', 'CD', 'GP']
Saved HTML to debug_output/smartpick_test_1_SA_r1.html
Saved screenshot to debug_output/smartpick_test_1_SA_r1.png
```

### **URL Formats Tested**
1. **Current Format**: Standard SmartPick URL with encoded date
2. **No Trailing Slash**: Alternative format without slash after .cfm
3. **Dash Date Format**: YYYY-MM-DD date format
4. **Parameter Reorder**: Different parameter order

---

## ⚡ **test_smartpick_urls_simple.py**

### **Purpose**
Lightweight URL testing tool using requests library for quick validation without browser overhead.

### **Key Features**
- **Fast Testing**: No browser startup overhead
- **Multiple URL Formats**: Tests 5 different URL variations
- **Content Analysis**: Basic HTML parsing and analysis
- **Error Detection**: Identifies common error patterns
- **Redirect Tracking**: Monitors URL redirects
- **Lightweight**: Minimal dependencies, fast execution

### **Usage**
```bash
# Basic usage
python test_smartpick_urls_simple.py SA 09/28/2024 1

# Test with different date
python test_smartpick_urls_simple.py DMR 08/24/2024 3
```

### **Sample Output**
```
============================================================
Testing SmartPick URL Construction
============================================================
Track: SA
Date: 09/28/2024
Race: 1
============================================================

--- Test 1: Testing URL ---
URL: https://www.equibase.com/smartPick/smartPick.cfm/?trackId=SA&raceDate=09%2F28%2F2024&country=USA&dayEvening=D&raceNumber=1
HTTP Status: 200
Content length: 45678 bytes
Expected date found: True
Track ID found: True
SmartPick content found: True
Results.cfm links found: 12
type=Horse links found: 8
Dates found in page: ['09/28/2024', '09/27/2024']
Track codes found: ['SA', 'DMR', 'CD']
Tables found: 11
Saved HTML to debug_output/smartpick_test_1_SA_r1.html
First 500 chars: <!DOCTYPE html><html lang="en"><head>...
```

### **Error Indicators Checked**
- 'no entries', 'not available', 'no data'
- 'no results', 'no race card', 'no racing'
- 'not found', 'does not exist'
- 'no information available', 'no smartpick data'
- 'incapsula', 'imperva' (WAF challenges)

---

## 🔧 **smartpick_fix.py**

### **Purpose**
Complete SmartPick scraper fix implementation that addresses Angular/JavaScript rendering issues.

### **Key Features**
- **Angular App Detection**: Waits for Angular app initialization
- **Multiple Extraction Methods**: 5 different data extraction strategies
- **Enhanced Captcha Handling**: Improved Incapsula/Imperva detection
- **JavaScript Execution**: Direct JavaScript data extraction
- **Fallback Strategies**: Multiple fallback methods for reliability
- **Improved Logging**: Detailed progress and error reporting
- **Session Management**: Proper session establishment

### **Core Fix Components**

#### 1. **Angular App Handling**
```python
# Wait for Angular app to initialize
await page.wait_for_selector('app-root', timeout=10000)
await page.wait_for_load_state('networkidle', timeout=15000)
await page.wait_for_timeout(8000)  # Additional wait for dynamic content
```

#### 2. **Five Extraction Methods**
1. **Angular Component Data**: Extract via `window.ng.probe`
2. **Script Tag Parsing**: Parse embedded JSON data
3. **DOM Element Selection**: CSS selectors for horse elements
4. **Table Row Parsing**: Traditional HTML table parsing
5. **Link Extraction**: Horse profile link extraction

#### 3. **Enhanced Captcha Detection**
```python
# Detect Incapsula/Imperva challenges
if 'incapsula' in page_content.lower() or 'imperva' in page_content.lower():
    logger.warning("🛡️  Challenge page detected - attempting to solve...")
    captcha_solved = await solve_equibase_captcha(page, self.captcha_solver)
```

### **Usage**
```bash
# Test the fixed scraper
python smartpick_fix.py

# Or import and use programmatically
from smartpick_fix import scrape_smartpick_with_fixed_playwright
result = await scrape_smartpick_with_fixed_playwright('SA', '09/28/2024', 1)
```

### **Key Classes**
- `FixedPlaywrightSmartPickScraper`: Main scraper class with fixes
- `scrape_smartpick_with_fixed_playwright()`: Convenience function

---

## 🩹 **smartpick_scraper_patch.py**

### **Purpose**
Utility to apply the SmartPick fix to the existing scraper with proper backup and verification.

### **Key Features**
- **Automatic Backup**: Creates timestamped backup of original file
- **Patch Application**: Applies fix with verification
- **Rollback Support**: Easy rollback if needed
- **Validation**: Verifies patch was applied correctly
- **Logging**: Detailed operation logging

### **Usage**
```bash
# Apply the fix
python smartpick_scraper_patch.py

# Output:
# 🔧 Applying SmartPick scraper fix...
# ✅ Backed up original file to: scrapers/smartpick_playwright.py.backup.20251007_120833
# ✅ Applied fix to: scrapers/smartpick_playwright.py
# 
# 🔧 Key changes made:
# 1. Added proper Angular app detection and waiting
# 2. Implemented JavaScript extraction methods for Angular data
# 3. Added multiple fallback methods for data extraction
# 4. Improved wait times for dynamic content loading
# 5. Enhanced error handling and logging
# 
# ✅ Fix applied successfully!
```

### **Backup Files**
Creates backups with timestamp:
- `scrapers/smartpick_playwright.py.backup.20251007_120833`

### **Rollback**
If needed, rollback by restoring from backup:
```bash
# Find latest backup
ls -la scrapers/smartpick_playwright.py.backup.*

# Restore from backup
cp scrapers/smartpick_playwright.py.backup.20251007_120833 scrapers/smartpick_playwright.py
```

---

## 🚀 **Using the Tools Together**

### **Complete Debugging Workflow**

#### **Step 1: Quick URL Validation**
```bash
# Fast test to check URL formats
python test_smartpick_urls_simple.py SA 09/28/2024 1
```

#### **Step 2: Comprehensive Testing**
```bash
# Full browser-based testing
python debug_smartpick_url.py SA 09/28/2024 1
```

#### **Step 3: Apply Fix if Needed**
```bash
# Apply the SmartPick fix
python smartpick_scraper_patch.py
```

#### **Step 4: Test Fixed Scraper**
```bash
# Test the fixed implementation
python smartpick_fix.py
```

### **Debugging Output Analysis**

#### **Success Indicators**
```
✅ "🛡️  Incapsula/Imperva challenge detected"
✅ "🔍 Found hCaptcha in nested iframe"
✅ "✅ Captcha solved!"
✅ "✅ Found app-root element"
✅ "✅ Found 8 horses via JavaScript extraction"
```

#### **Error Indicators**
```
⚠️  Could not find app-root
⚠️  JavaScript extraction returned null
❌ Failed to solve captcha
🚫 Page appears to be blocked by WAF
```

### **Debug Files Location**
All debug tools save output to `debug_output/` directory:
- HTML files for content analysis
- PNG screenshots for visual inspection
- Log files for detailed analysis

---

## 🔧 **Integration with Main Application**

### **Applying Fixes to Production**

#### **Option 1: Patch Application**
```bash
# Apply fix to existing scraper
python smartpick_scraper_patch.py

# Deploy updated code
git add .
git commit -m "Apply SmartPick Angular fix"
git push origin main
```

#### **Option 2: Manual Integration**
Copy the fixed scraper class to the main application:
```python
# In scrapers/smartpick_playwright.py
from smartpick_fix import FixedPlaywrightSmartPickScraper

# Replace existing scraper with fixed version
```

### **Environment Configuration**
Ensure these environment variables are set:
```bash
TWOCAPTCHA_API_KEY=your_2captcha_key_here
OPENROUTER_API_KEY=your_openrouter_key_here
LOG_LEVEL=DEBUG  # For detailed debugging
```

---

## 📊 **Troubleshooting Guide**

### **Common Issues**

#### **Tool Won't Run**
```bash
# Check Python version (requires 3.8+)
python --version

# Install missing dependencies
pip install playwright beautifulsoup4 requests

# Install Playwright browsers
python -m playwright install chromium
```

#### **No Debug Output Created**
```bash
# Create debug directory manually
mkdir -p debug_output

# Check permissions
chmod 755 debug_output
```

#### **Screenshots Not Working**
```bash
# Install Playwright dependencies
python -m playwright install-deps

# Check display (for non-headless mode)
export DISPLAY=:99
```

### **Performance Optimization**

#### **Reduce Memory Usage**
```bash
# Use headless mode in debug_smartpick_url.py
browser = await p.chromium.launch(headless=True)

# Reduce timeout values
timeout=10000  # Reduce from 30000
```

#### **Faster Testing**
```bash
# Use simple test for quick validation
python test_smartpick_urls_simple.py SA 09/28/2024 1

# Limit URL formats tested
# Modify the urls_to_test list in debug tools
```

---

## 📝 **Best Practices**

### **Development Workflow**
1. **Start Simple**: Use `test_smartpick_urls_simple.py` first
2. **Comprehensive Testing**: Use `debug_smartpick_url.py` for detailed analysis
3. **Apply Fixes**: Use `smartpick_scraper_patch.py` for safe updates
4. **Verify**: Test with `smartpick_fix.py` after applying patches
5. **Monitor**: Check logs and debug output regularly

### **Debug Output Management**
```bash
# Clean old debug files
find debug_output/ -name "*.html" -mtime +7 -delete
find debug_output/ -name "*.png" -mtime +7 -delete

# Archive important debug sessions
tar -czf debug_session_20251007.tar.gz debug_output/
```

### **Version Control**
```bash
# Include debug tools in version control
git add debug_smartpick_url.py test_smartpick_urls_simple.py
git add smartpick_fix.py smartpick_scraper_patch.py
git commit -m "Add SmartPick debugging tools"

# Exclude debug output
echo "debug_output/" >> .gitignore
```

---

## 🎯 **Success Stories**

### **Issue Resolution Examples**

#### **Angular Rendering Problem**
- **Symptom**: 0 horses found despite page loading
- **Diagnosis**: Used `debug_smartpick_url.py` to capture HTML
- **Root Cause**: Angular app not rendering horse data
- **Solution**: Applied `smartpick_fix.py` with Angular handling
- **Result**: Successfully extracted 8+ horses per race

#### **Captcha Challenge Issues**
- **Symptom**: "Challenge page detected" errors
- **Diagnosis**: `debug_smartpick_url.py` showed Incapsula challenges
- **Root Cause**: Missing 2Captcha configuration
- **Solution**: Configured `TWOCAPTCHA_API_KEY` environment variable
- **Result**: Automatic captcha solving success

#### **URL Format Problems**
- **Symptom**: HTTP 200 but no race data
- **Diagnosis**: `test_smartpick_urls_simple.py` showed wrong date format
- **Root Cause**: Date encoding (MMDDYYYY vs MM/DD/YYYY)
- **Solution**: Fixed URL encoding in scraper
- **Result**: Proper race data loading

---

## 📞 **Getting Help**

### **Debug Information to Collect**
When reporting issues, include:
1. **Tool Output**: Full output from debugging tools
2. **Debug Files**: HTML and screenshots from `debug_output/`
3. **Environment**: Python version, OS, browser version
4. **Configuration**: Environment variables (redacted)
5. **Error Messages**: Complete error stack traces

### **Contact Channels**
- **GitHub Issues**: Create issue with full debug information
- **Documentation**: Check this guide and `DEBUGGING_SMARTPICK.md`
- **Community**: Join discussions for community support

---

**Last Updated**: October 7, 2025  
**Version**: 2.0.0  
**Status**: Production Ready ✅

These debugging tools have been instrumental in resolving the SmartPick scraping issues and are now part of the standard debugging toolkit for the Del Mar Race Analyzer project.