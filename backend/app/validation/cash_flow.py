from typing import List, Dict, Optional, Tuple
from app.schemas.extraction import DocumentExtraction
from app.schemas.validation import ValidationCheck
from app.core.config import settings
from decimal import Decimal

def validate_cash_flow(extraction: DocumentExtraction) -> List[ValidationCheck]:
    checks: List[ValidationCheck] = []
    abs_tol = settings.VALIDATION_ABSOLUTE_TOLERANCE

    period_buckets: List[Tuple[str, Dict[str, Optional[float]]]] = []
    if extraction.periods:
        for p in extraction.periods:
            p_map = {f.name.lower().strip(): f.normalized_value for f in p.fields}
            period_buckets.append((p.label, p_map))
    else:
        top_map = {f.name.lower().strip(): f.normalized_value for f in extraction.fields}
        period_buckets.append(("General", top_map))

    for label, field_map in period_buckets:
        op_cash = field_map.get("operating_cash_flow") or field_map.get("net_cash_from_operating_activities")
        inv_cash = field_map.get("investing_cash_flow") or field_map.get("net_cash_from_investing_activities")
        fin_cash = field_map.get("financing_cash_flow") or field_map.get("net_cash_from_financing_activities")
        fx_effect = field_map.get("foreign_exchange_effect") or 0.0
        net_increase = field_map.get("net_increase") or field_map.get("net_change_in_cash")

        opening_cash = field_map.get("opening_cash") or field_map.get("cash_at_beginning_of_period")
        closing_cash = field_map.get("closing_cash") or field_map.get("cash_at_end_of_period")
        adjustments = field_map.get("adjustments") or 0.0

        # Check 1: Operating + Investing + Financing + Foreign Exchange ≈ Net Increase
        check_name_1 = f"[{label}] Operating + Investing + Financing Cash Flows ≈ Net Increase"
        formula_1 = "operating + investing + financing + fx_effect ≈ net_increase"
        operands_1 = {
            "operating_cash": op_cash,
            "investing_cash": inv_cash,
            "financing_cash": fin_cash,
            "net_increase": net_increase
        }

        if op_cash is not None and inv_cash is not None and fin_cash is not None and net_increase is not None:
            calc_increase = float(
                Decimal(str(op_cash)) + Decimal(str(inv_cash)) + Decimal(str(fin_cash)) + Decimal(str(fx_effect))
            )
            variance_1 = abs(calc_increase - net_increase)
            status_1 = "PASS" if variance_1 <= abs_tol else "FAIL"
            checks.append(ValidationCheck(
                check_name=check_name_1,
                formula=formula_1,
                operands=operands_1,
                calculated_value=calc_increase,
                reported_value=net_increase,
                variance=variance_1,
                tolerance=abs_tol,
                status=status_1,
                period=label
            ))
        else:
            checks.append(ValidationCheck(
                check_name=check_name_1,
                formula=formula_1,
                operands=operands_1,
                tolerance=abs_tol,
                status="NOT_APPLICABLE",
                details="Missing one or more cash flow activity components (operating, investing, financing, or net_increase).",
                period=label
            ))

        # Check 2: Opening Cash + Net Increase + Adjustments ≈ Closing Cash
        check_name_2 = f"[{label}] Opening Cash + Net Increase + Adjustments ≈ Closing Cash"
        formula_2 = "opening_cash + net_increase + adjustments ≈ closing_cash"
        operands_2 = {
            "opening_cash": opening_cash,
            "net_increase": net_increase,
            "adjustments": adjustments,
            "closing_cash": closing_cash
        }

        if opening_cash is not None and net_increase is not None and closing_cash is not None:
            calc_closing = float(
                Decimal(str(opening_cash)) + Decimal(str(net_increase)) + Decimal(str(adjustments))
            )
            variance_2 = abs(calc_closing - closing_cash)
            status_2 = "PASS" if variance_2 <= abs_tol else "FAIL"
            checks.append(ValidationCheck(
                check_name=check_name_2,
                formula=formula_2,
                operands=operands_2,
                calculated_value=calc_closing,
                reported_value=closing_cash,
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
                details="Missing opening_cash, net_increase, or closing_cash.",
                period=label
            ))

    return checks
