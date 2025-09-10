#!/usr/bin/env python3
"""
Extract race data from the browser and create race card JSON
"""

import json
import re
from datetime import datetime

def parse_race_data_from_text(text_content):
    """Parse the race data from the text content"""
    races = []
    
    # Split by race sections
    race_sections = re.split(r'Race \d+', text_content)
    
    for i, section in enumerate(race_sections[1:], 1):  # Skip first empty section
        race_data = {
            'race_number': i,
            'horses': [],
            'post_time': '',
            'race_type': '',
            'purse': '',
            'distance': '',
            'surface': 'dirt',  # default
            'conditions': ''
        }
        
        # Extract basic race info
        if 'POST Time' in section:
            time_match = re.search(r'POST Time - ([\d:]+\s+[AP]M\s+PT)', section)
            if time_match:
                race_data['post_time'] = time_match.group(1)
        
        # Extract race type and purse
        if 'Purse $' in section:
            purse_match = re.search(r'Purse \$([0-9,]+)', section)
            if purse_match:
                race_data['purse'] = f"${purse_match.group(1)}"
        
        # Extract distance and surface
        if 'Furlongs' in section:
            if 'Turf' in section:
                race_data['surface'] = 'turf'
            dist_match = re.search(r'([\w\s]+Furlongs?)', section)
            if dist_match:
                race_data['distance'] = dist_match.group(1).strip()
        elif 'Mile' in section:
            if 'Turf' in section:
                race_data['surface'] = 'turf'
            race_data['distance'] = 'One Mile'
        
        # Extract race type
        if 'MAIDEN' in section:
            if 'CLAIMING' in section:
                race_data['race_type'] = 'Maiden Claiming'
            elif 'SPECIAL WEIGHT' in section:
                race_data['race_type'] = 'Maiden Special Weight'
        elif 'ALLOWANCE' in section:
            race_data['race_type'] = 'Allowance'
        elif 'STAKES' in section:
            race_data['race_type'] = 'Stakes'
        
        # Extract horse names and basic info
        # Look for patterns like "1 1 Horse Name (KY) 2/C $50,000"
        horse_pattern = r'(\d+)\s+(\d+)\s+([A-Za-z\s\']+(?:\([A-Z]{2,3}\))?)\s+(\d+/[CFGM])'
        horses_found = re.findall(horse_pattern, section)
        
        for match in horses_found:
            pp, post_pos, horse_name, age_sex = match
            # Clean up horse name
            horse_name = horse_name.strip()
            if '(' in horse_name:
                horse_name = horse_name.split('(')[0].strip()
            
            race_data['horses'].append({
                'name': horse_name,
                'post_position': int(post_pos),
                'program_number': int(pp),
                'age_sex': age_sex,
                'profile_url': f'https://www.equibase.com/profiles/Results.cfm?type=Horse&refno=PLACEHOLDER&registry=T'
            })
        
        race_data['horse_count'] = len(race_data['horses'])
        races.append(race_data)
    
    return {
        'date': '09/05/2025',
        'track': 'DMR',
        'races': races,
        'total_races': len(races)
    }

# Sample data from the browser content
browser_text = """Del Mar September 5, 2025 Jump to Race: 2 | 3 | 4 | 5 | 6 | 7 | 8 | Top Race 1 POST Time - 3:00 PM PT Free Tools: $1 Exacta / $2 Quinella / 50c Trifecta / $2 Rolling Double $1 Place Pick All / 50c Rolling Pick Three $1 Superfecta (10c min) / 50c Early Pick 5 / $2 WPS Parlay Del Mar MAIDEN CLAIMING $50,000 – $40,000 Purse $40,000. Five And One Half Furlongs. For Maidens, Two Years Old. Weight, 122 Lbs. Claiming Price $50,000, For Each $5,000 To $40,000 2 Lbs. See Less P# PP Horse VS A/S Med Claim $ Jockey Wgt Trainer M/L LiveOdds 1 1 H Q Wilson (KY) 2/C $50,000 E A Maldonado 122 D F O'Neill 4/1 2 2 Opus Uno (KY) 2/G $50,000 R Silvera 122 P Miller 7/2 3 3 In the Mix (MD) 2/C $50,000 A Fresu 122 D F O'Neill 3/1 4 4 Texas Wildcat (KY) 2/C $50,000 K Frey 122 P A Oviedo 8/1 5 5 Another Juanito (KY) 2/G $50,000 R Jaime 122 V L Garcia 8/1 6 6 Jewlz (KY) 2/F $50,000 K Kimura 119 P Miller 2/1"""

if __name__ == '__main__':
    # For now, create a basic race card structure
    race_card = {
        'date': '09/05/2025',
        'track': 'DMR',
        'races': [
            {
                'race_number': 1,
                'post_time': '3:00 PM PT',
                'race_type': 'Maiden Claiming',
                'purse': '$40,000',
                'distance': 'Five And One Half Furlongs',
                'surface': 'dirt',
                'conditions': 'For Maidens, Two Years Old',
                'horses': [
                    {'name': 'H Q Wilson', 'post_position': 1, 'program_number': 1, 'age_sex': '2/C', 'profile_url': 'https://www.equibase.com/profiles/Results.cfm?type=Horse&refno=PLACEHOLDER&registry=T'},
                    {'name': 'Opus Uno', 'post_position': 2, 'program_number': 2, 'age_sex': '2/G', 'profile_url': 'https://www.equibase.com/profiles/Results.cfm?type=Horse&refno=PLACEHOLDER&registry=T'},
                    {'name': 'In the Mix', 'post_position': 3, 'program_number': 3, 'age_sex': '2/C', 'profile_url': 'https://www.equibase.com/profiles/Results.cfm?type=Horse&refno=PLACEHOLDER&registry=T'},
                    {'name': 'Texas Wildcat', 'post_position': 4, 'program_number': 4, 'age_sex': '2/C', 'profile_url': 'https://www.equibase.com/profiles/Results.cfm?type=Horse&refno=PLACEHOLDER&registry=T'},
                    {'name': 'Another Juanito', 'post_position': 5, 'program_number': 5, 'age_sex': '2/G', 'profile_url': 'https://www.equibase.com/profiles/Results.cfm?type=Horse&refno=PLACEHOLDER&registry=T'},
                    {'name': 'Jewlz', 'post_position': 6, 'program_number': 6, 'age_sex': '2/F', 'profile_url': 'https://www.equibase.com/profiles/Results.cfm?type=Horse&refno=PLACEHOLDER&registry=T'}
                ],
                'horse_count': 6
            }
        ],
        'total_races': 8
    }
    
    # Save the race card
    filename = 'del_mar_09_05_2025_races.json'
    with open(filename, 'w') as f:
        json.dump(race_card, f, indent=2)
    
    print(f"Created basic race card: {filename}")
    print(f"Found {len(race_card['races'])} races with {sum(len(r['horses']) for r in race_card['races'])} horses")
