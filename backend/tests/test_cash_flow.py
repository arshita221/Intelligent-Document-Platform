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


def test_cash_flow_table_recovery_and_multi_period():
    from app.services.groq_service import normalize_extraction_json
    from app.validation.engine import run_financial_validation

    # Raw payload mimicking Cash Flow table output returned under tables array
    raw_llm_data = {
        "document_type": "cash_flow",
        "fields": [],
        "tables": [
            {
                "name": "Consolidated Cash Flow Statement",
                "headers": ["Particulars", "Year Ended March 31, 2026", "Year Ended March 31, 2025"],
                "rows": [
                    ["Net cash flow from operating activities", "150,000.00", "120,000.00"],
                    ["Net cash flow from investing activities", "-50,000.00", "-40,000.00"],
                    ["Net cash flow from financing activities", "-30,000.00", "-20,000.00"],
                    ["Net increase in cash and cash equivalents", "70,000.00", "60,000.00"],
                    ["Cash and cash equivalents at beginning of year", "100,000.00", "40,000.00"],
                    ["Cash and cash equivalents at end of year", "170,000.00", "100,000.00"]
                ]
            }
        ]
    }

    extraction = normalize_extraction_json(raw_llm_data, "cash_flow", [])

    # 1. Verify fields recovered and canonical aliases mapped
    f_map = {f.name: f for f in extraction.fields}
    assert "operating_cash_flow" in f_map
    assert f_map["operating_cash_flow"].normalized_value == 150000.0
    assert "net_change_in_cash" in f_map
    assert f_map["net_change_in_cash"].normalized_value == 70000.0

    # 2. Verify deterministic validation passes
    summary = run_financial_validation(extraction)
    assert summary.overall_status == "PASS"
    assert summary.passed_count >= 1
    assert summary.failed_count == 0

