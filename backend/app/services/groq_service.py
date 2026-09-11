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
4. Extract canonical summary fields as well as ANY arbitrary additional key-value fields visible in headers or footers.

5. STRICT LABEL-AWARE FIELD MAPPING FOR HEADERS & METADATA:
   - Never map a field value based solely on page position. You MUST use the literal textual label in the evidence snippet to determine field semantics.
   - Evidence label 'Sales Man' / 'Salesperson' / 'Sales Rep' MUST be mapped to field name `sales_person` or `sales_man`. NEVER map Sales Man to `buyer_name`.
   - Evidence label 'Market' / 'Market Area' / 'Route' MUST be mapped to field name `market`. NEVER map Market or Area to `buyer_address`.
   - Evidence label 'Buyer' / 'Buyer's Name' / 'Customer' / 'Billed To' MUST be mapped to field name `buyer_name`.
   - Evidence label 'Buyer's Address' / 'Customer Address' / 'Billing Address' MUST be mapped to field name `buyer_address`.
   - Evidence label 'Delivery Note' / 'Order No' / 'Ref No' MUST be mapped to `delivery_note_no`, `order_no`, or `reference_no`.
   - Evidence label 'Mode of Payment' / 'Terms' MUST be mapped to `mode_of_payment` or `payment_terms`.

6. SPECIAL INSTRUCTION FOR BALANCE SHEETS:
   - Extract ALL visible financial rows (Capital, Share Capital, Reserves & Surplus, Minority Interest, Deposits, Borrowings, Total Assets, Current Assets, Non-Current Assets, Total Liabilities, Current Liabilities, Non-Current Liabilities, Investments, Fixed Assets, Loans & Advances, Cash & Cash Equivalents) into the `fields` array and/or `periods` array.
   - DO NOT extract Balance Sheet rows into `line_items`. `line_items` is strictly for itemized invoice product/service rows.
   - For multi-period balance sheets (e.g. 2026 vs 2025), group each period's values under the `periods` array with `label` set to the period/year (e.g. '2026' or '2025').
   - Include exact row labels in `evidence`.
   - Missing values MUST remain null.

7. SPECIAL INSTRUCTION FOR INVOICE TABLE ROWS (LINE ITEMS):
   - You MUST extract EVERY itemized product/service table row into the `line_items` array for INVOICE documents.
   - DO NOT return an empty `line_items` array if table rows are visible in an invoice.
   - Interpret table columns flexibly (S.No, particulars, item description, product, goods, qty, rate, unit price, discount, taxable value, GST, tax, amount, line total).
   - For each line item row, extract:
     * `description`: Item description, product name, or particulars.
     * `quantity`: Quantity, count, or pcs (as a float or null if absent).
     * `unit_price`: Unit price, rate, or price (as a float or null if absent).
     * `discount`: Discount amount or percentage if visible (as a float or null if absent).
     * `tax`: Row-level tax/GST amount if present (or null if absent).
     * `taxable_amount`: Taxable value or line amount before tax (as a float or null if absent).
     * `amount`: Line amount or taxable value (as a float or null if absent).
     * `total`: Row total or line total (as a float or null if absent).
     * `evidence`: Exact text snippet from the table row.
     * `page_number`: Page number (1-indexed).

8. CANONICAL SUMMARY FIELDS TO ALWAYS INCLUDE IN THE `fields` ARRAY IF VISIBLE:
   - Invoices: `subtotal`, `tax`, `total` (or `total_amount`), `amount_paid`, `amount_due`.
   - Balance Sheets: `total_assets` (or `assets`), `total_liabilities` (or `liabilities`), `capital` (or `equity`), `total_capital_and_liabilities`, `current_assets`, `non_current_assets`, `current_liabilities`, `non_current_liabilities`, `deposits`, `borrowings`, `reserves_and_surplus`.
   - Profit & Loss: `primary_income` (or `revenue`, `interest_earned`), `other_income`, `total_income`, `operating_expenses`, `interest_expended`, `provisions`, `total_expenditure`, `profit_before_tax`, `tax`, `net_profit`.
   - Cash Flow: `operating_cash_flow` (or `net_cash_from_operating_activities`), `investing_cash_flow` (or `net_cash_from_investing_activities`), `financing_cash_flow` (or `net_cash_from_financing_activities`), `net_change_in_cash` (or `net_increase`), `opening_cash`, `closing_cash`.

9. For financial numbers:
   - Extract raw text in `value` (e.g. "$10,000.00", "(5,000)").
   - Interpret parentheses like `(5,000)` as negative numbers `-5000`.
   - Do NOT convert non-monetary strings (dates, IDs, invoice numbers, phone numbers, sales person, market area) into numeric values.

10. For multi-period financial statements (e.g., 2023 vs 2024):
   - Group fields under their respective period label in the `periods` array.

11. Do NOT attempt to perform arithmetic or determine whether math is correct. Just extract reported values.

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
      "discount": number or null,
      "tax": number or null,
      "taxable_amount": number or null,
      "amount": number or null,
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

    # Execute single Groq extraction request with safe token budget (<= 1000)
    try:
        logger.info(f"Sending extraction request to Groq '{model_name}' for {document_type} (max_tokens=950)...")
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

        # Check for 429 Rate Limit error / output token limit exceeded
        if isinstance(e, RateLimitError) or "429" in err_str or "rate limit" in err_str.lower() or "reduce max_tokens" in err_str.lower() or "limit 1000" in err_str.lower():
            logger.warning(f"Groq API 429 / Rate Limit error encountered: {err_str}. Retrying once with max_tokens=700...")
            
            retry_after_val = None
            if hasattr(e, "response") and e.response is not None:
                retry_after_val = e.response.headers.get("retry-after") or e.response.headers.get("x-ratelimit-reset-tokens")
            
            if retry_after_val:
                try:
                    wait_sec = float(str(retry_after_val).replace("s", "").strip())
                    if 0 < wait_sec <= 2.0:
                        logger.info(f"Waiting {wait_sec:.1f}s before 429 retry...")
                        time.sleep(wait_sec)
                except Exception:
                    pass

            # Perform single retry with max_tokens=700
            try:
                retry_resp = client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.1,
                    max_tokens=700
                )
                raw_response_text = retry_resp.choices[0].message.content
                logger.info(f"Received successful response from Groq on 429 retry ({model_name}).")
                parsed_json = json.loads(raw_response_text)
                return normalize_extraction_json(parsed_json, document_type, raw_text_pages)
            except Exception as retry_err:
                logger.error(f"Single 429 retry failed: {retry_err}")
                quota_err = f"Groq API Rate Limit Exceeded (429): {retry_err}"
                raise RuntimeError(quota_err) from retry_err

        logger.error(f"Groq API Extraction failed: {err_str}")
        raise RuntimeError(f"Groq extraction failed: {err_str}") from e


