"""
Equipment and medication normalization utilities for Del Mar Race Analyzer.
Ensures consistent equipment_changes strings so engine bonuses trigger reliably.
"""

import re
from typing import Dict, List, Optional, Set


class EquipmentNormalizer:
    """Normalizes equipment changes and medication data from various sources"""
    
    # Mapping patterns to normalized tokens
    EQUIPMENT_PATTERNS = {
        # Lasix/L1 variations
        r'(?i)\b(?:first[- ]?time\s+)?lasix\b': 'L1',
        r'(?i)\bL1\b': 'L1',
        r'(?i)\bfirst[- ]?time\s+L\b': 'L1',
        
        # Blinkers variations
        r'(?i)\bblinkers?\s+on\b': 'Blinkers On',
        r'(?i)\bblinkers?\s+off\b': 'Blinkers Off',
        r'(?i)\bblinkers?\s+added\b': 'Blinkers On',
        r'(?i)\bblinkers?\s+removed\b': 'Blinkers Off',
        
        # Other common equipment
        r'(?i)\btongue[- ]?tie\s+on\b': 'Tongue Tie On',
        r'(?i)\btongue[- ]?tie\s+off\b': 'Tongue Tie Off',
        r'(?i)\bvisor\s+on\b': 'Visor On',
        r'(?i)\bvisor\s+off\b': 'Visor Off',
        r'(?i)\bshadow[- ]?roll\s+on\b': 'Shadow Roll On',
        r'(?i)\bshadow[- ]?roll\s+off\b': 'Shadow Roll Off',
    }
    
    def __init__(self):
        self.compiled_patterns = {
            re.compile(pattern): replacement 
            for pattern, replacement in self.EQUIPMENT_PATTERNS.items()
        }
    
    def normalize_equipment_string(self, equipment_text: Optional[str]) -> str:
        """
        Normalize a single equipment string.
        
        Args:
            equipment_text: Raw equipment string from scraper
            
        Returns:
            Normalized equipment string with standardized tokens
        """
        if not equipment_text or not equipment_text.strip():
            return ""
        
        normalized = equipment_text.strip()
        
        # Apply all pattern replacements
        for pattern, replacement in self.compiled_patterns.items():
            normalized = pattern.sub(replacement, normalized)
        
        # Clean up extra whitespace and separators
        normalized = re.sub(r'\s*[,;]\s*', ', ', normalized)
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        return normalized
    
    def extract_equipment_tokens(self, equipment_text: Optional[str]) -> Set[str]:
        """
        Extract individual equipment tokens from normalized string.
        
        Args:
            equipment_text: Equipment string (raw or normalized)
            
        Returns:
            Set of individual equipment tokens
        """
        normalized = self.normalize_equipment_string(equipment_text)
        if not normalized:
            return set()
        
        # Split on common separators and clean
        tokens = re.split(r'[,;]+', normalized)
        return {token.strip() for token in tokens if token.strip()}
    
    def normalize_horse_equipment(self, horse_data: Dict) -> Dict:
        """
        Normalize equipment data for a single horse entry.
        Handles both 'equipment_changes' and 'medication' fields.
        
        Args:
            horse_data: Horse dictionary with potential equipment fields
            
        Returns:
            Updated horse dictionary with normalized equipment_changes field
        """
        equipment_parts = []
        
        # Handle equipment_changes field
        if 'equipment_changes' in horse_data and horse_data['equipment_changes']:
            equipment_parts.append(str(horse_data['equipment_changes']))
        
        # Handle medication field (convert to equipment_changes)
        if 'medication' in horse_data and horse_data['medication']:
            medication = str(horse_data['medication']).strip()
            if medication:
                equipment_parts.append(medication)
            # Remove the separate medication field
            horse_data.pop('medication', None)
        
        # Combine and normalize all equipment
        combined_equipment = ', '.join(equipment_parts)
        normalized_equipment = self.normalize_equipment_string(combined_equipment)
        
        # Update the horse data
        horse_data['equipment_changes'] = normalized_equipment
        
        return horse_data
    
    def normalize_race_equipment(self, race_data: Dict) -> Dict:
        """
        Normalize equipment for all horses in a race.
        
        Args:
            race_data: Race dictionary containing horses list
            
        Returns:
            Updated race dictionary with normalized equipment
        """
        if 'horses' in race_data:
            for horse in race_data['horses']:
                self.normalize_horse_equipment(horse)
        
        return race_data
    
    def normalize_card_equipment(self, card_data: Dict) -> Dict:
        """
        Normalize equipment for all horses in a race card.
        
        Args:
            card_data: Race card dictionary containing races list
            
        Returns:
            Updated card dictionary with normalized equipment
        """
        if 'races' in card_data:
            for race in card_data['races']:
                self.normalize_race_equipment(race)
        
        return card_data
    
    def validate_equipment_coverage(self, card_data: Dict) -> Dict:
        """
        Validate equipment coverage and return statistics.
        
        Args:
            card_data: Race card dictionary
            
        Returns:
            Dictionary with validation statistics
        """
        stats = {
            'total_horses': 0,
            'horses_with_equipment': 0,
            'horses_missing_equipment': [],
            'equipment_tokens_found': set(),
            'races_analyzed': 0
        }
        
        for race in card_data.get('races', []):
            stats['races_analyzed'] += 1
            race_num = race.get('race_number', 'Unknown')
            
            for horse in race.get('horses', []):
                stats['total_horses'] += 1
                horse_name = horse.get('name', 'Unknown')
                equipment = horse.get('equipment_changes', '')
                
                if equipment and equipment.strip():
                    stats['horses_with_equipment'] += 1
                    tokens = self.extract_equipment_tokens(equipment)
                    stats['equipment_tokens_found'].update(tokens)
                else:
                    stats['horses_missing_equipment'].append({
                        'race': race_num,
                        'horse': horse_name
                    })
        
        stats['equipment_tokens_found'] = list(stats['equipment_tokens_found'])
        stats['coverage_percentage'] = (
            (stats['horses_with_equipment'] / stats['total_horses'] * 100) 
            if stats['total_horses'] > 0 else 0
        )
        
        return stats


# Global normalizer instance
normalizer = EquipmentNormalizer()

# Convenience functions for easy import
def normalize_equipment(equipment_text: Optional[str]) -> str:
    """Normalize equipment string"""
    return normalizer.normalize_equipment_string(equipment_text)

def normalize_horse(horse_data: Dict) -> Dict:
    """Normalize equipment for a horse"""
    return normalizer.normalize_horse_equipment(horse_data)

def normalize_race(race_data: Dict) -> Dict:
    """Normalize equipment for a race"""
    return normalizer.normalize_race_equipment(race_data)

def normalize_card(card_data: Dict) -> Dict:
    """Normalize equipment for a race card"""
    return normalizer.normalize_card_equipment(card_data)

def validate_card(card_data: Dict) -> Dict:
    """Validate equipment coverage in a race card"""
    return normalizer.validate_equipment_coverage(card_data)
