# Samples & Representative API Output Examples

This directory contains representative sample financial documents and their corresponding complete API output JSON files matching the platform's actual `DocumentResponse` Pydantic schema.

## Directory Structure

```
samples/
├── sample_invoice.pdf              # Generated 1-page sample invoice (USD)
├── sample_balance_sheet.pdf        # Generated 1-page sample balance sheet (USD)
├── sample_profit_loss.pdf          # Generated 1-page sample profit & loss statement (USD)
├── sample_cash_flow.pdf            # Generated 1-page sample statement of cash flows (USD)
├── generate_samples.py             # Script that produces the sample PDFs above
└── json/
    ├── invoice_sample.json         # Complete API output for Invoice
    ├── balance_sheet_sample.json   # Complete API output for Balance Sheet
    ├── profit_loss_sample.json     # Complete API output for Profit & Loss
    └── cash_flow_sample.json       # Complete API output for Cash Flow
```

## Representative API JSON Files (`samples/json/`)

Each file in `samples/json/` represents the full API response from `POST /api/v1/documents/process` and `GET /api/v1/documents/{document_name}`.

| Sample JSON File | Document Type | Key Financial Relationships Verified | Status |
|---|---|---|---|
| `invoice_sample.json` | Invoice | `quantity × unit_price ≈ line_total`, `subtotal + tax ≈ total`, `total - amount_paid ≈ amount_due` | `PASS` |
| `balance_sheet_sample.json` | Balance Sheet | `total_assets ≈ total_liabilities + equity`, `current_assets + non_current_assets ≈ total_assets`, `current_liabilities + non_current_liabilities ≈ total_liabilities` | `PASS` |
| `profit_loss_sample.json` | Profit & Loss | `primary_income + other_income ≈ total_income`, `operating_expenses + provisions ≈ total_expenditure`, `total_income - total_expenditure ≈ profit_before_tax` | `PASS` |
| `cash_flow_sample.json` | Cash Flow | `operating + investing + financing ≈ net_increase`, `opening_cash + net_increase ≈ closing_cash` | `PASS` |

## Schema Components Demonstrated

1. **`file_validation`**: Pre-extraction integrity checks (file existence, non-emptiness, magic bytes, MIME type, page count).
2. **`extracted_data`**: Structured extraction containing typed key-value `fields`, `line_items`, `periods`, evidence text snippets, page numbers, and raw text.
3. **`validation`**: Deterministic math validation checks showing `check_name`, `formula`, input `operands`, `calculated_value`, `reported_value`, `variance`, and `status`.
4. **`processing_metadata`**: Execution timing, model identifier (`qwen/qwen3.8-27b`), and environment details.
