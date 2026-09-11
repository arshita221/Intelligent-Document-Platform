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

def test_balance_sheet_label_aware_mapping_and_no_invoice_line_items():
    from app.services.groq_service import normalize_extraction_json
    
    # Raw JSON mimicking real live test of Consolidated Balance Sheet 2026
    raw_llm_data = {
        "document_type": "balance_sheet",
        "fields": [],
        "line_items": [
            {"description": "Capital", "amount": "500000", "evidence": "Capital: 500,000"},
            {"description": "Reserves and surplus", "amount": "200000", "evidence": "Reserves and Surplus: 200,000"},
            {"description": "Deposits", "amount": "300000", "evidence": "Deposits: 300,000"},
            {"description": "Borrowings", "amount": "100000", "evidence": "Borrowings: 100,000"},
            {"description": "Current Assets", "amount": "600000", "evidence": "Current Assets: 600,000"},
            {"description": "Non-Current Assets", "amount": "500000", "evidence": "Non-Current Assets: 500,000"},
            {"description": "Total Assets", "amount": "1100000", "evidence": "Total Assets: 1,100,000"}
        ]
    }
    
    extraction = normalize_extraction_json(raw_llm_data, "balance_sheet", [])
    
    # 1. Verify Balance Sheet rows were NOT converted to invoice line items
    assert len(extraction.line_items) == 0
    
    # 2. Verify fields were extracted and mapped label-aware
    f_dict = {f.name: f for f in extraction.fields}
    assert "capital" in f_dict
    assert f_dict["capital"].normalized_value == 500000.0
    assert "reserves_and_surplus" in f_dict
    assert f_dict["reserves_and_surplus"].normalized_value == 200000.0
    assert "deposits" in f_dict
    assert f_dict["deposits"].normalized_value == 300000.0
    assert "borrowings" in f_dict
    assert f_dict["borrowings"].normalized_value == 100000.0
    assert "current_assets" in f_dict
    assert f_dict["current_assets"].normalized_value == 600000.0
    assert "non_current_assets" in f_dict
    assert f_dict["non_current_assets"].normalized_value == 500000.0
    assert "total_assets" in f_dict or "assets" in f_dict
    
    # 3. Verify validation runs on canonical fields
    checks = validate_balance_sheet(extraction)
    curr_non_curr_check = next(c for c in checks if "Current Assets + Non-Current Assets" in c.check_name)
    assert curr_non_curr_check.status == "PASS"
    assert curr_non_curr_check.calculated_value == 1100000.0

def test_balance_sheet_not_applicable_on_missing_values():
    from app.services.groq_service import normalize_extraction_json
    
    raw_llm_data = {
        "document_type": "balance_sheet",
        "fields": [
            {"name": "Company", "value": "ABC Corp"},
            {"name": "Total Assets", "value": None}
        ]
    }
    
    extraction = normalize_extraction_json(raw_llm_data, "balance_sheet", [])
    
    # Missing values must remain null
    assets_f = next((f for f in extraction.fields if f.name in ("assets", "total_assets")), None)
    if assets_f:
        assert assets_f.value is None
        assert assets_f.normalized_value is None
        
    checks = validate_balance_sheet(extraction)
    assert all(c.status == "NOT_APPLICABLE" for c in checks)


def test_balance_sheet_context_aware_totals_disambiguation():
    from app.services.groq_service import normalize_extraction_json
    from app.validation.engine import run_financial_validation

    # Raw payload mimicking HDFC Bank style balance sheet table output
    raw_llm_data = {
        "document_type": "balance_sheet",
        "fields": [],
        "tables": [
            {
                "name": "Consolidated Balance Sheet",
                "headers": ["Particulars", "Schedule", "As at March 31, 2026", "As at March 31, 2025"],
                "rows": [
                    ["Capital", "1", "1,539.34", "765.22"],
                    ["Reserves and surplus", "2", "579,975.02", "517,218.98"],
                    ["Deposits", "3", "3,099,638.29", "2,710,898.23"],
                    ["Borrowings", "4", "588,484.55", "634,605.57"],
                    ["Other liabilities and provisions", "5", "252,977.53", "188,163.66"],
                    ["Total", "", "4,908,040.84", "4,392,417.42"],
                    ["Cash and balances with Reserve Bank of India", "6", "200,707.11", "144,390.25"],
                    ["Balances with banks", "7", "111,218.94", "105,557.65"],
                    ["Investments", "8", "1,280,216.29", "1,188,472.89"],
                    ["Advances", "9", "3,050,783.23", "2,724,938.16"],
                    ["Fixed assets", "10", "16,491.59", "15,257.94"],
                    ["Other assets", "11", "248,623.68", "215,800.53"],
                    ["Total", "", "4,908,040.84", "4,392,417.42"]
                ]
            }
        ]
    }

    extraction = normalize_extraction_json(raw_llm_data, "balance_sheet", [])
    
    # 1. Verify 1st Total mapped to total_capital_and_liabilities and 2nd Total mapped to total_assets
    f_map = {f.name: f for f in extraction.fields}
    assert "total_capital_and_liabilities" in f_map
    assert f_map["total_capital_and_liabilities"].normalized_value == 4908040.84
    assert "total_assets" in f_map
    assert f_map["total_assets"].normalized_value == 4908040.84
    
    # 2. Verify periods parsed multi-period values
    assert len(extraction.periods) >= 2
    p_2026 = next(p for p in extraction.periods if p.label == "2026")
    p_2025 = next(p for p in extraction.periods if p.label == "2025")
    
    p2026_map = {f.name: f.normalized_value for f in p_2026.fields}
    p2025_map = {f.name: f.normalized_value for f in p_2025.fields}
    
    assert p2026_map.get("total_capital_and_liabilities") == 4908040.84
    assert p2025_map.get("total_capital_and_liabilities") == 4392417.42
    assert p2026_map.get("total_assets") == 4908040.84
    assert p2025_map.get("total_assets") == 4392417.42

    # 3. Verify bank-style statement without separate liabilities breakdown safely remains INCOMPLETE (no fabricated PASS)
    summary = run_financial_validation(extraction)
    assert summary.overall_status == "INCOMPLETE"
    assert summary.passed_count == 0
    assert summary.failed_count == 0


