from typing import List, Dict, Optional, Any
from app.schemas.extraction import DocumentExtraction, ExtractedField
from app.schemas.validation import ValidationCheck
from app.core.config import settings
from decimal import Decimal

def validate_invoice(extraction: DocumentExtraction) -> List[ValidationCheck]:
    checks: List[ValidationCheck] = []
    abs_tol = settings.VALIDATION_ABSOLUTE_TOLERANCE
    
    # Helper to look up field normalized_value from extraction fields
    field_map: Dict[str, Optional[float]] = {}
    for f in extraction.fields:
        field_map[f.name.lower().strip()] = f.normalized_value

    # Check A: Quantity * Unit Price = Line Total for each line item
    for idx, item in enumerate(extraction.line_items, 1):
        qty = item.quantity
        price = item.unit_price
        total = item.total or item.amount
        
        operands = {"quantity": qty, "unit_price": price, "line_total": total}
        check_name = f"Line Item {idx}: Quantity × Unit Price ≈ Line Total"
        formula = "quantity * unit_price ≈ line_total"
        
        if qty is not None and price is not None and total is not None:
            calc_val = float(Decimal(str(qty)) * Decimal(str(price)))
            variance = abs(calc_val - total)
            status = "PASS" if variance <= abs_tol else "FAIL"
            checks.append(ValidationCheck(
                check_name=check_name,
                formula=formula,
                operands=operands,
                calculated_value=calc_val,
                reported_value=total,
                variance=variance,
                tolerance=abs_tol,
                status=status
            ))
        else:
            checks.append(ValidationCheck(
                check_name=check_name,
                formula=formula,
                operands=operands,
                tolerance=abs_tol,
                status="NOT_APPLICABLE",
                details="Missing one or more required fields (quantity, unit_price, line_total)."
            ))

    # Check B: Sum of line totals = subtotal / total
    line_totals = [item.total or item.amount for item in extraction.line_items if (item.total or item.amount) is not None]
    subtotal = field_map.get("subtotal")
    total_amount = field_map.get("total")
    
    check_name_b = "Sum of Line Items ≈ Subtotal"
    formula_b = "sum(line_totals) ≈ subtotal"
    operands_b = {"sum_line_items": sum(line_totals) if line_totals else None, "subtotal": subtotal}
    
    if line_totals and subtotal is not None:
        calc_subtotal = float(sum(Decimal(str(v)) for v in line_totals))
        variance_b = abs(calc_subtotal - subtotal)
        status_b = "PASS" if variance_b <= abs_tol else "FAIL"
        checks.append(ValidationCheck(
            check_name=check_name_b,
            formula=formula_b,
            operands=operands_b,
            calculated_value=calc_subtotal,
            reported_value=subtotal,
            variance=variance_b,
            tolerance=abs_tol,
            status=status_b
        ))
    else:
        checks.append(ValidationCheck(
            check_name=check_name_b,
            formula=formula_b,
            operands=operands_b,
            tolerance=abs_tol,
            status="NOT_APPLICABLE",
            details="Missing line totals or subtotal field."
        ))

    # Check C: Subtotal + Tax = Total
    tax = field_map.get("tax")
    check_name_c = "Subtotal + Tax ≈ Total"
    formula_c = "subtotal + tax ≈ total"
    operands_c = {"subtotal": subtotal, "tax": tax, "total": total_amount}
    
    if subtotal is not None and tax is not None and total_amount is not None:
        calc_total = float(Decimal(str(subtotal)) + Decimal(str(tax)))
        variance_c = abs(calc_total - total_amount)
        status_c = "PASS" if variance_c <= abs_tol else "FAIL"
        checks.append(ValidationCheck(
            check_name=check_name_c,
            formula=formula_c,
            operands=operands_c,
            calculated_value=calc_total,
            reported_value=total_amount,
            variance=variance_c,
            tolerance=abs_tol,
            status=status_c
        ))
    else:
        checks.append(ValidationCheck(
            check_name=check_name_c,
            formula=formula_c,
            operands=operands_c,
            tolerance=abs_tol,
            status="NOT_APPLICABLE",
            details="Missing subtotal, tax, or total."
        ))

    # Check D: Total - Amount Paid = Amount Due
    amount_paid = field_map.get("amount_paid")
    amount_due = field_map.get("amount_due")
    check_name_d = "Total - Amount Paid ≈ Amount Due"
    formula_d = "total - amount_paid ≈ amount_due"
    operands_d = {"total": total_amount, "amount_paid": amount_paid, "amount_due": amount_due}
    
    if total_amount is not None and amount_paid is not None and amount_due is not None:
        calc_due = float(Decimal(str(total_amount)) - Decimal(str(amount_paid)))
        variance_d = abs(calc_due - amount_due)
        status_d = "PASS" if variance_d <= abs_tol else "FAIL"
        checks.append(ValidationCheck(
            check_name=check_name_d,
            formula=formula_d,
            operands=operands_d,
            calculated_value=calc_due,
            reported_value=amount_due,
            variance=variance_d,
            tolerance=abs_tol,
            status=status_d
        ))
    else:
        checks.append(ValidationCheck(
            check_name=check_name_d,
            formula=formula_d,
            operands=operands_d,
            tolerance=abs_tol,
            status="NOT_APPLICABLE",
            details="Missing amount_paid or amount_due."
        ))

    return checks
