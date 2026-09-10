from app.validation.invoice import validate_invoice
from app.schemas.extraction import DocumentExtraction, ExtractedField, LineItem

def test_invoice_validation_passing(mock_invoice_passing):
    checks = validate_invoice(mock_invoice_passing)
    
    assert len(checks) >= 4
    # All checks should pass
    passed = [c for c in checks if c.status == "PASS"]
    failed = [c for c in checks if c.status == "FAIL"]
    
    assert len(failed) == 0
    assert len(passed) >= 3

def test_invoice_validation_failing(mock_invoice_failing):
    checks = validate_invoice(mock_invoice_failing)
    
    failed = [c for c in checks if c.status == "FAIL"]
    assert len(failed) >= 2 # Line total mismatch & subtotal+tax mismatch

def test_invoice_validation_missing_fields():
    doc = DocumentExtraction(
        document_type="invoice",
        fields=[ExtractedField(name="total", value="100.00", normalized_value=100.0)]
        # Missing subtotal, tax, line items
    )
    checks = validate_invoice(doc)
    
    na_checks = [c for c in checks if c.status == "NOT_APPLICABLE"]
    assert len(na_checks) >= 2
    assert all(c.status != "FAIL" for c in checks)
