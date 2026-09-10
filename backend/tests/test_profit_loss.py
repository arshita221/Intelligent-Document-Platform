from app.validation.profit_loss import validate_profit_loss
from app.schemas.extraction import DocumentExtraction, ExtractedField, Period

def test_profit_loss_passing(mock_profit_loss_passing):
    checks = validate_profit_loss(mock_profit_loss_passing)
    failed = [c for c in checks if c.status == "FAIL"]
    passed = [c for c in checks if c.status == "PASS"]
    
    assert len(failed) == 0
    assert len(passed) >= 3

def test_profit_loss_failing():
    doc = DocumentExtraction(
        document_type="profit_loss",
        fields=[
            ExtractedField(name="revenue", value="100000", normalized_value=100000.0),
            ExtractedField(name="other_income", value="20000", normalized_value=20000.0),
            ExtractedField(name="total_income", value="150000", normalized_value=150000.0) # 100k + 20k != 150k -> FAIL
        ]
    )
    checks = validate_profit_loss(doc)
    failed = [c for c in checks if c.status == "FAIL"]
    assert len(failed) >= 1
