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


def test_profit_loss_table_recovery_and_multi_period():
    from app.services.groq_service import normalize_extraction_json
    from app.validation.engine import run_financial_validation

    # Raw payload mimicking P&L table output returned under tables array
    raw_llm_data = {
        "document_type": "profit_loss",
        "fields": [],
        "tables": [
            {
                "name": "Consolidated Profit and Loss Statement",
                "headers": ["Particulars", "Schedule", "Year Ended March 31, 2026", "Year Ended March 31, 2025"],
                "rows": [
                    ["Interest earned", "13", "500,000.00", "450,000.00"],
                    ["Other income", "14", "50,000.00", "40,000.00"],
                    ["Total income", "", "550,000.00", "490,000.00"],
                    ["Operating expenses", "16", "200,000.00", "180,000.00"],
                    ["Total expenditure", "", "200,000.00", "180,000.00"],
                    ["Net profit for the year", "", "350,000.00", "310,000.00"]
                ]
            }
        ]
    }

    extraction = normalize_extraction_json(raw_llm_data, "profit_loss", [])

    # 1. Verify fields recovered and canonical aliases mapped
    f_map = {f.name: f for f in extraction.fields}
    assert "primary_income" in f_map or "total_income" in f_map
    assert "total_income" in f_map
    assert f_map["total_income"].normalized_value == 550000.0
    assert "net_profit" in f_map
    assert f_map["net_profit"].normalized_value == 350000.0

    # 2. Verify deterministic validation passes
    summary = run_financial_validation(extraction)
    assert summary.overall_status == "PASS"
    assert summary.passed_count >= 1
    assert summary.failed_count == 0


def test_profit_loss_primary_income_alias_pass():
    """Proves that primary_income + other_income == total_income produces PASS."""
    doc = DocumentExtraction(
        document_type="profit_loss",
        fields=[
            ExtractedField(name="primary_income", value="348615.15", normalized_value=348615.15),
            ExtractedField(name="other_income", value="146847.66", normalized_value=146847.66),
            ExtractedField(name="total_income", value="495462.81", normalized_value=495462.81),
        ]
    )
    checks = validate_profit_loss(doc)
    income_check = next(c for c in checks if "Primary Income" in c.check_name)
    assert income_check.status == "PASS"
    assert income_check.calculated_value == 495462.81
    assert income_check.reported_value == 495462.81
    assert income_check.variance == 0.0


def test_profit_loss_missing_operands_remain_not_applicable():
    """Proves that missing income components remain safely NOT_APPLICABLE."""
    doc = DocumentExtraction(
        document_type="profit_loss",
        fields=[
            ExtractedField(name="total_income", value="495462.81", normalized_value=495462.81),
        ]
    )
    checks = validate_profit_loss(doc)
    income_check = next(c for c in checks if "Primary Income" in c.check_name)
    assert income_check.status == "NOT_APPLICABLE"
    assert "Missing income components" in income_check.details


def test_profit_loss_minority_interest_no_tax_pass():
    """total_income - total_expenditure - minority_interest ≈ net_profit → PASS
    Mirrors the Consolidated P&L 2026 scenario: no tax field present."""
    doc = DocumentExtraction(
        document_type="profit_loss",
        fields=[
            ExtractedField(name="primary_income", value="348615.15", normalized_value=348615.15),
            ExtractedField(name="other_income", value="146847.66", normalized_value=146847.66),
            ExtractedField(name="total_income", value="495462.81", normalized_value=495462.81),
            ExtractedField(name="total_expenditure", value="416243.35", normalized_value=416243.35),
            ExtractedField(name="minority_interest", value="3193.49", normalized_value=3193.49),
            ExtractedField(name="net_profit", value="76025.97", normalized_value=76025.97),
        ]
    )
    checks = validate_profit_loss(doc)
    profit_check = next(c for c in checks if "Total Income - Total Expenditure" in c.check_name)
    assert profit_check.status == "PASS", f"Expected PASS, got {profit_check.status} (calc={profit_check.calculated_value}, reported={profit_check.reported_value}, var={profit_check.variance})"
    # 495462.81 - 416243.35 - 3193.49 = 76025.97
    assert abs(profit_check.calculated_value - 76025.97) < 0.01


def test_profit_loss_minority_interest_with_tax_pass():
    """total_income - total_expenditure - tax - minority_interest ≈ net_profit → PASS"""
    doc = DocumentExtraction(
        document_type="profit_loss",
        fields=[
            ExtractedField(name="revenue", value="500000", normalized_value=500000.0),
            ExtractedField(name="other_income", value="50000", normalized_value=50000.0),
            ExtractedField(name="total_income", value="550000", normalized_value=550000.0),
            ExtractedField(name="total_expenditure", value="200000", normalized_value=200000.0),
            ExtractedField(name="tax", value="100000", normalized_value=100000.0),
            ExtractedField(name="minority_interest", value="10000", normalized_value=10000.0),
            ExtractedField(name="net_profit", value="240000", normalized_value=240000.0),
        ]
    )
    checks = validate_profit_loss(doc)
    profit_check = next(c for c in checks if "Total Income - Total Expenditure" in c.check_name)
    assert profit_check.status == "PASS"
    # 550000 - 200000 - 100000 - 10000 = 240000
    assert abs(profit_check.calculated_value - 240000.0) < 0.01


def test_profit_loss_minority_interest_genuine_mismatch_fail():
    """total_income - total_expenditure - minority_interest != net_profit → FAIL"""
    doc = DocumentExtraction(
        document_type="profit_loss",
        fields=[
            ExtractedField(name="total_income", value="500000", normalized_value=500000.0),
            ExtractedField(name="total_expenditure", value="200000", normalized_value=200000.0),
            ExtractedField(name="minority_interest", value="10000", normalized_value=10000.0),
            ExtractedField(name="net_profit", value="100000", normalized_value=100000.0),  # should be 290000
        ]
    )
    checks = validate_profit_loss(doc)
    profit_check = next(c for c in checks if "Total Income - Total Expenditure" in c.check_name)
    assert profit_check.status == "FAIL"
    # 500000 - 200000 - 10000 = 290000, but reported 100000 → FAIL
    assert profit_check.variance > 100000