def test_balance_sheet_ambiguous_total_remains_null():
    from app.services.groq_service import normalize_extraction_json
    from app.validation.engine import run_financial_validation

    # Standalone Total with no section context or surrounding fields
    raw_llm_data = {
        "document_type": "balance_sheet",
        "fields": [
            {"name": "Company Name", "value": "Unknown Corp"},
            {"name": "Total", "value": "1000000", "evidence": "Total 1,000,000"}
        ]
    }

    extraction = normalize_extraction_json(raw_llm_data, "balance_sheet", [])
    
    # Ambiguous standalone total should remain unmapped to total_assets or total_capital_and_liabilities
    f_map = {f.name: f for f in extraction.fields}
    assert "total_assets" not in f_map
    assert "total_capital_and_liabilities" not in f_map
    
    summary = run_financial_validation(extraction)
    assert summary.overall_status == "INCOMPLETE"


def test_balance_sheet_total_capital_and_liabilities_not_mapped_to_total_assets():
    """Proves that 'Total Capital & Liabilities' does NOT become total_assets or liabilities."""
    from app.services.groq_service import normalize_extraction_json

    raw_llm_data = {
        "document_type": "balance_sheet",
        "fields": [
            {"name": "Total Capital and Liabilities", "value": "15808304373", "evidence": "Total Capital and Liabilities 15,808,304,373"}
        ]
    }

    extraction = normalize_extraction_json(raw_llm_data, "balance_sheet", [])
    f_map = {f.name: f for f in extraction.fields}

    # Must preserve the exact semantic identity
    assert "total_capital_and_liabilities" in f_map
    assert f_map["total_capital_and_liabilities"].normalized_value == 15808304373.0
    # Must NOT be mislabeled as total_assets or liabilities
    assert "total_assets" not in f_map
    assert "assets" not in f_map
    assert "liabilities" not in f_map


def test_balance_sheet_explicit_total_assets_maps_to_total_assets():
    """Proves that an explicit 'Total Assets' row correctly maps to total_assets."""
    from app.services.groq_service import normalize_extraction_json

    raw_llm_data = {
        "document_type": "balance_sheet",
        "fields": [
            {"name": "Total Assets", "value": "15808304373", "evidence": "Total Assets 15,808,304,373"}
        ]
    }

    extraction = normalize_extraction_json(raw_llm_data, "balance_sheet", [])
    f_map = {f.name: f for f in extraction.fields}

    assert "total_assets" in f_map
    assert f_map["total_assets"].normalized_value == 15808304373.0


def test_balance_sheet_bank_style_no_separate_assets_safely_not_applicable():
    """Proves that bank-style statements with Capital & Liabilities but no separate Total Assets remain NOT_APPLICABLE."""
    from app.validation.balance_sheet import validate_balance_sheet

    doc = DocumentExtraction(
        document_type="balance_sheet",
        fields=[
            ExtractedField(name="capital", value="5483286", normalized_value=5483286.0),
            ExtractedField(name="deposits", value="11462071336", normalized_value=11462071336.0),
            ExtractedField(name="borrowings", value="1868343231", normalized_value=1868343231.0),
            ExtractedField(name="total_capital_and_liabilities", value="15808304373", normalized_value=15808304373.0),
        ]
    )

    checks = validate_balance_sheet(doc)
    check_1 = next(c for c in checks if "Capital & Equity + Liabilities" in c.check_name)
    assert check_1.status == "NOT_APPLICABLE"
    assert check_1.operands.get("assets") is None
    assert check_1.operands.get("liabilities") is None


