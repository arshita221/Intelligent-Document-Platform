import pytest
from app.schemas.extraction import DocumentExtraction, ExtractedField, LineItem
from app.validation.engine import run_financial_validation

def test_validation_engine_all_not_applicable_returns_incomplete():
    # Document with missing financial summary totals -> all checks N/A
    extraction = DocumentExtraction(
        document_type="invoice",
        fields=[
            ExtractedField(name="invoice_no", value="INV-001", normalized_value=None),
            ExtractedField(name="dated", value="2025-01-01", normalized_value=None)
        ],
        line_items=[]
    )
    summary = run_financial_validation(extraction)
    assert summary.overall_status == "INCOMPLETE"
    assert summary.passed_count == 0
    assert summary.failed_count == 0
    assert summary.not_applicable_count > 0
    assert any("unavailable" in c.details.lower() for c in summary.checks if c.details)

def test_validation_engine_passing_checks_returns_pass():
    extraction = DocumentExtraction(
        document_type="invoice",
        fields=[
            ExtractedField(name="subtotal", value="100.00", normalized_value=100.0),
            ExtractedField(name="tax", value="10.00", normalized_value=10.0),
            ExtractedField(name="total", value="110.00", normalized_value=110.0)
        ],
        line_items=[]
    )
    summary = run_financial_validation(extraction)
    assert summary.overall_status == "PASS"
    assert summary.passed_count >= 1
    assert summary.failed_count == 0

def test_validation_engine_failing_checks_returns_failed():
    extraction = DocumentExtraction(
        document_type="invoice",
        fields=[
            ExtractedField(name="subtotal", value="100.00", normalized_value=100.0),
            ExtractedField(name="tax", value="10.00", normalized_value=10.0),
            ExtractedField(name="total", value="500.00", normalized_value=500.0)  # Incorrect total!
        ],
        line_items=[]
    )
    summary = run_financial_validation(extraction)
    assert summary.overall_status == "FAILED"
    assert summary.failed_count >= 1
