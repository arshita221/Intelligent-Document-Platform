import re
from typing import Optional

def parse_financial_number(val: Optional[str]) -> Optional[float]:
    """
    Parses financial strings into floats.
    Handles:
    - Currency symbols ($, ₹, €, £, etc.)
    - Commas in US (1,234.56) and Indian (1,23,456.78) formats
    - Parentheses for negative values: (5,000) -> -5000.0
    - Explicit negative signs: -5,000 -> -5000.0
    - Whitespace and non-breaking spaces
    """
    if val is None:
        return None
    
    if isinstance(val, (int, float)):
        return float(val)
        
    s = str(val).strip()
    if not s or s.lower() in ("null", "none", "n/a", "-", "--", ""):
        return None
        
    # Check for parentheses negative representation: (1,234.56) or (1234.56)
    is_negative = False
    if s.startswith("(") and s.endswith(")"):
        is_negative = True
        s = s[1:-1].strip()
    elif s.startswith("-"):
        is_negative = True
        s = s[1:].strip()
        
    # Strip currency symbols and non-numeric chars except digits and dot
    # Remove currency symbols and letters
    s = re.sub(r'[^\d.,]', '', s)
    
    if not s:
        return None
        
    # Handle European format (e.g., 1.234,56) vs Standard (1,234.56)
    # If comma is last separator and followed by 1 or 2 digits, it might be decimal separator
    if ',' in s and '.' in s:
        if s.rfind(',') > s.rfind('.'):
            # European format: 1.234,56 -> 1234.56
            s = s.replace('.', '').replace(',', '.')
        else:
            # Standard format: 1,234.56 -> 1234.56
            s = s.replace(',', '')
    elif ',' in s:
        # Check if comma is decimal separator (e.g. "1234,56") or thousand separator ("1,234")
        parts = s.split(',')
        if len(parts) == 2 and len(parts[1]) in (1, 2) and not parts[0].endswith(('000', '00')):
            s = s.replace(',', '.')
        else:
            s = s.replace(',', '')
            
    try:
        num = float(s)
        return -num if is_negative else num
    except ValueError:
        return None

def normalize_field_value(raw_val: Optional[str]) -> Optional[float]:
    """Helper to convert field value to float or return None."""
    return parse_financial_number(raw_val)
