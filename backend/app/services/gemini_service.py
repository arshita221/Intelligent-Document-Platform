import json
import os
import re
import time
from typing import List, Dict, Any, Optional
from app.core.config import settings
from app.core.logging_config import logger
from app.schemas.extraction import DocumentExtraction, ExtractedField, LineItem, FinancialTable, Period, Note, RawTextPage
from app.utils.number_parser import parse_financial_number

# System prompt enforcing strict financial extraction rules
EXTRACTION_SYSTEM_PROMPT = """
You are an expert AI financial document extraction engine.
Your task is to extract ALL meaningful information from the provided financial document (Invoice, Balance Sheet, Profit & Loss Statement, or Cash Flow Statement).

STRICT EXTRACTION RULES:
1. Extract ONLY information that is explicitly visible in the document.
2. NEVER calculate missing values. If a line total, tax, subtotal, or summary value is missing or unreadable, set value to null.
3. NEVER hallucinate values or invent data.
4. Extract canonical fields as well as any arbitrary additional key-value fields visible.
5. For financial numbers:
   - Extract raw text in `value` (e.g. "$10,000.00", "(5,000)").
   - Interpret parentheses like `(5,000)` as negative numbers `-5000`.
6. For multi-period financial statements (e.g., 2023 vs 2024):
   - Group fields under their respective period label in the `periods` array.
7. Include line items, financial tables, notes, and raw text evidence wherever present.
8. Do NOT attempt to perform arithmetic or determine whether math is correct. Just extract reported values.

Document Type: {document_type}

Return your output as a SINGLE JSON object matching this exact JSON schema:
{{
  "document_type": "{document_type}",
  "fields": [
    {{
      "name": "string (canonical or raw name)",
      "value": "string or null",
      "normalized_value": number or null,
      "evidence": "string or null",
      "page_number": 1,
      "confidence": 1.0,
      "status": "EXTRACTED"
    }}
  ],
  "line_items": [
    {{
      "description": "string or null",
      "quantity": number or null,
      "unit_price": number or null,
      "amount": number or null,
      "tax": number or null,
      "total": number or null,
      "evidence": "string or null",
      "page_number": 1
    }}
  ],
  "tables": [
    {{
      "name": "string or null",
      "headers": ["header1", "header2"],
      "rows": [["cell1", "cell2"]],
      "page_number": 1,
      "evidence": "string or null"
    }}
  ],
  "periods": [
    {{
      "label": "2024",
      "fields": [
        {{
          "name": "assets",
          "value": "500000",
          "normalized_value": 500000.0,
          "evidence": "Total Assets 2024: 500,000",
          "page_number": 1,
          "confidence": 1.0,
          "status": "EXTRACTED"
        }}
      ]
    }}
  ],
  "notes": [
    {{
      "title": "string or null",
      "content": "string",
      "page_number": 1
    }}
  ]
}}
"""

def extract_with_gemini(
    document_type: str,
    raw_text_pages: List[RawTextPage],
    page_images: List[bytes],
    is_scanned: bool = False
) -> DocumentExtraction:
    """
    Extracts financial structured data using Google Gemini API.
    """
    model_name = settings.GEMINI_MODEL or "gemini-3.6-flash"

    # Safe diagnostic logging - NEVER log actual key value
    logger.info(f"GEMINI_API_KEY configured: {settings.is_gemini_api_key_configured}")
    logger.info(f"Using Gemini Model: {model_name}")

    api_key = settings.GEMINI_API_KEY
    if not api_key or not settings.is_gemini_api_key_configured:
        err_msg = (
            "GEMINI_API_KEY is not configured or contains a placeholder. "
            "Please set a valid Google Gemini API key in backend/.env or .env file."
        )
        logger.error(err_msg)
        raise ValueError(err_msg)

    prompt_text = EXTRACTION_SYSTEM_PROMPT.format(document_type=document_type)

    # Add native text content to prompt if present
    text_content_snippet = ""
    for p in raw_text_pages:
        text_content_snippet += f"\n--- Page {p.page_number} Native Text ---\n{p.text}\n"

    if text_content_snippet.strip():
        prompt_text += f"\n\nNATIVE TEXT IN DOCUMENT:\n{text_content_snippet}"

    # Import google-genai SDK
    from google import genai
    from google.genai import types
    
    client = genai.Client(api_key=api_key)
    
    # Build contents array with images and prompt text
    contents = []
    
    # Add page images for multimodal extraction
    for idx, img_bytes in enumerate(page_images):
        part = types.Part.from_bytes(
            data=img_bytes,
            mime_type="image/png"
        )
        contents.append(part)

    contents.append(prompt_text)

    # Smart retry parameters for transient rate-limit (429) or 503 errors
    max_retries = 4
    default_delays = [3.0, 6.0, 12.0, 20.0]

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"Sending extraction request to '{model_name}' for {document_type} (attempt {attempt}/{max_retries})...")

            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
                )
            )
            
            raw_response_text = response.text
            logger.info(f"Received successful response from Gemini ({model_name}).")
            
            # Parse JSON
            parsed_json = json.loads(raw_response_text)
            
            # Post-process & normalize numeric values safely
            extraction = normalize_extraction_json(parsed_json, document_type, raw_text_pages)
            return extraction

        except Exception as e:
            err_str = str(e)
            
            # Handle non-retriable auth or model errors immediately
            if "API_KEY_INVALID" in err_str or "API key not valid" in err_str:
                auth_err = (
                    "Gemini API key authentication failed (400 INVALID_ARGUMENT / API_KEY_INVALID). "
                    "The current GEMINI_API_KEY in backend/.env or .env is invalid or expired. "
                    "Please replace it with a valid Google Gemini API key."
                )
                logger.error(auth_err)
                raise RuntimeError(auth_err) from e

            if "404" in err_str or "NOT_FOUND" in err_str or "no longer available" in err_str:
                model_err = (
                    f"Gemini model '{model_name}' is not found or unavailable (404 NOT_FOUND). "
                    "Please verify GEMINI_MODEL in backend/.env (recommended: gemini-3.6-flash)."
                )
                logger.error(model_err)
                raise RuntimeError(model_err) from e

            # Handle transient retriable errors (503 / 429)
            if ("503" in err_str or "UNAVAILABLE" in err_str or "429" in err_str or "RESOURCE_EXHAUSTED" in err_str) and attempt < max_retries:
                # Check if error specifies retry delay in seconds
                match = re.search(r'retry in (\d+(?:\.\d+)?)s', err_str, re.IGNORECASE)
                if match:
                    wait_sec = min(float(match.group(1)) + 1.0, 30.0)
                else:
                    wait_sec = default_delays[attempt - 1]
                    
                logger.warning(f"Transient rate-limit/503 from Gemini ({err_str[:120]}...). Retrying in {wait_sec:.1f}s (attempt {attempt}/{max_retries})...")
                time.sleep(wait_sec)
                continue

            if "RESOURCE_EXHAUSTED" in err_str or "429" in err_str:
                quota_err = (
                    "Gemini API Free Tier Rate Limit / Quota Exceeded (429 RESOURCE_EXHAUSTED). "
                    "Please wait a few seconds before attempting another document upload."
                )
                logger.error(quota_err)
                raise RuntimeError(quota_err) from e

            logger.error(f"Gemini API Extraction failed on attempt {attempt}: {err_str}")
            raise RuntimeError(f"Gemini extraction failed: {err_str}") from e

    raise RuntimeError(f"Gemini extraction failed after {max_retries} attempts.")

