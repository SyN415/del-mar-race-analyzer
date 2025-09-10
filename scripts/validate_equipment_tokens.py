#!/usr/bin/env python3
"""
Equipment Token Validation Script for Del Mar Race Analyzer.
Flags missing equipment tokens and validates normalization.
"""

import json
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.equipment_normalizer import validate_card, normalize_card


def load_race_card(filename: str = "del_mar_08_24_2025_races.json") -> dict:
    """Load race card data from JSON file"""
    if not os.path.exists(filename):
        print(f"Error: Race card file '{filename}' not found")
        return {}
    
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading race card: {e}")
        return {}


def print_validation_report(stats: dict):
    """Print a formatted validation report"""
    print("=" * 60)
    print("EQUIPMENT TOKEN VALIDATION REPORT")
    print("=" * 60)
    
    print(f"Races analyzed: {stats['races_analyzed']}")
    print(f"Total horses: {stats['total_horses']}")
    print(f"Horses with equipment: {stats['horses_with_equipment']}")
    print(f"Coverage: {stats['coverage_percentage']:.1f}%")
    print()
    
    if stats['equipment_tokens_found']:
        print("Equipment tokens found:")
        for token in sorted(stats['equipment_tokens_found']):
            print(f"  - {token}")
        print()
    
    if stats['horses_missing_equipment']:
        print("Horses missing equipment data:")
        for entry in stats['horses_missing_equipment']:
            print(f"  Race {entry['race']}: {entry['horse']}")
        print()
    
    # Recommendations
    print("RECOMMENDATIONS:")
    if stats['coverage_percentage'] < 50:
        print("  ⚠️  Low equipment coverage - check scraper extraction")
    elif stats['coverage_percentage'] < 80:
        print("  ⚠️  Moderate equipment coverage - some horses missing data")
    else:
        print("  ✅ Good equipment coverage")
    
    if 'L1' not in stats['equipment_tokens_found']:
        print("  ⚠️  No L1 tokens found - check Lasix normalization")
    else:
        print("  ✅ L1 tokens found")
    
    blinkers_found = any('Blinkers' in token for token in stats['equipment_tokens_found'])
    if not blinkers_found:
        print("  ⚠️  No Blinkers tokens found - check blinkers normalization")
    else:
        print("  ✅ Blinkers tokens found")


def main():
    """Main validation function"""
    # Allow custom filename as argument
    filename = sys.argv[1] if len(sys.argv) > 1 else "del_mar_08_24_2025_races.json"
    
    print(f"Loading race card: {filename}")
    card_data = load_race_card(filename)
    
    if not card_data:
        sys.exit(1)
    
    # Normalize equipment first
    print("Normalizing equipment tokens...")
    normalized_card = normalize_card(card_data.copy())
    
    # Validate coverage
    print("Validating equipment coverage...")
    stats = validate_card(normalized_card)
    
    # Print report
    print_validation_report(stats)
    
    # Save normalized card if requested
    if '--save-normalized' in sys.argv:
        output_file = filename.replace('.json', '_normalized.json')
        with open(output_file, 'w') as f:
            json.dump(normalized_card, f, indent=2)
        print(f"\nNormalized card saved to: {output_file}")
    
    # Exit with error code if coverage is too low
    if stats['coverage_percentage'] < 30:
        print("\n❌ Equipment coverage too low - scraper may need fixes")
        sys.exit(1)
    else:
        print("\n✅ Validation complete")


if __name__ == "__main__":
    main()
