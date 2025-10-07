#!/usr/bin/env python3
"""
Patch to apply the fix to the existing SmartPick scraper
"""
import os
import shutil
from datetime import datetime

def apply_smartpick_fix():
    """Apply the fix to the existing SmartPick scraper"""
    
    # Backup the original file
    original_file = 'scrapers/smartpick_playwright.py'
    backup_file = f'scrapers/smartpick_playwright.py.backup.{datetime.now().strftime("%Y%m%d_%H%M%S")}'
    
    if os.path.exists(original_file):
        shutil.copy2(original_file, backup_file)
        print(f"✅ Backed up original file to: {backup_file}")
    else:
        print(f"❌ Original file not found: {original_file}")
        return False
    
    # Read the fixed version
    with open('smartpick_fix.py', 'r') as f:
        fixed_content = f.read()
    
    # Write the fixed version to the original file
    with open(original_file, 'w') as f:
        f.write(fixed_content)
    
    print(f"✅ Applied fix to: {original_file}")
    print("\n🔧 Key changes made:")
    print("1. Added proper Angular app detection and waiting")
    print("2. Implemented JavaScript extraction methods for Angular data")
    print("3. Added multiple fallback methods for data extraction")
    print("4. Improved wait times for dynamic content loading")
    print("5. Enhanced error handling and logging")
    
    return True

if __name__ == "__main__":
    print("🔧 Applying SmartPick scraper fix...")
    if apply_smartpick_fix():
        print("\n✅ Fix applied successfully!")
        print("\n📝 To test the fix:")
        print("1. Deploy the updated code to Render")
        print("2. Try scraping a race with data (e.g., SA 10/05/2025)")
        print("3. Check the logs for improved output")
    else:
        print("\n❌ Failed to apply fix")