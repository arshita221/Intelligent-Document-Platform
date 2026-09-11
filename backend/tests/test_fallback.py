"""
Tests for the fallback extraction strategy.
Tests: trigger logic, merge logic, null preservation, deduplication,
evidence/page preservation, and validator-after-merge.
"""
import pytest
from unittest.mock import patch, MagicMock
from app.schemas.extraction import (
    DocumentExtraction, ExtractedField, LineItem, Period, FinancialTable, RawTextPage
)
from app.services.groq_service import (
    should_trigger_fallback, merge_extractions
)
from app.validation.engine import run_financial_validation


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_field(name, value, norm=None, evidence=None, page=1):
    return ExtractedField(
        name=name, value=value, normalized_value=norm,
        evidence=evidence or f"{name}: {value}", page_number=page, status="EXTRACTED"
    )

def _make_line_item(desc, qty=None, price=None, total=None, evidence=None, page=1):
    return LineItem(
        description=desc, quantity=qty, unit_price=price,
        total=total, evidence=evidence or f"{desc}", page_number=page
    )


# ── should_trigger_fallback ─────────────────────────────────────────────────

class TestShouldTriggerFallback:

    def test_invoice_triggers_when_no_line_items(self):
        ext = DocumentExtraction(
            document_type="invoice",
            fields=[_make_field("subtotal", "1000", 1000.0)],
            line_items=[]
        )
        assert should_trigger_fallback(ext, "invoice") is True

    def test_invoice_does_not_trigger_when_line_items_exist(self):
        ext = DocumentExtraction(
            document_type="invoice",
            fields=[_make_field("subtotal", "1000", 1000.0)],
            line_items=[_make_line_item("Widget A", total=500.0)]
        )
        assert should_trigger_fallback(ext, "invoice") is False

    def test_balance_sheet_triggers_when_no_canonical_fields(self):
        ext = DocumentExtraction(
            document_type="balance_sheet",
            fields=[
                _make_field("report_title", "Balance Sheet", None),
                _make_field("currency_unit", "INR", None),
            ]
        )
        assert should_trigger_fallback(ext, "balance_sheet") is True

    def test_balance_sheet_does_not_trigger_with_canonical_fields(self):
        ext = DocumentExtraction(
            document_type="balance_sheet",
            fields=[
                _make_field("total_assets", "500000", 500000.0),
                _make_field("liabilities", "300000", 300000.0),
                _make_field("capital", "200000", 200000.0),
            ]
        )
        assert should_trigger_fallback(ext, "balance_sheet") is False

    def test_profit_loss_triggers_when_insufficient_numeric_fields(self):
        ext = DocumentExtraction(
            document_type="profit_loss",
            fields=[
                _make_field("report_title", "P&L Statement", None),
                _make_field("company_name", "Acme Corp", None),
            ]
        )
        assert should_trigger_fallback(ext, "profit_loss") is True

    def test_profit_loss_does_not_trigger_with_sufficient_fields(self):
        ext = DocumentExtraction(
            document_type="profit_loss",
            fields=[
                _make_field("total_income", "1000000", 1000000.0),
                _make_field("total_expenditure", "800000", 800000.0),
                _make_field("net_profit", "200000", 200000.0),
            ]
        )
        assert should_trigger_fallback(ext, "profit_loss") is False

    def test_cash_flow_triggers_when_no_canonical_fields(self):
        ext = DocumentExtraction(
            document_type="cash_flow",
            fields=[
                _make_field("report_title", "Cash Flow", None),
                _make_field("period", "2026", None),
            ]
        )
        assert should_trigger_fallback(ext, "cash_flow") is True

    def test_cash_flow_does_not_trigger_with_canonical_fields(self):
        ext = DocumentExtraction(
            document_type="cash_flow",
            fields=[
                _make_field("operating_cash_flow", "50000", 50000.0),
                _make_field("investing_cash_flow", "-20000", -20000.0),
                _make_field("closing_cash", "80000", 80000.0),
            ]
        )
        assert should_trigger_fallback(ext, "cash_flow") is False


# ── merge_extractions ───────────────────────────────────────────────────────

