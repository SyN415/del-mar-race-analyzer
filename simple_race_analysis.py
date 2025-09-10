#!/usr/bin/env python3
"""
Simple race analysis for Del Mar 09/05/2025
Bypasses terminal interception issues
"""

import json
import os
from datetime import datetime

def analyze_race_card():
    """Analyze the race card and provide predictions"""
    
    # Load race card
    race_card_file = 'del_mar_09_05_2025_races.json'
    if not os.path.exists(race_card_file):
        print(f"❌ Race card file not found: {race_card_file}")
        return
    
    with open(race_card_file, 'r') as f:
        race_card = json.load(f)
    
    print("🏇 DEL MAR RACE ANALYSIS - September 5, 2025")
    print("=" * 60)
    print(f"Track: {race_card['track']}")
    print(f"Date: {race_card['date']}")
    print(f"Total Races: {race_card['total_races']}")
    print()
    
    # Analyze each race
    for race in race_card['races']:
        print(f"🏁 RACE {race['race_number']} - {race['post_time']}")
        print(f"   Type: {race['race_type']}")
        print(f"   Purse: {race['purse']}")
        print(f"   Distance: {race['distance']} ({race['surface']})")
        print(f"   Horses: {race['horse_count']}")
        print()
        
        # Analyze horses
        print("   HORSES:")
        for horse in race['horses']:
            ml_odds = horse.get('morning_line', 'N/A')
            jockey = horse.get('jockey', 'N/A')
            trainer = horse.get('trainer', 'N/A')
            
            print(f"   {horse['program_number']:2d}. {horse['name']:<20} "
                  f"({horse['age_sex']}) J: {jockey:<15} T: {trainer:<15} ML: {ml_odds}")
        
        # Simple predictions based on morning line odds
        print("\n   🎯 PREDICTIONS:")
        
        # Find favorites (lowest odds)
        horses_with_odds = []
        for horse in race['horses']:
            ml = horse.get('morning_line', '99/1')
            if '/' in ml:
                try:
                    num, den = ml.split('/')
                    decimal_odds = float(num) / float(den)
                    horses_with_odds.append((horse, decimal_odds))
                except:
                    horses_with_odds.append((horse, 99.0))
        
        # Sort by odds (favorites first)
        horses_with_odds.sort(key=lambda x: x[1])
        
        if horses_with_odds:
            favorite = horses_with_odds[0][0]
            print(f"   💰 WIN: #{favorite['program_number']} {favorite['name']} (Favorite)")
            
            if len(horses_with_odds) >= 2:
                second_choice = horses_with_odds[1][0]
                print(f"   🥈 PLACE: #{second_choice['program_number']} {second_choice['name']} (Second choice)")
            
            if len(horses_with_odds) >= 3:
                third_choice = horses_with_odds[2][0]
                print(f"   🥉 SHOW: #{third_choice['program_number']} {third_choice['name']} (Third choice)")
            
            # Exacta suggestion
            if len(horses_with_odds) >= 2:
                print(f"   🎲 EXACTA: {favorite['program_number']}-{second_choice['program_number']} / {second_choice['program_number']}-{favorite['program_number']}")
        
        print("\n" + "-" * 60 + "\n")
    
    # Overall card summary
    total_horses = sum(race['horse_count'] for race in race_card['races'])
    print(f"📊 CARD SUMMARY:")
    print(f"   Total Horses: {total_horses}")
    print(f"   Average Field Size: {total_horses / len(race_card['races']):.1f}")
    
    # Save analysis
    analysis_file = f"analysis_results_{race_card['date'].replace('/', '_')}.txt"
    with open(analysis_file, 'w') as f:
        f.write(f"Del Mar Race Analysis - {race_card['date']}\n")
        f.write("=" * 50 + "\n\n")
        for race in race_card['races']:
            f.write(f"Race {race['race_number']}: {race['race_type']}\n")
            f.write(f"Distance: {race['distance']} ({race['surface']})\n")
            f.write(f"Purse: {race['purse']}\n")
            f.write(f"Horses: {race['horse_count']}\n\n")
    
    print(f"\n💾 Analysis saved to: {analysis_file}")

if __name__ == '__main__':
    analyze_race_card()
