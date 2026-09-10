from typing import List
from app.schemas.extraction import DocumentExtraction
from app.schemas.validation import ValidationCheck, ValidationSummary
from app.validation.invoice import validate_invoice
from app.validation.balance_sheet import validate_balance_sheet
from app.validation.profit_loss import validate_profit_loss
from app.validation.cash_flow import validate_cash_flow
from app.core.logging_config import logger

def run_financial_validation(extraction: DocumentExtraction) -> ValidationSummary:
    """
    Executes document-specific deterministic financial validation.
    """
    doc_type = extraction.document_type.lower().strip()
    checks: List[ValidationCheck] = []

    logger.info(f"Running deterministic financial validation for doc_type='{doc_type}'...")

    if doc_type == "invoice":
        checks = validate_invoice(extraction)
    elif doc_type in ("balance_sheet", "balancesheet"):
        checks = validate_balance_sheet(extraction)
    elif doc_type in ("profit_loss", "profit_and_loss", "pnl"):
        checks = validate_profit_loss(extraction)
    elif doc_type in ("cash_flow", "cashflow"):
        checks = validate_cash_flow(extraction)
    else:
        logger.warning(f"Unknown document type '{doc_type}' for validation.")

    passed_count = sum(1 for c in checks if c.status == "PASS")
    failed_count = sum(1 for c in checks if c.status == "FAIL")
    na_count = sum(1 for c in checks if c.status == "NOT_APPLICABLE")

    # Financial checks overall status: FAILED only if failed_count > 0
    overall_status = "FAILED" if failed_count > 0 else "PASS"

    return ValidationSummary(
        overall_status=overall_status,
        passed_count=passed_count,
        failed_count=failed_count,
        not_applicable_count=na_count,
        checks=checks
    )