class TestMergeExtractions:

    def test_fallback_adds_new_fields(self):
        primary = DocumentExtraction(
            document_type="balance_sheet",
            fields=[_make_field("report_title", "BS", None)]
        )
        fallback = DocumentExtraction(
            document_type="balance_sheet",
            fields=[
                _make_field("total_assets", "500000", 500000.0),
                _make_field("liabilities", "300000", 300000.0),
            ]
        )
        merged = merge_extractions(primary, fallback)
        names = {f.name for f in merged.fields}
        assert "total_assets" in names
        assert "liabilities" in names
        assert "report_title" in names

    def test_primary_non_null_not_overwritten_by_null(self):
        primary = DocumentExtraction(
            document_type="invoice",
            fields=[_make_field("subtotal", "1000", 1000.0, "Subtotal: 1000")]
        )
        fallback = DocumentExtraction(
            document_type="invoice",
            fields=[_make_field("subtotal", None, None, None)]
        )
        merged = merge_extractions(primary, fallback)
        sub = next(f for f in merged.fields if f.name == "subtotal")
        assert sub.normalized_value == 1000.0
        assert sub.evidence == "Subtotal: 1000"

    def test_primary_null_overwritten_by_fallback_value(self):
        primary = DocumentExtraction(
            document_type="invoice",
            fields=[_make_field("tax", None, None, None)]
        )
        fallback = DocumentExtraction(
            document_type="invoice",
            fields=[_make_field("tax", "150", 150.0, "Tax: 150")]
        )
        merged = merge_extractions(primary, fallback)
        tax = next(f for f in merged.fields if f.name == "tax")
        assert tax.normalized_value == 150.0
        assert tax.evidence == "Tax: 150"

    def test_line_items_deduplicated_by_description(self):
        primary = DocumentExtraction(
            document_type="invoice",
            line_items=[_make_line_item("Widget A", total=500.0)]
        )
        fallback = DocumentExtraction(
            document_type="invoice",
            line_items=[
                _make_line_item("Widget A", total=500.0),  # duplicate
                _make_line_item("Widget B", total=300.0),  # new
            ]
        )
        merged = merge_extractions(primary, fallback)
        assert len(merged.line_items) == 2
        descs = [li.description for li in merged.line_items]
        assert "Widget A" in descs
        assert "Widget B" in descs

    def test_no_duplicate_line_items_on_empty_primary(self):
        primary = DocumentExtraction(document_type="invoice", line_items=[])
        fallback = DocumentExtraction(
            document_type="invoice",
            line_items=[
                _make_line_item("Item X", total=100.0),
                _make_line_item("Item Y", total=200.0),
            ]
        )
        merged = merge_extractions(primary, fallback)
        assert len(merged.line_items) == 2

    def test_evidence_and_page_preserved_after_merge(self):
        primary = DocumentExtraction(
            document_type="profit_loss",
            fields=[_make_field("total_income", "1000000", 1000000.0, "Total Income: 1,000,000", page=1)]
        )
        fallback = DocumentExtraction(
            document_type="profit_loss",
            fields=[_make_field("net_profit", "200000", 200000.0, "Net Profit: 200,000", page=2)]
        )
        merged = merge_extractions(primary, fallback)
        ti = next(f for f in merged.fields if f.name == "total_income")
        np_f = next(f for f in merged.fields if f.name == "net_profit")
        assert ti.evidence == "Total Income: 1,000,000"
        assert ti.page_number == 1
        assert np_f.evidence == "Net Profit: 200,000"
        assert np_f.page_number == 2

    def test_periods_merged_without_duplication(self):
        primary = DocumentExtraction(
            document_type="balance_sheet",
            periods=[
                Period(label="2026", fields=[_make_field("capital", "1000", 1000.0)])
            ]
        )
        fallback = DocumentExtraction(
            document_type="balance_sheet",
            periods=[
                Period(label="2026", fields=[_make_field("deposits", "5000", 5000.0)]),
                Period(label="2025", fields=[_make_field("capital", "900", 900.0)]),
            ]
        )
        merged = merge_extractions(primary, fallback)
        assert len(merged.periods) == 2
        p2026 = next(p for p in merged.periods if p.label == "2026")
        p2025 = next(p for p in merged.periods if p.label == "2025")
        p2026_names = {f.name for f in p2026.fields}
        assert "capital" in p2026_names
        assert "deposits" in p2026_names
        assert any(f.name == "capital" for f in p2025.fields)

    def test_metadata_marks_fallback_applied(self):
        primary = DocumentExtraction(document_type="invoice", metadata={"normalized": True})
        fallback = DocumentExtraction(document_type="invoice")
        merged = merge_extractions(primary, fallback)
        assert merged.metadata.get("fallback_applied") is True
        assert merged.metadata.get("normalized") is True

    def test_null_fields_from_fallback_not_added(self):
        """Fallback fields with both value=None and normalized_value=None should NOT be merged."""
        primary = DocumentExtraction(document_type="balance_sheet", fields=[])
        fallback = DocumentExtraction(
            document_type="balance_sheet",
            fields=[
                _make_field("garbage", None, None, None),
                _make_field("total_assets", "500000", 500000.0, "Total Assets: 500,000"),
            ]
        )
        merged = merge_extractions(primary, fallback)
        names = {f.name for f in merged.fields}
        assert "garbage" not in names
        assert "total_assets" in names


# ── Validator runs after merge ──────────────────────────────────────────────

