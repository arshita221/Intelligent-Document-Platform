from typing import List, Dict, Optional, Tuple
from app.schemas.extraction import DocumentExtraction
from app.schemas.validation import ValidationCheck
from app.core.config import settings
from decimal import Decimal

def validate_profit_loss(extraction: DocumentExtraction) -> List[ValidationCheck]:
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
        # Income components
        revenue = field_map.get("revenue") or field_map.get("sales") or field_map.get("interest_earned")
        other_income = field_map.get("other_income")
        total_income = field_map.get("total_income")

        # Expense components
        interest_exp = field_map.get("interest_expended")
        op_expenses = field_map.get("operating_expenses") or field_map.get("expenses")
        provisions = field_map.get("provisions_and_contingencies") or field_map.get("provisions")
        total_expenditure = field_map.get("total_expenditure") or field_map.get("total_expenses")

        # Profit components
        profit_before_tax = field_map.get("profit_before_tax")
        tax = field_map.get("tax")
        minority_interest = field_map.get("minority_interest") or 0.0
        net_profit = field_map.get("net_profit") or field_map.get("consolidated_net_profit_before_minority_interest")

        # Check 1: Revenue/Interest Earned + Other Income ≈ Total Income
        check_name_1 = f"[{label}] Primary Income + Other Income ≈ Total Income"
        formula_1 = "primary_income + other_income ≈ total_income"
        operands_1 = {"primary_income": revenue, "other_income": other_income, "total_income": total_income}

        if revenue is not None and other_income is not None and total_income is not None:
            calc_income = float(Decimal(str(revenue)) + Decimal(str(other_income)))
            variance_1 = abs(calc_income - total_income)
            status_1 = "PASS" if variance_1 <= abs_tol else "FAIL"
            checks.append(ValidationCheck(
                check_name=check_name_1,
                formula=formula_1,
                operands=operands_1,
                calculated_value=calc_income,
                reported_value=total_income,
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
                details="Missing income components (primary_income, other_income, or total_income).",
                period=label
            ))

        # Check 2: Expenses + Provisions ≈ Total Expenditure
        check_name_2 = f"[{label}] Operating Expenses + Provisions/Interest ≈ Total Expenditure"
        formula_2 = "operating_expenses + provisions_or_interest ≈ total_expenditure"
        
        # Gather available expense components
        exp_components = []
        if interest_exp is not None: exp_components.append(("interest_expended", interest_exp))
        if op_expenses is not None: exp_components.append(("operating_expenses", op_expenses))
        if provisions is not None: exp_components.append(("provisions", provisions))
        
        operands_2 = {k: v for k, v in exp_components}
        operands_2["total_expenditure"] = total_expenditure

        if len(exp_components) >= 2 and total_expenditure is not None:
            calc_exp = float(sum(Decimal(str(v)) for _, v in exp_components))
            variance_2 = abs(calc_exp - total_expenditure)
            status_2 = "PASS" if variance_2 <= abs_tol else "FAIL"
            checks.append(ValidationCheck(
                check_name=check_name_2,
                formula=formula_2,
                operands=operands_2,
                calculated_value=calc_exp,
                reported_value=total_expenditure,
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
                details="Insufficient expenditure breakdown components.",
                period=label
            ))

        # Check 3: Total Income - Total Expenditure ≈ Net Profit / Profit Before Tax
        target_profit = profit_before_tax if profit_before_tax is not None else net_profit
        target_name = "profit_before_tax" if profit_before_tax is not None else "net_profit"
        check_name_3 = f"[{label}] Total Income - Total Expenditure ≈ {target_name.replace('_', ' ').title()}"
        formula_3 = f"total_income - total_expenditure ≈ {target_name}"
        operands_3 = {"total_income": total_income, "total_expenditure": total_expenditure, target_name: target_profit}

        if total_income is not None and total_expenditure is not None and target_profit is not None:
            calc_profit = float(Decimal(str(total_income)) - Decimal(str(total_expenditure)))
            if tax is not None and target_name == "net_profit":
                calc_profit = float(Decimal(str(calc_profit)) - Decimal(str(tax)) - Decimal(str(minority_interest)))
                
            variance_3 = abs(calc_profit - target_profit)
            status_3 = "PASS" if variance_3 <= abs_tol else "FAIL"
            checks.append(ValidationCheck(
                check_name=check_name_3,
                formula=formula_3,
                operands=operands_3,
                calculated_value=calc_profit,
                reported_value=target_profit,
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
                details="Missing total_income, total_expenditure, or profit fields.",
                period=label
            ))

    return checks