# ──────────────────────────────────────────────────────────────────────────────
# FALLBACK EXTRACTION: Targeted Groq Vision call for dense/scanned documents
# ──────────────────────────────────────────────────────────────────────────────

FALLBACK_PROMPTS = {
    "invoice": """You are extracting ONLY the itemized product/service table rows from the provided invoice image(s) across all pages.
Do NOT repeat header metadata (seller, buyer, date, invoice number, address, phone, market, salesperson).
Extract EVERY visible table row across all pages. For each row return:
- description (item name / particulars)
- quantity (float or null)
- unit_price (float or null)
- discount (float or null)
- tax (float or null)
- taxable_amount (float or null)
- amount (float or null)
- total (float or null)
- evidence (exact row text)
- page_number (1-indexed)
Also extract summary totals if visible: subtotal, tax, total, amount_paid, amount_due.
Preserve nulls for genuinely missing values. Do NOT hallucinate.
Return JSON: {{"fields": [...], "line_items": [...]}}""",

    "balance_sheet": """You are extracting ONLY the financial statement rows from the provided Balance Sheet image(s) across all pages.
Do NOT repeat document title, company name, report date, currency unit, or page number.
Extract EVERY visible financial row across all pages with its label and ALL period column values.
Common rows: Capital, Share Capital, Reserves & Surplus, Minority Interest, Deposits, Borrowings,
Other Liabilities, Current Assets, Non-Current Assets, Investments, Fixed Assets, Advances,
Cash & Balances, Other Assets, Total Assets, Total Capital & Liabilities, Total Liabilities.
For each row: name, value (primary period), evidence (exact row text with all numbers), page_number.
For multi-period tables, include a periods array with label (year) and fields.
Preserve negative values and parentheses notation. Preserve nulls. Do NOT hallucinate.
Return JSON: {{"fields": [...], "periods": [...]}}""",

    "profit_loss": """You are extracting ONLY the financial statement rows from the provided Profit & Loss Statement image(s) across all pages.
Do NOT repeat document title, company name, report date, currency unit, or page number.
Extract EVERY visible financial row across all pages with its label and ALL period column values.
Common rows: Interest Earned / Revenue, Other Income, Total Income, Interest Expended / Finance Costs,
Operating Expenses, Employee Benefits, Provisions & Contingencies, Depreciation, Total Expenditure,
Profit Before Tax, Tax Expense, Net Profit.
For each row: name, value (primary period), evidence (exact row text with all numbers), page_number.
For multi-period tables, include a periods array with label (year) and fields.
Preserve negative values and parentheses notation. Preserve nulls. Do NOT hallucinate.
Return JSON: {{"fields": [...], "periods": [...]}}""",

    "cash_flow": """You are extracting ONLY the financial statement rows from the provided Cash Flow Statement image(s) across all pages.
Do NOT repeat document title, company name, report date, currency unit, or page number.
Extract EVERY visible financial row across all pages with its label and ALL period column values.
Common rows: Net Cash from Operating Activities, Net Cash from Investing Activities,
Net Cash from Financing Activities, Net Increase in Cash, Opening Cash, Closing Cash,
Profit Before Tax, Adjustments, Changes in Working Capital.
For each row: name, value (primary period), evidence (exact row text with all numbers), page_number.
For multi-period tables, include a periods array with label (year) and fields.
Preserve negative values and parentheses notation e.g. (5,000) = -5000. Preserve nulls. Do NOT hallucinate.
Return JSON: {{"fields": [...], "periods": [...]}}"""
}

# Canonical field sets used to detect extraction completeness per doc type
_INVOICE_FINANCIAL_FIELDS = {"subtotal", "tax", "total", "amount_paid", "amount_due", "total_amount", "grand_total"}
_BS_CANONICAL_FIELDS = {"total_assets", "assets", "total_liabilities", "liabilities", "capital", "equity",
                        "total_capital_and_liabilities", "current_assets", "non_current_assets",
                        "deposits", "borrowings", "reserves_and_surplus"}
_PNL_CANONICAL_FIELDS = {"total_income", "total_expenditure", "net_profit", "primary_income",
                         "other_income", "operating_expenses", "interest_expended", "provisions",
                         "profit_before_tax", "tax"}
_CF_CANONICAL_FIELDS = {"operating_cash_flow", "investing_cash_flow", "financing_cash_flow",
                        "net_change_in_cash", "opening_cash", "closing_cash"}


def should_trigger_fallback(extraction: DocumentExtraction, doc_type: str) -> bool:
    """
    Determines whether a targeted fallback extraction is warranted based on
    extraction completeness — never based on filename, year, or company.
    """
    doc_type_clean = doc_type.lower().strip()

    if doc_type_clean == "invoice":
        # Fallback if no line items were extracted
        return len(extraction.line_items) == 0

    # For statement types, count how many fields have a non-null normalized_value
    numeric_fields = [f for f in extraction.fields if f.normalized_value is not None]
    field_names = {f.name for f in extraction.fields if f.normalized_value is not None}

    if doc_type_clean in ("balance_sheet", "balancesheet"):
        has_canonical = bool(field_names & _BS_CANONICAL_FIELDS)
        return len(numeric_fields) < 2 or not has_canonical

    if doc_type_clean in ("profit_loss", "profit_and_loss", "pnl"):
        has_canonical = bool(field_names & _PNL_CANONICAL_FIELDS)
        return len(numeric_fields) < 2 or not has_canonical

    if doc_type_clean in ("cash_flow", "cashflow"):
        has_canonical = bool(field_names & _CF_CANONICAL_FIELDS)
        return len(numeric_fields) < 2 or not has_canonical

    return False