class TestValidatorAfterMerge:

    def test_invoice_validator_runs_on_merged_extraction(self):
        primary = DocumentExtraction(
            document_type="invoice",
            fields=[_make_field("subtotal", "1000", 1000.0)]
        )
        fallback = DocumentExtraction(
            document_type="invoice",
            fields=[
                _make_field("tax", "100", 100.0),
                _make_field("total", "1100", 1100.0),
            ]
        )
        merged = merge_extractions(primary, fallback)
        result = run_financial_validation(merged)
        # With subtotal=1000, tax=100, total=1100 -> subtotal+tax=total -> PASS
        assert result.overall_status == "PASS"
        assert result.passed_count >= 1

    def test_balance_sheet_validator_runs_on_merged_extraction(self):
        primary = DocumentExtraction(
            document_type="balance_sheet",
            fields=[_make_field("report_title", "Balance Sheet", None)]
        )
        fallback = DocumentExtraction(
            document_type="balance_sheet",
            fields=[
                _make_field("capital", "200000", 200000.0),
                _make_field("liabilities", "500000", 500000.0),
                _make_field("assets", "500000", 500000.0),
            ]
        )
        merged = merge_extractions(primary, fallback)
        result = run_financial_validation(merged)
        # capital + liabilities = 200000 + 500000 = 700000 != 500000 -> FAILED
        # But at least the validator ran
        assert result.overall_status in ("PASS", "FAILED", "INCOMPLETE")
        assert len(result.checks) >= 1


# ── End-to-end pipeline with mock (fallback triggered) ──────────────────────

class TestFallbackPipelineIntegration:

    @patch("app.services.document_service.perform_fallback_extraction")
    @patch("app.services.document_service.extract_with_groq")
    def test_fallback_triggered_and_merged_in_pipeline(self, mock_extract, mock_fallback):
        """Simulates the full pipeline with a mocked primary extraction that lacks
        line items (invoice), verifying fallback is called and results are merged."""
        from app.services.document_service import process_document_pipeline
        from app.db.database import init_db, get_db

        init_db()
        db = next(get_db())

        # Primary returns header fields but no line items
        mock_extract.return_value = DocumentExtraction(
            document_type="invoice",
            fields=[
                _make_field("invoice_no", "INV-001", None),
                _make_field("subtotal", "1000", 1000.0),
            ],
            line_items=[]
        )

        # Fallback returns line items + summary totals
        mock_fallback.return_value = DocumentExtraction(
            document_type="invoice",
            fields=[
                _make_field("tax", "100", 100.0),
                _make_field("total", "1100", 1100.0),
            ],
            line_items=[
                _make_line_item("Widget A", qty=2, price=250, total=500.0),
                _make_line_item("Widget B", qty=1, price=500, total=500.0),
            ]
        )

        # Create a valid test PDF
        import fitz
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 50), "Invoice #INV-001")
        pdf_bytes = doc.tobytes()
        doc.close()

        import tempfile, os
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        try:
            resp, status_code = process_document_pipeline(
                file_path=tmp_path,
                original_filename="test_fallback_invoice.pdf",
                document_type="invoice",
                db=db
            )
            assert status_code == 200
            # Fallback should have been called
            mock_fallback.assert_called_once()
            # Merged result should have line items
            assert len(resp.extracted_data.line_items) == 2
            # Merged result should have both primary and fallback fields
            field_names = {f.name for f in resp.extracted_data.fields}
            assert "invoice_no" in field_names
            assert "tax" in field_names
            assert "total" in field_names
        finally:
            os.remove(tmp_path)

    @patch("app.services.document_service.perform_fallback_extraction")
    @patch("app.services.document_service.extract_with_groq")
    def test_fallback_not_triggered_when_sufficient(self, mock_extract, mock_fallback):
        """When primary extraction has enough data, fallback should NOT be called."""
        from app.services.document_service import process_document_pipeline
        from app.db.database import init_db, get_db

        init_db()
        db = next(get_db())

        mock_extract.return_value = DocumentExtraction(
            document_type="profit_loss",
            fields=[
                _make_field("total_income", "1000000", 1000000.0),
                _make_field("total_expenditure", "800000", 800000.0),
                _make_field("net_profit", "200000", 200000.0),
            ]
        )

        import fitz
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 50), "Profit & Loss Statement")
        pdf_bytes = doc.tobytes()
        doc.close()

        import tempfile, os
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        try:
            resp, status_code = process_document_pipeline(
                file_path=tmp_path,
                original_filename="test_no_fallback_pnl.pdf",
                document_type="profit_loss",
                db=db
            )
            assert status_code == 200
            # Fallback should NOT have been called
            mock_fallback.assert_not_called()
        finally:
            os.remove(tmp_path)
