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

if __name__ == "__main__":
    run_real_extractions()