def perform_fallback_extraction(
    document_type: str,
    raw_text_pages: List[RawTextPage],
    page_images: List[bytes],
    is_scanned: bool = False
) -> DocumentExtraction:
    """
    Performs ONE targeted Groq Vision extraction focused exclusively on financial
    rows/line items. Uses max_tokens=900 and a document-type-specific prompt
    that omits metadata to maximise financial content in the output budget.
    """
    model_name = settings.GROQ_MODEL or "qwen/qwen3.8-27b"
    api_key = settings.GROQ_API_KEY
    doc_type_clean = document_type.lower().strip()

    fallback_prompt = FALLBACK_PROMPTS.get(doc_type_clean, FALLBACK_PROMPTS.get("invoice", ""))

    # Add native text if present
    text_snippet = ""
    for p in raw_text_pages:
        text_snippet += f"\n--- Page {p.page_number} Native Text ---\n{p.text}\n"
    if text_snippet.strip():
        fallback_prompt += f"\n\nNATIVE TEXT IN DOCUMENT:\n{text_snippet}"

    from groq import Groq
    client = Groq(api_key=api_key)

    content_parts = []
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
                    "image_url": {"url": f"data:image/jpeg;base64,{b64_str}"}
                })
            except Exception:
                b64_str = base64.b64encode(img_bytes).decode("utf-8")
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64_str}"}
                })

    content_parts.append({"type": "text", "text": fallback_prompt})

    messages = [{"role": "user", "content": content_parts}]

    try:
        logger.info(f"Sending FALLBACK extraction request to Groq '{model_name}' for {document_type} (max_tokens=900)...")
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=900
        )
        raw_text = response.choices[0].message.content
        logger.info(f"Received successful FALLBACK response from Groq ({model_name}).")
        parsed_json = json.loads(raw_text)
        return normalize_extraction_json(parsed_json, document_type, raw_text_pages)
    except Exception as e:
        err_str = str(e)
        from groq import RateLimitError

        if isinstance(e, RateLimitError) or "429" in err_str or "rate limit" in err_str.lower():
            logger.warning(f"Fallback 429 error: {err_str}. Retrying with max_tokens=700...")
            retry_after_val = None
            if hasattr(e, "response") and e.response is not None:
                retry_after_val = e.response.headers.get("retry-after") or e.response.headers.get("x-ratelimit-reset-tokens")
            if retry_after_val:
                try:
                    wait_sec = float(str(retry_after_val).replace("s", "").strip())
                    if 0 < wait_sec <= 2.0:
                        time.sleep(wait_sec)
                except Exception:
                    pass
            try:
                retry_resp = client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.1,
                    max_tokens=700
                )
                raw_text = retry_resp.choices[0].message.content
                logger.info(f"Received successful FALLBACK response on retry ({model_name}).")
                parsed_json = json.loads(raw_text)
                return normalize_extraction_json(parsed_json, document_type, raw_text_pages)
            except Exception as retry_err:
                logger.error(f"Fallback retry failed: {retry_err}")
                raise RuntimeError(f"Fallback extraction failed: {retry_err}") from retry_err

        logger.error(f"Fallback extraction failed: {err_str}")
        raise RuntimeError(f"Fallback extraction failed: {err_str}") from e


def merge_extractions(primary: DocumentExtraction, fallback: DocumentExtraction) -> DocumentExtraction:
    """
    Safely merges a fallback extraction into a primary extraction:
    - Never overwrites a non-null primary value with null.
    - Deduplicates fields and line items.
    - Preserves evidence and page numbers.
    """
    # 1. Merge fields: keep primary values, add new fallback fields
    primary_field_map = {f.name: f for f in primary.fields}
    for fb_field in fallback.fields:
        if fb_field.name in primary_field_map:
            existing = primary_field_map[fb_field.name]
            # Only overwrite if primary has null value and fallback has a real value
            if existing.normalized_value is None and fb_field.normalized_value is not None:
                primary_field_map[fb_field.name] = fb_field
        else:
            if fb_field.value is not None or fb_field.normalized_value is not None:
                primary_field_map[fb_field.name] = fb_field

    merged_fields = list(primary_field_map.values())

    # 2. Merge line items: deduplicate by description
    merged_line_items = list(primary.line_items)
    existing_descs = {(li.description or "").lower().strip() for li in merged_line_items}
    for fb_li in fallback.line_items:
        fb_desc = (fb_li.description or "").lower().strip()
        if fb_desc and fb_desc not in existing_descs:
            merged_line_items.append(fb_li)
            existing_descs.add(fb_desc)
        elif not fb_desc:
            # Check if this is a truly new item by amount
            if fb_li.total is not None and not any(
                li.total == fb_li.total and (li.description or "").lower().strip() == fb_desc
                for li in merged_line_items
            ):
                merged_line_items.append(fb_li)

    # 3. Merge periods: combine period field maps
    primary_period_map = {p.label: p for p in primary.periods}
    for fb_period in fallback.periods:
        if fb_period.label in primary_period_map:
            existing_p = primary_period_map[fb_period.label]
            existing_p_field_names = {f.name for f in existing_p.fields}
            for fb_pf in fb_period.fields:
                if fb_pf.name not in existing_p_field_names:
                    existing_p.fields.append(fb_pf)
                else:
                    # Overwrite only if existing value is null and fallback has value
                    for i, ef in enumerate(existing_p.fields):
                        if ef.name == fb_pf.name and ef.normalized_value is None and fb_pf.normalized_value is not None:
                            existing_p.fields[i] = fb_pf
                            break
        else:
            primary_period_map[fb_period.label] = fb_period

    merged_periods = list(primary_period_map.values())

    # 4. Merge tables: append new tables
    merged_tables = list(primary.tables) + [
        t for t in fallback.tables
        if t.name not in {et.name for et in primary.tables}
    ]

    return DocumentExtraction(
        document_type=primary.document_type,
        fields=merged_fields,
        line_items=merged_line_items,
        tables=merged_tables,
        periods=merged_periods,
        notes=primary.notes,
        raw_text_by_page=primary.raw_text_by_page,
        metadata={**(primary.metadata or {}), "fallback_applied": True}
    )



def _get_dict_alias(d: dict, aliases: List[str]) -> Any:
    if not isinstance(d, dict):
        return None
    for a in aliases:
        if a in d and d[a] is not None:
            return d[a]
        for k, v in d.items():
            if str(k).lower().strip() == a and v is not None:
                return v
    return None

