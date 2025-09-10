#!/usr/bin/env python3
"""Direct URL test for today's race card"""

import requests
from datetime import datetime

def test_todays_race_card():
    # Build URL for today (09/05/2025)
    date_str = '09/05/2025'
    date_obj = datetime.strptime(date_str, '%m/%d/%Y')
    formatted_date = date_obj.strftime('%m%d%y')  # Should be 090525
    
    url = f'https://www.equibase.com/static/entry/DMR{formatted_date}USA-EQB.html?SAP=viewe2'
    print(f'Testing URL: {url}')
    
    try:
        response = requests.get(url, timeout=15)
        print(f'Status Code: {response.status_code}')
        print(f'Content Length: {len(response.text)} characters')
        
        if response.status_code == 200:
            # Check for race content
            content = response.text
            
            # Look for race indicators
            race_indicators = [
                'Race 1', 'Race 2', 'Race 3',
                'race-header', 'race-number',
                'Results.cfm', 'type=Horse'
            ]
            
            found_indicators = []
            for indicator in race_indicators:
                if indicator in content:
                    count = content.count(indicator)
                    found_indicators.append(f'{indicator}: {count}')
            
            if found_indicators:
                print('Found race indicators:')
                for indicator in found_indicators:
                    print(f'  - {indicator}')
            else:
                print('No race indicators found')
            
            # Save the HTML for manual inspection
            with open('todays_race_card.html', 'w', encoding='utf-8') as f:
                f.write(content)
            print('Saved HTML to todays_race_card.html')
            
            return True
        else:
            print(f'HTTP Error: {response.status_code}')
            return False
            
    except Exception as e:
        print(f'Error fetching URL: {e}')
        return False

if __name__ == '__main__':
    test_todays_race_card()
