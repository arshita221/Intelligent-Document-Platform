import re
from typing import Optional

# Non-numeric field keywords that represent identifiers, dates, contacts, or non-monetary text
NON_NUMERIC_FIELD_KEYWORDS = {
    "invoice_no", "invoice_number", "invoiceno", "invoice no", "delivery_note", "delivery note",
    "order_no", "order_number", "order no", "ref_no", "reference_no", "reference no", "reference",
    "date", "dated", "invoice_date", "report_date", "period", "due_date", "payment_terms",
    "mode", "terms", "phone", "mobile", "contact", "sales_man", "salesman", "sales_person", "salesperson", "gstin", "pan",
    "address", "market", "company_name", "company", "buyer", "seller", "customer", "vendor",
    "supplier", "report_title", "title", "currency", "currency_unit", "unit", "notes", "note",
    "description", "email", "website", "location", "city", "state", "country", "zip", "pincode",
    "dispatched", "dispatch", "terms_of_delivery", "delivery_terms", "buyer_name", "buyer_address"
}

def parse_financial_number(val: Optional[str], field_name: Optional[str] = None) -> Optional[float]:
    """
    Parses financial strings into floats.
    Guards against converting non-monetary strings (IDs, dates, phone numbers, terms) into numeric values.
    """
    if val is None or isinstance(val, bool):
        return None
        
    if isinstance(val, (int, float)):
        return float(val)

    s = str(val).strip()
    if not s or s.lower() in ("null", "none", "n/a", "-", "--", ""):
        return None

    # 1. Guard based on field name semantics (using word boundary matching so 'date' does not match 'rate')
    if field_name:
        fn_lower = str(field_name).lower().strip()
        for keyword in NON_NUMERIC_FIELD_KEYWORDS:
            kw_clean = keyword.replace("_", r"[\s_]?")
            if re.search(r'\b' + kw_clean + r'\b', fn_lower):
                return None


    # 2. Check for date patterns e.g. 16-Jul-25, 16/07/2025, March 31, 2017, 2025-11-18
    date_pattern = r'(\b\d{1,4}[-/\.]([a-zA-Z]{3}|\d{1,2})[-/\.]\d{1,4}\b|\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b|\b\d{1,2}\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{2,4}\b)'
    if re.search(date_pattern, s, re.IGNORECASE):
        return None

    # 3. Check for invoice/ID slash/backslash patterns e.g. SCI/25-26/13331
    if "/" in s or "\\" in s:
        return None

    # 4. Check for phone number patterns or embedded name + phone e.g. +1-800-555-0199 or (800) 555-0199
    if (re.search(r'\+\d{1,3}[\s.-]?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}', s) or 
        re.search(r'\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b', s) or 
        re.search(r'\(\d{3}\)[\s.-]?\d{3}[\s.-]?\d{4}', s)):
        return None

    if "(" in s and ")" in s and not re.match(r'^\s*\(\s*[\d.,]+\s*\)\s*$', s):
        return None


    # 5. Check for non-monetary alphabetic text
    # Allowed currency codes and quantity units
    allowed_units_pattern = r'\b(usd|inr|eur|gbp|rs|rs\.|cr|lakh|lakhs|dr|nil|zero|pcs|pc|units|unit|kg|g|lbs|hrs|hours|%)\b'
    
    # Strip currency symbols and allowed units to check for other letters
    cleaned_s = re.sub(r'[$₹€£¥]', '', s, flags=re.IGNORECASE)
    cleaned_s = re.sub(allowed_units_pattern, '', cleaned_s, flags=re.IGNORECASE).strip()

    if re.search(r'[a-zA-Z]', cleaned_s):
        # Contains non-monetary words e.g. "Area LOHAPPOOL", "Cash", "Destination"
        return None

    # Handle "Nil" or "Zero"
    if s.lower() in ("nil", "zero"):
        return 0.0

    # 6. Check for parentheses negative representation: (1,234.56) or -1,234.56
    is_negative = False
    num_str = s
    if num_str.startswith("(") and num_str.endswith(")"):
        is_negative = True
        num_str = num_str[1:-1].strip()
    elif num_str.startswith("-"):
        is_negative = True
        num_str = num_str[1:].strip()

    # Strip remaining non-numeric chars except digits and dot/comma
    num_str = re.sub(r'[^\d.,]', '', num_str)
    if not num_str:
        return None

    # Format conversion (European vs Standard)
    if ',' in num_str and '.' in num_str:
        if num_str.rfind(',') > num_str.rfind('.'):
            num_str = num_str.replace('.', '').replace(',', '.')
        else:
            num_str = num_str.replace(',', '')
    elif ',' in num_str:
        parts = num_str.split(',')
        if len(parts) == 2 and len(parts[1]) in (1, 2) and not parts[0].endswith(('000', '00')):
            num_str = num_str.replace(',', '.')
        else:
            num_str = num_str.replace(',', '')

    try:
        num = float(num_str)
        return -num if is_negative else num
    except ValueError:
        return None

def normalize_field_value(raw_val: Optional[str], field_name: Optional[str] = None) -> Optional[float]:
    """Helper to convert field value to float or return None."""
    return parse_financial_number(raw_val, field_name)

