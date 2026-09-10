import json
import os
import re
import time
import base64
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
7. For invoices, extract every line item table row into the `line_items` array (description, quantity, unit_price, total). Include financial tables, notes, and raw text evidence wherever present.
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

def extract_with_groq(
    document_type: str,
    raw_text_pages: List[RawTextPage],
    page_images: List[bytes],
    is_scanned: bool = False
) -> DocumentExtraction:
    """
    Extracts financial structured data using Groq SDK and qwen/qwen3.8-27b model.
    """
    model_name = settings.GROQ_MODEL or "qwen/qwen3.8-27b"

    # Safe diagnostic logging - NEVER log actual key value
    logger.info(f"GROQ_API_KEY configured: {settings.is_groq_api_key_configured}")
    logger.info(f"Using Groq Model: {model_name}")

    api_key = settings.GROQ_API_KEY
    if not api_key or not settings.is_groq_api_key_configured:
        err_msg = (
            "GROQ_API_KEY is not configured or contains a placeholder. "
            "Please set a valid Groq API key in backend/.env or .env file."
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

    # Import Groq SDK
    from groq import Groq
    
    client = Groq(api_key=api_key)
    
    # Build multimodal content parts
    content_parts = []
    
    # Add page images as compressed base64 data URLs for multimodal vision extraction
    if is_scanned or not any(p.text.strip() for p in raw_text_pages):
        for img_bytes in page_images:
            try:
                from PIL import Image
                import io
                img = Image.open(io.BytesIO(img_bytes))
                img.thumbnail((1024, 1024))
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=85)
                b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")
                content_parts.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{b64_str}"
                    }
                })
            except Exception as img_err:
                logger.warning(f"Image thumbnail compression failed: {img_err}, using raw bytes")
                b64_str = base64.b64encode(img_bytes).decode("utf-8")
                content_parts.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{b64_str}"
                    }
                })

    content_parts.append({
        "type": "text",
        "text": prompt_text
    })

    messages = [
        {
            "role": "user",
            "content": content_parts
        }
    ]

    # Execute single Groq extraction request
    try:
        logger.info(f"Sending extraction request to Groq '{model_name}' for {document_type}...")
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=950
        )
        raw_response_text = response.choices[0].message.content
        logger.info(f"Received successful response from Groq ({model_name}).")
        parsed_json = json.loads(raw_response_text)
        return normalize_extraction_json(parsed_json, document_type, raw_text_pages)

    except Exception as e:
        err_str = str(e)
        from groq import RateLimitError
        
        # Check for 401 Authentication error
        if "invalid_api_key" in err_str.lower() or "authentication failed" in err_str.lower() or "401" in err_str:
            auth_err = (
                "Groq API key authentication failed (401 / Invalid API Key). "
                "The current GROQ_API_KEY in backend/.env or .env is invalid or expired. "
                "Please replace it with a valid Groq API key."
            )
            logger.error(auth_err)
            raise RuntimeError(auth_err) from e

        # Check for 429 Rate Limit error
        if isinstance(e, RateLimitError) or "429" in err_str or "rate limit" in err_str.lower():
            retry_after_val = None
            if hasattr(e, "response") and e.response is not None:
                retry_after_val = e.response.headers.get("retry-after") or e.response.headers.get("x-ratelimit-reset-tokens")
            
            # If server specifies a short retry-after (<= 2.0 seconds), perform at most one brief retry
            if retry_after_val:
                try:
                    wait_sec = float(str(retry_after_val).replace("s", "").strip())
                    if 0 < wait_sec <= 2.0:
                        logger.warning(f"Server retry-after indicates safe wait of {wait_sec:.1f}s. Performing single retry...")
                        time.sleep(wait_sec)
                        retry_resp = client.chat.completions.create(
                            model=model_name,
                            messages=messages,
                            response_format={"type": "json_object"},
                            temperature=0.1,
                            max_tokens=950
                        )
                        parsed_json = json.loads(retry_resp.choices[0].message.content)
                        return normalize_extraction_json(parsed_json, document_type, raw_text_pages)
                except Exception as retry_err:
                    logger.error(f"Single retry failed: {retry_err}")

            quota_err = f"Groq API Rate Limit Exceeded (429): {err_str}"
            logger.error(quota_err)
            raise RuntimeError(quota_err) from e

        logger.error(f"Groq API Extraction failed: {err_str}")
        raise RuntimeError(f"Groq extraction failed: {err_str}") from e

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
