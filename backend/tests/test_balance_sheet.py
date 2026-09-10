from app.validation.balance_sheet import validate_balance_sheet
from app.schemas.extraction import DocumentExtraction, ExtractedField, Period

def test_balance_sheet_multi_period_passing(mock_balance_sheet_multi_period):
    checks = validate_balance_sheet(mock_balance_sheet_multi_period)
    
    # Must evaluate 2024 and 2023 independently
    periods_tested = set(c.period for c in checks if c.period)
    assert "2024" in periods_tested
    assert "2023" in periods_tested
    
    failed = [c for c in checks if c.status == "FAIL"]
    assert len(failed) == 0

def test_balance_sheet_failing():
    doc = DocumentExtraction(
        document_type="balance_sheet",
        fields=[
            ExtractedField(name="capital", value="500000", normalized_value=500000.0),
            ExtractedField(name="liabilities", value="300000", normalized_value=300000.0),
            ExtractedField(name="assets", value="900000", normalized_value=900000.0) # 500k + 300k != 900k -> FAIL
        ]
    )
    checks = validate_balance_sheet(doc)
    failed = [c for c in checks if c.status == "FAIL"]
    assert len(failed) >= 1
    assert failed[0].variance == 100000.0
