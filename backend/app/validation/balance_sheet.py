from typing import List, Dict, Optional
from app.schemas.extraction import DocumentExtraction, ExtractedField, Period
from app.schemas.validation import ValidationCheck
from app.core.config import settings
from decimal import Decimal

def validate_balance_sheet(extraction: DocumentExtraction) -> List[ValidationCheck]:
    checks: List[ValidationCheck] = []
    abs_tol = settings.VALIDATION_ABSOLUTE_TOLERANCE

    # If periods exist, evaluate per period; otherwise create default period from top-level fields
    period_buckets: List[Tuple[str, Dict[str, Optional[float]]]] = []
    
    if extraction.periods:
        for p in extraction.periods:
            p_map = {f.name.lower().strip(): f.normalized_value for f in p.fields}
            period_buckets.append((p.label, p_map))
    else:
        top_map = {f.name.lower().strip(): f.normalized_value for f in extraction.fields}
        period_buckets.append(("General", top_map))

    for label, field_map in period_buckets:
        # Field lookups with canonical fallbacks
        assets = field_map.get("assets") or field_map.get("total_assets")
        capital = field_map.get("capital") or field_map.get("equity") or field_map.get("total_equity")
        liabilities = field_map.get("liabilities") or field_map.get("total_liabilities")
        cap_liab = field_map.get("capital_and_liabilities") or field_map.get("total_capital_and_liabilities") or field_map.get("total_liabilities_and_equity")

        curr_assets = field_map.get("current_assets")
        non_curr_assets = field_map.get("non_current_assets")
        
        curr_liab = field_map.get("current_liabilities")
        non_curr_liab = field_map.get("non_current_liabilities")

        # 1. Fundamental Accounting Equation: Capital & Equity + Liabilities ≈ Total Assets
        check_name_1 = f"[{label}] Capital & Equity + Liabilities ≈ Total Assets"
        formula_1 = "capital_and_equity + liabilities ≈ assets"
        operands_1 = {"capital_or_equity": capital, "liabilities": liabilities, "assets": assets}

        if capital is not None and liabilities is not None and assets is not None:
            calc_val = float(Decimal(str(capital)) + Decimal(str(liabilities)))
            variance = abs(calc_val - assets)
            status = "PASS" if variance <= abs_tol else "FAIL"
            checks.append(ValidationCheck(
                check_name=check_name_1,
                formula=formula_1,
                operands=operands_1,
                calculated_value=calc_val,
                reported_value=assets,
                variance=variance,
                tolerance=abs_tol,
                status=status,
                period=label
            ))
        else:
            checks.append(ValidationCheck(
                check_name=check_name_1,
                formula=formula_1,
                operands=operands_1,
                tolerance=abs_tol,
                status="NOT_APPLICABLE",
                details="Missing required fields for capital/equity, liabilities, or assets.",
                period=label
            ))

        # 2. Current Assets + Non-current Assets ≈ Total Assets
        check_name_2 = f"[{label}] Current Assets + Non-Current Assets ≈ Total Assets"
        formula_2 = "current_assets + non_current_assets ≈ total_assets"
        operands_2 = {"current_assets": curr_assets, "non_current_assets": non_curr_assets, "total_assets": assets}

        if curr_assets is not None and non_curr_assets is not None and assets is not None:
            calc_assets = float(Decimal(str(curr_assets)) + Decimal(str(non_curr_assets)))
            variance_2 = abs(calc_assets - assets)
            status_2 = "PASS" if variance_2 <= abs_tol else "FAIL"
            checks.append(ValidationCheck(
                check_name=check_name_2,
                formula=formula_2,
                operands=operands_2,
                calculated_value=calc_assets,
                reported_value=assets,
                variance=variance_2,
                tolerance=abs_tol,
                status=status_2,
                period=label
            ))
        else:
            checks.append(ValidationCheck(
                check_name=check_name_2,
                formula=formula_2,
                operands=operands_2,
                tolerance=abs_tol,
                status="NOT_APPLICABLE",
                details="Missing current_assets, non_current_assets, or total_assets.",
                period=label
            ))

        # 3. Current Liabilities + Non-current Liabilities ≈ Total Liabilities
        check_name_3 = f"[{label}] Current Liabilities + Non-Current Liabilities ≈ Total Liabilities"
        formula_3 = "current_liabilities + non_current_liabilities ≈ total_liabilities"
        operands_3 = {"current_liabilities": curr_liab, "non_current_liabilities": non_curr_liab, "total_liabilities": liabilities}

        if curr_liab is not None and non_curr_liab is not None and liabilities is not None:
            calc_liab = float(Decimal(str(curr_liab)) + Decimal(str(non_curr_liab)))
            variance_3 = abs(calc_liab - liabilities)
            status_3 = "PASS" if variance_3 <= abs_tol else "FAIL"
            checks.append(ValidationCheck(
                check_name=check_name_3,
                formula=formula_3,
                operands=operands_3,
                calculated_value=calc_liab,
                reported_value=liabilities,
                variance=variance_3,
                tolerance=abs_tol,
                status=status_3,
                period=label
            ))
        else:
            checks.append(ValidationCheck(
                check_name=check_name_3,
                formula=formula_3,
                operands=operands_3,
                tolerance=abs_tol,
                status="NOT_APPLICABLE",
                details="Missing current_liabilities, non_current_liabilities, or total_liabilities.",
                period=label
            ))

    return checks
