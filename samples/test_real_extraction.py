import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.database import SessionLocal, init_db
from app.services.document_service import process_document_pipeline

def run_real_extractions():
    init_db()
    db = SessionLocal()
    
    samples_dir = os.path.dirname(__file__)
    documents = [
        ("invoice", os.path.join(samples_dir, "sample_invoice.pdf")),
        ("balance_sheet", os.path.join(samples_dir, "sample_balance_sheet.pdf")),
        ("profit_loss", os.path.join(samples_dir, "sample_profit_loss.pdf")),
        ("cash_flow", os.path.join(samples_dir, "sample_cash_flow.pdf"))
    ]
    
    print("==================================================")
    print("REAL GROQ QWEN 3.8 27B E2E DOCUMENT EXTRACTION TEST")
    print("==================================================")
    
    for doc_type, file_path in documents:
        filename = os.path.basename(file_path)
        print(f"\nProcessing {doc_type.upper()} ({filename})...")
        
        resp, status_code = process_document_pipeline(file_path, filename, doc_type, db)
        
        print(f"HTTP Status Code: {status_code}")
        print(f"Document Name:    {resp.document_name}")
        print(f"Processing Status:{resp.processing_status}")
        print(f"Extracted Fields: {len(resp.extracted_data.fields)}")
        print(f"Line Items Count: {len(resp.extracted_data.line_items)}")
        print(f"Periods Count:    {len(resp.extracted_data.periods)}")
        print(f"Math Checks:      {len(resp.validation.checks)} (Passed: {resp.validation.passed_count}, Failed: {resp.validation.failed_count})")
        print(f"Math Status:      {resp.validation.overall_status}")
        
        # Pacing delay between Groq API calls
        time.sleep(3)

def diagnose_groq_limits():
    from app.core.config import settings
    from groq import Groq, RateLimitError
    client = Groq(api_key=settings.GROQ_API_KEY)
    print("\n--- DIAGNOSING GROQ API RATE LIMIT HEADERS ---")
    print(f"Model: {settings.GROQ_MODEL}")
    print(f"GROQ_API_KEY Configured: {settings.is_groq_api_key_configured}")
    
    try:
        raw_resp = client.chat.completions.with_raw_response.create(
            model=settings.GROQ_MODEL,
            messages=[{"role": "user", "content": "Respond in json format: {\"test\": \"ok\"}"}],
            response_format={"type": "json_object"},
            max_tokens=50
        )
        print("API Status Code:", raw_resp.status_code)
        print("Rate Limit Headers:")
        for k, v in raw_resp.headers.items():
            if k.lower().startswith(("x-ratelimit", "retry-after")):
                print(f"  {k}: {v}")
    except RateLimitError as rle:
        print("CAUGHT RateLimitError 429:")
        print("Message:", rle.message)
        print("Headers:")
        if hasattr(rle, "response") and rle.response is not None:
            for k, v in rle.response.headers.items():
                if k.lower().startswith(("x-ratelimit", "retry-after")):
                    print(f"  {k}: {v}")
    except Exception as ex:
        print("CAUGHT Exception:", type(ex), str(ex))

if __name__ == "__main__":
    diagnose_groq_limits()