def normalize_extraction_json(
    data: Dict[str, Any],
    document_type: str,
    raw_text_pages: List[RawTextPage]
) -> DocumentExtraction:
    """
    Validates and enriches extraction JSON with field-aware normalized numbers,
    document-type scoped line item recovery, Balance Sheet label-aware normalization,
    generic table conversion, and canonical summary field auto-promotion.
    """
    doc_type_clean = (document_type or data.get("document_type") or "invoice").lower().strip()
    
    fields_raw = data.get("fields", [])
    initial_fields: List[ExtractedField] = []
    
    for f in fields_raw:
        if isinstance(f, dict) and "name" in f:
            name_str = str(f.get("name")).lower().strip()
            val = f.get("value")
            norm_val = f.get("normalized_value")
            if norm_val is None and val is not None:
                norm_val = parse_financial_number(str(val), field_name=name_str)
            
            ext_field = ExtractedField(
                name=name_str,
                value=val,
                normalized_value=norm_val,
                evidence=f.get("evidence"),
                page_number=f.get("page_number", 1),
                confidence=f.get("confidence", 1.0),
                status="UNREADABLE" if val is None else f.get("status", "EXTRACTED")
            )
            initial_fields.append(ext_field)

    # General Financial Statement Row & Table Recovery:
    # If Groq extracted financial statement rows into line_items or tables, convert them into ExtractedField entries
    if doc_type_clean in ("balance_sheet", "balancesheet", "profit_loss", "profit_and_loss", "pnl", "cash_flow", "cashflow"):
        raw_items_bs = data.get("line_items") or data.get("items") or data.get("rows") or []
        for item in raw_items_bs:
            if isinstance(item, dict):
                label_val = _get_dict_alias(item, ["description", "label", "item", "name", "particulars"])
                amount_val = _get_dict_alias(item, ["amount", "value", "total", "val"])
                if label_val is not None:
                    norm_v = parse_financial_number(amount_val)
                    initial_fields.append(ExtractedField(
                        name=str(label_val).lower().strip(),
                        value=str(amount_val) if amount_val is not None else None,
                        normalized_value=norm_v,
                        evidence=item.get("evidence") or f"{label_val}: {amount_val}",
                        page_number=item.get("page_number", 1),
                        status="EXTRACTED"
                    ))

        # Also check tables array for financial statement rows
        tables_raw_bs = data.get("tables") or data.get("table") or []
        for t in tables_raw_bs:
            if isinstance(t, dict) and t.get("rows"):
                rows = t.get("rows", [])
                headers_str = " ".join(t.get("headers", []))
                for r in rows:
                    if isinstance(r, list) and len(r) > 0:
                        label_cell = str(r[0]).strip()
                        if label_cell:
                            row_cells = [str(c).strip() for c in r[1:] if c is not None and str(c).strip() != ""]
                            # Prefer formatted decimal amounts (e.g. -1,539.34 or (1,539.34)), falling back to parseable numeric strings
                            decimal_amounts = [c for c in row_cells if re.search(r'-?[\d,]+\.\d{2}|\([\d,]+\.\d{2}\)', c)]
                            all_amounts = [c for c in row_cells if parse_financial_number(c) is not None]
                            prim_val = decimal_amounts[0] if decimal_amounts else (all_amounts[0] if all_amounts else (row_cells[0] if row_cells else None))
                            ev_text = f"{label_cell} {' '.join(row_cells)} {headers_str}"
                            norm_v = parse_financial_number(prim_val) if prim_val else None
                            initial_fields.append(ExtractedField(
                                name=label_cell.lower().strip(),
                                value=prim_val,
                                normalized_value=norm_v,
                                evidence=ev_text.strip(),
                                page_number=t.get("page_number", 1),
                                status="EXTRACTED"
                            ))

    # Label-Aware Semantic Disambiguation & Canonical Field Mapping Pass:
    fields: List[ExtractedField] = []
    field_map_dict: Dict[str, ExtractedField] = {}

    if doc_type_clean == "invoice":
        sales_person_keywords = ["sales man", "salesman", "sales person", "salesperson", "sales executive", "sales rep"]
        market_keywords = ["market area", "market", "area lohappool", "route", "market:"]
        buyer_name_keywords = ["buyer's name", "buyer name", "customer name", "billed to", "party name"]
        buyer_address_keywords = ["buyer's address", "buyer address", "customer address", "billing address"]

        for f in initial_fields:
            ev_lower = (f.evidence or "").lower().strip()
            val_lower = str(f.value or "").lower().strip()
            combined_text = f"{ev_lower} {val_lower}"
            target_name = f.name

            if target_name in ("buyer_name", "buyer_address") and any(kw in combined_text for kw in sales_person_keywords):
                target_name = "sales_person"
            elif target_name in ("buyer_name", "buyer_address") and any(kw in combined_text for kw in market_keywords):
                target_name = "market"
            elif any(kw in ev_lower for kw in buyer_name_keywords) and target_name not in ("buyer_name", "buyer_address"):
                target_name = "buyer_name"
            elif any(kw in ev_lower for kw in buyer_address_keywords) and target_name not in ("buyer_name", "buyer_address"):
                target_name = "buyer_address"

            norm_val = f.normalized_value
            if norm_val is not None:
                norm_val = parse_financial_number(str(f.value), field_name=target_name)

            final_field = ExtractedField(
                name=target_name,
                value=f.value,
                normalized_value=norm_val,
                evidence=f.evidence,
                page_number=f.page_number,
                confidence=f.confidence,
                status=f.status
            )
            fields.append(final_field)
            field_map_dict[target_name] = final_field

    elif doc_type_clean in ("balance_sheet", "balancesheet"):
        bs_alias_rules = [
            ("total_assets", ["total assets", "assets total", "grand total assets"]),
            ("total_capital_and_liabilities", ["total capital and liabilities", "total capital & liabilities", "total equity and liabilities", "total liabilities and equity", "capital and liabilities"]),
            ("total_liabilities", ["total liabilities", "liabilities total"]),
            ("non_current_assets", ["non-current assets", "non current assets", "total non-current assets", "long term assets", "fixed assets"]),
            ("current_assets", ["current assets", "total current assets", "short term assets"]),
            ("other_assets", ["other assets", "other_assets"]),
            ("other_liabilities", ["other liabilities", "other liabilities and provisions", "other_liabilities"]),
            ("contingent_liabilities", ["contingent liabilities", "contingent_liabilities"]),
            ("non_current_liabilities", ["non-current liabilities", "non current liabilities", "total non-current liabilities", "long term liabilities"]),
            ("current_liabilities", ["current liabilities", "total current liabilities", "short term liabilities"]),
            ("capital", ["capital", "share capital", "equity", "shareholders' equity", "shareholder equity", "total equity", "equity capital", "capital account", "owners equity", "owner's equity", "paid up capital", "capital / shareholder equity"]),
            ("reserves_and_surplus", ["reserves and surplus", "reserves & surplus", "retained earnings", "reserves", "surplus", "other equity"]),
            ("minority_interest", ["minority interest", "non-controlling interest", "non controlling interest"]),
            ("deposits", ["deposits", "customer deposits", "term deposits", "fixed deposits"]),
            ("borrowings", ["borrowings", "short term borrowings", "long term borrowings", "loans", "debt", "total borrowings"]),
            ("liabilities", ["liabilities", "total liabilities"]),
            ("assets", ["assets", "total assets"])
        ]

        asset_keywords = ["cash and balances", "balances with bank", "investments", "advances", "fixed assets", "other assets"]
        cap_liab_keywords = ["capital", "equity", "reserves", "surplus", "deposits", "borrowings", "policyholders", "other liabilities", "contingent liabilities"]

        total_rows_count = sum(
            1 for f in initial_fields 
            if f.name.lower().strip() in ("total", "total amount", "grand total", "total (rs.)", "total (inr)") or
               (f.evidence or "").lower().strip().startswith("total ") or
               (f.evidence or "").lower().strip() == "total"
        )
        
        has_section_context = any(
            any(kw in f.name.lower() or kw in (f.evidence or "").lower() for kw in cap_liab_keywords + asset_keywords)
            for f in initial_fields
        )

        current_section = "CAPITAL_AND_LIABILITIES"
        seen_first_total = False
        period_field_maps: Dict[str, Dict[str, ExtractedField]] = {}

        for f in initial_fields:
            ev_lower = (f.evidence or "").lower().strip()
            name_lower = f.name.lower().strip()
            combined_text = f"{name_lower} {ev_lower}"

            if not seen_first_total:
                if any(kw in combined_text for kw in asset_keywords) and not any(kw in combined_text for kw in cap_liab_keywords):
                    current_section = "ASSETS"

            target_name = name_lower
            is_standalone_total = (
                (name_lower in ("total", "total amount", "grand total", "total (rs.)", "total (inr)") or
                 ev_lower.startswith("total ") or ev_lower == "total") and
                not any(kw in name_lower or kw in ev_lower for kw in ("assets", "liabilities", "equity", "capital"))
            )

            if is_standalone_total:
                if has_section_context and total_rows_count >= 2:
                    if current_section == "CAPITAL_AND_LIABILITIES" and not seen_first_total:
                        target_name = "total_capital_and_liabilities"
                        seen_first_total = True
                        current_section = "ASSETS"
                    elif current_section == "ASSETS" or seen_first_total:
                        target_name = "total_assets"
                elif has_section_context and total_rows_count == 1:
                    if current_section == "ASSETS":
                        target_name = "total_assets"
                    elif current_section == "CAPITAL_AND_LIABILITIES":
                        target_name = "total_capital_and_liabilities"
            else:
                for canonical_k, aliases in bs_alias_rules:
                    matched = False
                    for a in aliases:
                        if canonical_k in ("assets", "liabilities") and a in ("assets", "liabilities"):
                            if name_lower == a or ev_lower == a:
                                matched = True
                                break
                        else:
                            if a == name_lower or a == ev_lower or f" {a} " in f" {ev_lower} " or ev_lower.startswith(a):
                                matched = True
                                break
                    if matched:
                        target_name = canonical_k
                        break

            norm_val = f.normalized_value
            if norm_val is None and f.value is not None:
                norm_val = parse_financial_number(str(f.value), field_name=target_name)

            final_field = ExtractedField(
                name=target_name,
                value=f.value,
                normalized_value=norm_val,
                evidence=f.evidence,
                page_number=f.page_number,
                confidence=f.confidence,
                status=f.status
            )
            fields.append(final_field)
            field_map_dict[target_name] = final_field

            # Extract multi-period numbers from evidence snippet if present
            numbers_in_ev = re.findall(r'-?[\d,]+\.\d{2}|\([\d,]+\.\d{2}\)', f.evidence or "")
            if len(numbers_in_ev) >= 2:
                v1 = parse_financial_number(numbers_in_ev[0], field_name=target_name)
                v2 = parse_financial_number(numbers_in_ev[1], field_name=target_name)
                y_matches = re.findall(r'20\d\d', f.evidence or "")
                p1_k = y_matches[0] if len(y_matches) >= 1 else "Period 1"
                p2_k = y_matches[1] if len(y_matches) >= 2 else ("Period 2" if p1_k == "Period 1" else "Previous Period")

                if p1_k not in period_field_maps:
                    period_field_maps[p1_k] = {}
                if p2_k not in period_field_maps:
                    period_field_maps[p2_k] = {}

                period_field_maps[p1_k][target_name] = ExtractedField(
                    name=target_name, value=numbers_in_ev[0], normalized_value=v1, evidence=f"{target_name} {p1_k}: {numbers_in_ev[0]}", page_number=f.page_number, status="EXTRACTED"
                )
                period_field_maps[p2_k][target_name] = ExtractedField(
                    name=target_name, value=numbers_in_ev[1], normalized_value=v2, evidence=f"{target_name} {p2_k}: {numbers_in_ev[1]}", page_number=f.page_number, status="EXTRACTED"
                )

    elif doc_type_clean in ("profit_loss", "profit_and_loss", "pnl"):
        pnl_alias_rules = [
            ("total_income", ["total income", "total revenue", "income total", "total (i+ii)", "grand total income", "total income (i + ii)", "total income (i+ii)"]),
            ("primary_income", ["primary income", "interest earned", "revenue from operations", "revenue", "operating revenue", "income from operations", "interest income"]),
            ("other_income", ["other income", "non-operating income", "other operating income"]),
            ("total_expenditure", ["total expenditure", "total expenses", "expenditure total", "total expenditure/expenses"]),
            ("operating_expenses", ["operating expenses", "operating expense", "other expenses", "employee benefits expense"]),
            ("interest_expended", ["interest expended", "finance costs", "interest expense", "interest paid"]),
            ("provisions", ["provisions and contingencies", "provisions & contingencies", "provisions", "depreciation and amortization"]),
            ("profit_before_tax", ["profit before tax", "profit / (loss) before tax", "pbt"]),
            ("tax", ["tax expense", "tax", "current tax", "deferred tax", "provision for tax"]),
            ("net_profit", ["net profit", "net profit for the year", "profit for the period", "profit after tax", "pat", "net profit / (loss)", "net profit for the period"])
        ]

        period_field_maps: Dict[str, Dict[str, ExtractedField]] = {}

        for f in initial_fields:
            ev_lower = (f.evidence or "").lower().strip()
            name_lower = f.name.lower().strip()
            target_name = name_lower

            for canonical_k, aliases in pnl_alias_rules:
                if any(a == name_lower or a == ev_lower or f" {a} " in f" {ev_lower} " or ev_lower.startswith(a) for a in aliases):
                    target_name = canonical_k
                    break

            norm_val = f.normalized_value
            if norm_val is None and f.value is not None:
                norm_val = parse_financial_number(str(f.value), field_name=target_name)

            final_field = ExtractedField(
                name=target_name,
                value=f.value,
                normalized_value=norm_val,
                evidence=f.evidence,
                page_number=f.page_number,
                confidence=f.confidence,
                status=f.status
            )
            fields.append(final_field)
            field_map_dict[target_name] = final_field

            # Extract multi-period numbers from evidence snippet if present
            numbers_in_ev = re.findall(r'-?[\d,]+\.\d{2}|\([\d,]+\.\d{2}\)', f.evidence or "")
            if len(numbers_in_ev) >= 2:
                v1 = parse_financial_number(numbers_in_ev[0], field_name=target_name)
                v2 = parse_financial_number(numbers_in_ev[1], field_name=target_name)
                y_matches = re.findall(r'20\d\d', f.evidence or "")
                p1_k = y_matches[0] if len(y_matches) >= 1 else "Period 1"
                p2_k = y_matches[1] if len(y_matches) >= 2 else ("Period 2" if p1_k == "Period 1" else "Previous Period")

                if p1_k not in period_field_maps:
                    period_field_maps[p1_k] = {}
                if p2_k not in period_field_maps:
                    period_field_maps[p2_k] = {}

                period_field_maps[p1_k][target_name] = ExtractedField(
                    name=target_name, value=numbers_in_ev[0], normalized_value=v1, evidence=f"{target_name} {p1_k}: {numbers_in_ev[0]}", page_number=f.page_number, status="EXTRACTED"
                )
                period_field_maps[p2_k][target_name] = ExtractedField(
                    name=target_name, value=numbers_in_ev[1], normalized_value=v2, evidence=f"{target_name} {p2_k}: {numbers_in_ev[1]}", page_number=f.page_number, status="EXTRACTED"
                )

    elif doc_type_clean in ("cash_flow", "cashflow"):
        cf_alias_rules = [
            ("operating_cash_flow", ["net cash flow from operating activities", "net cash from operating activities", "operating cash flow", "cash flow from operating activities", "net cash generated from operating activities", "cash from operating activities"]),
            ("investing_cash_flow", ["net cash flow from investing activities", "net cash from investing activities", "investing cash flow", "cash flow from investing activities", "net cash used in investing activities", "cash from investing activities"]),
            ("financing_cash_flow", ["net cash flow from financing activities", "net cash from financing activities", "financing cash flow", "cash flow from financing activities", "net cash used in financing activities", "cash from financing activities"]),
            ("net_change_in_cash", ["net increase in cash and cash equivalents", "net change in cash and cash equivalents", "net increase/(decrease) in cash", "net change in cash", "net cash flow"]),
            ("opening_cash", ["cash and cash equivalents at beginning of year", "opening cash and cash equivalents", "cash at beginning of year", "opening cash"]),
            ("closing_cash", ["cash and cash equivalents at end of year", "closing cash and cash equivalents", "cash at end of year", "closing cash"])
        ]

        period_field_maps: Dict[str, Dict[str, ExtractedField]] = {}

        for f in initial_fields:
            ev_lower = (f.evidence or "").lower().strip()
            name_lower = f.name.lower().strip()
            target_name = name_lower

            for canonical_k, aliases in cf_alias_rules:
                if any(a == name_lower or a == ev_lower or f" {a} " in f" {ev_lower} " or ev_lower.startswith(a) for a in aliases):
                    target_name = canonical_k
                    break

            norm_val = f.normalized_value
            if norm_val is None and f.value is not None:
                norm_val = parse_financial_number(str(f.value), field_name=target_name)

            final_field = ExtractedField(
                name=target_name,
                value=f.value,
                normalized_value=norm_val,
                evidence=f.evidence,
                page_number=f.page_number,
                confidence=f.confidence,
                status=f.status
            )
            fields.append(final_field)
            field_map_dict[target_name] = final_field

            # Multi-period values extraction
            numbers_in_ev = re.findall(r'-?[\d,]+\.\d{2}|\([\d,]+\.\d{2}\)', f.evidence or "")
            if len(numbers_in_ev) >= 2:
                v1 = parse_financial_number(numbers_in_ev[0], field_name=target_name)
                v2 = parse_financial_number(numbers_in_ev[1], field_name=target_name)
                y_matches = re.findall(r'20\d\d', f.evidence or "")
                p1_k = y_matches[0] if len(y_matches) >= 1 else "Period 1"
                p2_k = y_matches[1] if len(y_matches) >= 2 else ("Period 2" if p1_k == "Period 1" else "Previous Period")

                if p1_k not in period_field_maps:
                    period_field_maps[p1_k] = {}
                if p2_k not in period_field_maps:
                    period_field_maps[p2_k] = {}

                period_field_maps[p1_k][target_name] = ExtractedField(
                    name=target_name, value=numbers_in_ev[0], normalized_value=v1, evidence=f"{target_name} {p1_k}: {numbers_in_ev[0]}", page_number=f.page_number, status="EXTRACTED"
                )
                period_field_maps[p2_k][target_name] = ExtractedField(
                    name=target_name, value=numbers_in_ev[1], normalized_value=v2, evidence=f"{target_name} {p2_k}: {numbers_in_ev[1]}", page_number=f.page_number, status="EXTRACTED"
                )

    else:
        for f in initial_fields:
            fields.append(f)
            field_map_dict[f.name] = f

    line_items: List[LineItem] = []

    # Document-Type Scoped Line Item Processing: ONLY run generic line items for INVOICES
    if doc_type_clean == "invoice":
        line_items_raw = (
            data.get("line_items") or
            data.get("items") or
            data.get("invoice_items") or
            data.get("products") or
            data.get("goods") or
            data.get("rows") or
            data.get("table_rows") or
            data.get("particulars") or
            data.get("item_details") or
            data.get("item_list") or
            data.get("lines") or
            []
        )
        
        desc_aliases = ["description", "desc", "item", "item_name", "item_description", "particulars", "product", "product_name", "service", "name", "details", "title", "goods", "article", "specification"]
        qty_aliases = ["quantity", "qty", "count", "pcs", "qnt", "units", "nos", "pkg", "volume", "weight", "no_of_packages"]
        price_aliases = ["unit_price", "unitprice", "rate", "price", "unit_rate", "unit_cost", "cost", "mrp", "rate_per_unit"]
        discount_aliases = ["discount", "disc", "rebate", "discount_amount", "less_discount"]
        tax_aliases = ["tax", "tax_amount", "gst", "cgst", "sgst", "igst", "vat", "gst_amount", "total_tax"]
        taxable_aliases = ["taxable_amount", "taxable_value", "taxable_val", "taxable", "value_before_tax"]
        amount_aliases = ["amount", "line_amount", "row_amount", "val", "value", "taxable_value", "taxable_amount"]
        total_aliases = ["total", "line_total", "grand_total", "total_amount", "net_amount", "row_total", "final_amount"]

        for li in line_items_raw:
            if isinstance(li, dict):
                desc_val = _get_dict_alias(li, desc_aliases)
                qty_val = _get_dict_alias(li, qty_aliases)
                price_val = _get_dict_alias(li, price_aliases)
                disc_val = _get_dict_alias(li, discount_aliases)
                tax_val = _get_dict_alias(li, tax_aliases)
                taxable_val = _get_dict_alias(li, taxable_aliases)
                amt_val = _get_dict_alias(li, amount_aliases)
                tot_val = _get_dict_alias(li, total_aliases)

                qty_norm = parse_financial_number(qty_val, "quantity")
                price_norm = parse_financial_number(price_val, "unit_price")
                disc_norm = parse_financial_number(disc_val, "discount")
                tax_norm = parse_financial_number(tax_val, "tax")
                taxable_norm = parse_financial_number(taxable_val, "taxable_amount")
                amt_norm = parse_financial_number(amt_val, "amount")
                tot_norm = parse_financial_number(tot_val, "total")

                std_keys = set(desc_aliases + qty_aliases + price_aliases + discount_aliases + tax_aliases + taxable_aliases + amount_aliases + total_aliases + ["evidence", "page_number"])
                raw_extra = {k: v for k, v in li.items() if str(k).lower().strip() not in std_keys and v is not None} if isinstance(li, dict) else None

                if desc_val or qty_norm is not None or price_norm is not None or amt_norm is not None or tot_norm is not None or taxable_norm is not None or (raw_extra and len(raw_extra) > 0):
                    line_items.append(LineItem(
                        description=str(desc_val).strip() if desc_val is not None else None,
                        quantity=qty_norm,
                        unit_price=price_norm,
                        discount=disc_norm,
                        tax=tax_norm,
                        taxable_amount=taxable_norm,
                        amount=amt_norm,
                        total=tot_norm or amt_norm or taxable_norm,
                        raw_data=raw_extra if raw_extra else None,
                        evidence=li.get("evidence"),
                        page_number=li.get("page_number", 1)
                    ))

        # Generic Table Fallback for Invoices
        tables_raw = data.get("tables") or data.get("table") or []
        for t in tables_raw:
            if isinstance(t, dict):
                headers = [str(h).lower().strip() for h in t.get("headers", [])]
                rows = t.get("rows", [])
                
                if not line_items and rows:
                    desc_idx = next((i for i, h in enumerate(headers) if any(a in h for a in desc_aliases)), 0 if headers else 0)
                    qty_idx = next((i for i, h in enumerate(headers) if any(a in h for a in qty_aliases)), -1)
                    price_idx = next((i for i, h in enumerate(headers) if any(a in h for a in price_aliases)), -1)
                    disc_idx = next((i for i, h in enumerate(headers) if any(a in h for a in discount_aliases)), -1)
                    taxable_idx = next((i for i, h in enumerate(headers) if any(a in h for a in taxable_aliases)), -1)
                    tax_idx = next((i for i, h in enumerate(headers) if any(a in h for a in tax_aliases)), -1)
                    total_idx = next((i for i, h in enumerate(headers) if any(a in h for a in total_aliases) and i != desc_idx), -1)

                    for row in rows:
                        if isinstance(row, list) and len(row) > 0:
                            d_text = str(row[desc_idx]).strip() if 0 <= desc_idx < len(row) and row[desc_idx] is not None else None
                            q_val = parse_financial_number(row[qty_idx], "quantity") if 0 <= qty_idx < len(row) else None
                            p_val = parse_financial_number(row[price_idx], "unit_price") if 0 <= price_idx < len(row) else None
                            disc_v = parse_financial_number(row[disc_idx], "discount") if 0 <= disc_idx < len(row) else None
                            txbl_v = parse_financial_number(row[taxable_idx], "taxable_amount") if 0 <= taxable_idx < len(row) else None
                            tx_v = parse_financial_number(row[tax_idx], "tax") if 0 <= tax_idx < len(row) else None
                            t_val = parse_financial_number(row[total_idx], "total") if 0 <= total_idx < len(row) else None

                            if d_text is None and len(row) > 0:
                                for cell in row:
                                    if cell is not None and isinstance(cell, str) and re.search(r'[a-zA-Z]{3,}', cell):
                                        d_text = cell.strip()
                                        break

                            row_dict = {"col_" + str(i + 1): str(c) for i, c in enumerate(row) if c is not None}

                            if d_text or q_val is not None or p_val is not None or t_val is not None or txbl_v is not None or len(row_dict) > 0:
                                line_items.append(LineItem(
                                    description=d_text,
                                    quantity=q_val,
                                    unit_price=p_val,
                                    discount=disc_v,
                                    tax=tx_v,
                                    taxable_amount=txbl_v,
                                    amount=t_val or txbl_v,
                                    total=t_val or txbl_v,
                                    raw_data=row_dict if row_dict else None,
                                    evidence=t.get("evidence"),
                                    page_number=t.get("page_number", 1)
                                ))

    # Financial Tables Storage
    tables_raw = data.get("tables") or data.get("table") or []
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

    # Multi-Period Processing
    periods_raw = data.get("periods", [])
    periods: List[Period] = []
    for p in periods_raw:
        if isinstance(p, dict) and "label" in p:
            p_fields_raw = p.get("fields", [])
            p_fields: List[ExtractedField] = []
            for pf in p_fields_raw:
                if isinstance(pf, dict) and "name" in pf:
                    name_str = str(pf.get("name")).lower().strip()
                    v = pf.get("value")
                    nv = pf.get("normalized_value")
                    if nv is None and v is not None:
                        nv = parse_financial_number(str(v), field_name=name_str)
                    
                    # Normalize balance sheet canonical field name inside periods
                    if doc_type_clean == "balance_sheet":
                        for canonical_k, aliases in bs_alias_rules:
                            if any(a == name_str or a in (pf.get("evidence") or "").lower() for a in aliases):
                                name_str = canonical_k
                                break

                    p_fields.append(ExtractedField(
                        name=name_str,
                        value=v,
                        normalized_value=nv,
                        evidence=pf.get("evidence"),
                        page_number=pf.get("page_number", 1),
                        confidence=pf.get("confidence", 1.0),
                        status="UNREADABLE" if v is None else pf.get("status", "EXTRACTED")
                    ))
            periods.append(Period(label=str(p.get("label")), fields=p_fields))

    if doc_type_clean in ("balance_sheet", "balancesheet", "profit_loss", "profit_and_loss", "pnl", "cash_flow", "cashflow") and period_field_maps:
        if not periods:
            for p_label, p_fdict in period_field_maps.items():
                periods.append(Period(label=p_label, fields=list(p_fdict.values())))
        else:
            existing_p_map = {p.label: p for p in periods}
            for p_label, p_fdict in period_field_maps.items():
                if p_label in existing_p_map:
                    target_p = existing_p_map[p_label]
                    cur_f_names = {f.name for f in target_p.fields}
                    for fname, fobj in p_fdict.items():
                        if fname not in cur_f_names:
                            target_p.fields.append(fobj)
                else:
                    periods.append(Period(label=p_label, fields=list(p_fdict.values())))

    # Canonical Field Alias Standardizer & Auto-Promotion for Summary Totals
    canonical_alias_map = {
        "subtotal": ["subtotal", "sub_total", "sub total", "taxable value", "taxable_value", "taxable amount", "taxable_amount", "amount before tax", "amount_before_tax", "net amount", "net_amount"],
        "tax": ["tax", "tax_amount", "tax amount", "total tax", "total_tax", "gst", "cgst + sgst", "vat", "vat amount", "vat_amount"],
        "total": ["total", "total_amount", "total amount", "grand total", "grand_total", "invoice total", "invoice_total", "amount payable", "amount_payable", "net payable", "net_payable", "total (rs.)", "total (inr)"],
        "amount_paid": ["amount_paid", "amount paid", "cash paid", "cash_paid", "paid", "advance paid", "advance_paid"],
        "amount_due": ["amount_due", "amount due", "balance", "balance due", "balance_due", "payable", "balance payable", "balance_payable"],
        "assets": ["assets", "total assets", "total_assets", "grand total assets"],
        "total_assets": ["total assets", "assets total", "total_assets"],
        "liabilities": ["liabilities", "total liabilities", "total_liabilities"],
        "total_liabilities": ["total liabilities", "total_liabilities"],
        "total_capital_and_liabilities": ["total capital and liabilities", "total capital & liabilities", "total equity and liabilities", "total liabilities and equity", "capital and liabilities"],
        "capital": ["capital", "equity", "total equity", "total_equity", "share capital", "capital / shareholder equity"],
        "total_income": ["total_income", "total income", "gross income", "gross_income"],
        "total_expenditure": ["total_expenditure", "total expenditure", "total expenses", "total_expenses"],
        "net_profit": ["net_profit", "net profit", "profit after tax", "profit_after_tax"]
    }

    # Ensure canonical key aliases promote to standard field names if present under a non-standard key
    for canonical_name, aliases in canonical_alias_map.items():
        if canonical_name not in field_map_dict:
            for alias in aliases:
                if alias in field_map_dict:
                    orig_f = field_map_dict[alias]
                    promoted_f = ExtractedField(
                        name=canonical_name,
                        value=orig_f.value,
                        normalized_value=orig_f.normalized_value,
                        evidence=orig_f.evidence,
                        page_number=orig_f.page_number,
                        confidence=orig_f.confidence,
                        status=orig_f.status
                    )
                    fields.append(promoted_f)
                    field_map_dict[canonical_name] = promoted_f
                    break

    # If top-level fields map is missing canonical summary totals but periods has them, promote first period's values
    if periods and doc_type_clean == "balance_sheet":
        for p in periods:
            pf_map = {pf.name: pf for pf in p.fields}
            if "total_assets" in pf_map and "assets" not in pf_map:
                tot_a = pf_map["total_assets"]
                p.fields.append(ExtractedField(
                    name="assets",
                    value=tot_a.value,
                    normalized_value=tot_a.normalized_value,
                    evidence=tot_a.evidence,
                    page_number=tot_a.page_number
                ))

        first_p = periods[0]
        for pf in first_p.fields:
            if pf.name in ("assets", "total_assets", "capital", "equity", "liabilities", "total_liabilities", "total_capital_and_liabilities", "current_assets", "non_current_assets", "current_liabilities", "non_current_liabilities") and pf.name not in field_map_dict:
                promoted_f = ExtractedField(
                    name=pf.name,
                    value=pf.value,
                    normalized_value=pf.normalized_value,
                    evidence=pf.evidence,
                    page_number=pf.page_number,
                    confidence=pf.confidence,
                    status=pf.status
                )
                fields.append(promoted_f)
                field_map_dict[pf.name] = promoted_f

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
        document_type=doc_type_clean,
        fields=fields,
        line_items=line_items,
        tables=tables,
        periods=periods,
        notes=notes,
        raw_text_by_page=raw_text_pages,
        metadata={"normalized": True}
    )


