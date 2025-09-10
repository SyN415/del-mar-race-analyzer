#!/usr/bin/env python3
"""
Direct runner for today's race analysis
Bypasses any shell interception issues
"""

import os
import sys
import asyncio

# Set the environment variable for today's date
os.environ['RACE_DATE_STR'] = '09/05/2025'

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import and run the main function
from run_playwright_full_card import main

if __name__ == '__main__':
    print("🏇 Starting Del Mar Race Analysis for 09/05/2025")
    print("=" * 50)
    
    try:
        asyncio.run(main())
        print("\n✅ Analysis completed successfully!")
    except Exception as e:
        print(f"\n❌ Analysis failed: {e}")
        import traceback
        traceback.print_exc()