def normalize_extraction_json(
    data: Dict[str, Any],
    document_type: str,
    raw_text_pages: List[RawTextPage]
) -> DocumentExtraction:
    """
    Validates and enriches extraction JSON with normalized numbers.
    """
    fields_raw = data.get("fields", [])
    fields: List[ExtractedField] = []
    
    for f in fields_raw:
        if isinstance(f, dict) and "name" in f:
            val = f.get("value")
            norm_val = f.get("normalized_value")
            if norm_val is None and val is not None:
                norm_val = parse_financial_number(str(val))
            
            fields.append(ExtractedField(
                name=str(f.get("name")).lower().strip(),
                value=val,
                normalized_value=norm_val,
                evidence=f.get("evidence"),
                page_number=f.get("page_number", 1),
                confidence=f.get("confidence", 1.0),
                status="UNREADABLE" if val is None else f.get("status", "EXTRACTED")
            ))

    line_items_raw = data.get("line_items", [])
    line_items: List[LineItem] = []
    for li in line_items_raw:
        if isinstance(li, dict):
            line_items.append(LineItem(
                description=li.get("description"),
                quantity=parse_financial_number(li.get("quantity")),
                unit_price=parse_financial_number(li.get("unit_price")),
                amount=parse_financial_number(li.get("amount")),
                tax=parse_financial_number(li.get("tax")),
                total=parse_financial_number(li.get("total")),
                evidence=li.get("evidence"),
                page_number=li.get("page_number", 1)
            ))

    tables_raw = data.get("tables", [])
    tables: List[FinancialTable] = []
    for t in tables_raw:
        if isinstance(t, dict):
            tables.append(FinancialTable(
                name=t.get("name"),
                headers=t.get("headers", []),
                rows=t.get("rows", []),
                page_number=t.get("page_number", 1),
                evidence=t.get("evidence")
            ))

    periods_raw = data.get("periods", [])
    periods: List[Period] = []
    for p in periods_raw:
        if isinstance(p, dict) and "label" in p:
            p_fields_raw = p.get("fields", [])
            p_fields: List[ExtractedField] = []
            for pf in p_fields_raw:
                if isinstance(pf, dict) and "name" in pf:
                    v = pf.get("value")
                    nv = pf.get("normalized_value")
                    if nv is None and v is not None:
                        nv = parse_financial_number(str(v))
                    p_fields.append(ExtractedField(
                        name=str(pf.get("name")).lower().strip(),
                        value=v,
                        normalized_value=nv,
                        evidence=pf.get("evidence"),
                        page_number=pf.get("page_number", 1),
                        confidence=pf.get("confidence", 1.0),
                        status="UNREADABLE" if v is None else pf.get("status", "EXTRACTED")
                    ))
            periods.append(Period(label=str(p.get("label")), fields=p_fields))

    notes_raw = data.get("notes", [])
    notes: List[Note] = []
    for n in notes_raw:
        if isinstance(n, dict) and "content" in n:
            notes.append(Note(
                title=n.get("title"),
                content=str(n.get("content")),
                page_number=n.get("page_number", 1)
            ))

    return DocumentExtraction(
        document_type=document_type,
        fields=fields,
        line_items=line_items,
        tables=tables,
        periods=periods,
        notes=notes,
        raw_text_by_page=raw_text_pages,
        metadata={"normalized": True}
    )
