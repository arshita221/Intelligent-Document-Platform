from app.validation.cash_flow import validate_cash_flow
from app.schemas.extraction import DocumentExtraction, ExtractedField, Period

def test_cash_flow_passing_with_parentheses(mock_cash_flow_passing):
    checks = validate_cash_flow(mock_cash_flow_passing)
    failed = [c for c in checks if c.status == "FAIL"]
    passed = [c for c in checks if c.status == "PASS"]
    
    assert len(failed) == 0
    assert len(passed) >= 2

def test_cash_flow_failing():
    doc = DocumentExtraction(
        document_type="cash_flow",
        fields=[
            ExtractedField(name="operating_cash_flow", value="50000", normalized_value=50000.0),
            ExtractedField(name="investing_cash_flow", value="-20000", normalized_value=-20000.0),
            ExtractedField(name="financing_cash_flow", value="-10000", normalized_value=-10000.0),
            ExtractedField(name="net_increase", value="50000", normalized_value=50000.0) # 50k - 20k - 10k != 50k -> FAIL
        ]
    )
    checks = validate_cash_flow(doc)
    failed = [c for c in checks if c.status == "FAIL"]
    assert len(failed) >= 1
