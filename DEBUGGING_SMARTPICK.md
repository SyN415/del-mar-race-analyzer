# SmartPick Scraping Issue - Debugging Guide

## Current Status

The SmartPick scraper is successfully:
- ✅ Navigating to Equibase pages (HTTP 200)
- ✅ Solving captchas
- ✅ Finding 267 links on the page
- ✅ Finding 11 tables on the page
- ✅ Detecting "SmartPick" text in the page

But it's NOT finding:
- ❌ Horse profile links (Results.cfm + type=Horse)
- ❌ The expected race date in the page content
- ❌ Any horse data to scrape

## Key Log Messages

```
⚠️  Expected date 09/28/2025 not found in page content
⚠️  No SmartPick container element found
🔗 Found 0 Results.cfm links
🐴 Found 0 type=Horse links
🐎 Found 0 horse profile links (Results.cfm + type=Horse)
```

## Possible Causes

### 1. **Date/Track Has No Data**
Even though you say the data exists on Equibase, the scraper might be:
- Getting redirected to a different page
- Seeing an error page that still returns HTTP 200
- Seeing a "no races scheduled" page

### 2. **SmartPick Page Structure Changed**
Equibase might have:
- Changed their HTML structure
- Moved to a different URL format
- Changed how they load horse data (more JavaScript)

### 3. **URL Format Issue**
The URL might need:
- Different date encoding
- Different parameters
- Different track code format

## Debugging Steps

### Step 1: Check the Saved HTML

After running a scrape, check these files:
```
logs/html/smartpick_playwright_SA_r1.html
logs/html/smartpick_playwright_SA_r1.png
```

These show exactly what the scraper saw.

### Step 2: Run the Debug Script

```bash
python test_smartpick_debug.py SA 09/28/2024 1
```

This will:
- Show detailed logging
- Save HTML and screenshots
- Tell you exactly what was found

### Step 3: Compare with Manual Browser

1. Open this URL in your browser:
   ```
   https://www.equibase.com/smartPick/smartPick.cfm/?trackId=SA&raceDate=09%2F28%2F2024&country=USA&dayEvening=D&raceNumber=1
   ```

2. Check if:
   - The page loads correctly
   - You see horse data
   - The date matches what you expect
   - There are links to horse profiles

### Step 4: Check for Redirects

The new logging will show:
```
🔗 Current URL: [actual URL after navigation]
```

If this is different from the requested URL, Equibase is redirecting.

### Step 5: Check What Dates Are in the Page

The new logging will show:
```
📅 Dates found in page: ['09/27/2024', '09/29/2024', ...]
🏇 Track codes found in page: ['SA', 'DMR', 'CD', ...]
```

This tells you what Equibase is actually showing.

## New Debugging Features Added

1. **URL Encoding**: Properly encodes the date in the URL
2. **Redirect Detection**: Logs if the page redirects to a different URL
3. **Date Variations**: Checks for dates in multiple formats (09/28/2025, 09-28-2025, 09282025)
4. **Content Analysis**: Shows what dates and track codes are actually in the page
5. **Better Logging**: More detailed output about what's found

## Next Steps

1. **Wait for Render to rebuild** (5-10 minutes) - this will deploy the new debugging
2. **Run a test scrape** and check the logs for the new debug output
3. **Share the new log output** - specifically:
   - The "Current URL" line
   - The "Dates found in page" line
   - The "Track codes found in page" line
4. **Check the saved HTML file** in logs/html/ to see what the page actually looks like

## Frontend CSS Issue

The Docker cache-busting fix has been added with a `CACHEBUST` build arg. Render should rebuild and deploy the new CSS. If it still doesn't work after the rebuild, we may need to:
1. Add a version query parameter to CSS/JS files
2. Clear Render's build cache manually
3. Check if static files are being served correctly

## Manual Testing

You can also test locally:
```bash
# Run the debug script
python test_smartpick_debug.py SA 09/28/2024 1

# Check the output files
ls -la logs/html/
```

This will create the HTML and screenshot files locally so you can inspect them.

