from app.validation.invoice import validate_invoice
from app.schemas.extraction import DocumentExtraction, ExtractedField, LineItem

def test_invoice_validation_passing(mock_invoice_passing):
    checks = validate_invoice(mock_invoice_passing)
    
    assert len(checks) >= 4
    # All checks should pass
    passed = [c for c in checks if c.status == "PASS"]
    failed = [c for c in checks if c.status == "FAIL"]
    
    assert len(failed) == 0
    assert len(passed) >= 3

def test_invoice_validation_failing(mock_invoice_failing):
    checks = validate_invoice(mock_invoice_failing)
    
    failed = [c for c in checks if c.status == "FAIL"]
    assert len(failed) >= 2 # Line total mismatch & subtotal+tax mismatch

def test_invoice_validation_tax_free_invoice():
    # Tax-free invoice: subtotal = 150.0, tax = None, total = 150.0
    doc = DocumentExtraction(
        document_type="invoice",
        fields=[
            ExtractedField(name="subtotal", value="150.00", normalized_value=150.0),
            ExtractedField(name="total", value="150.00", normalized_value=150.0)
        ],
        line_items=[
            LineItem(description="Consulting Service", quantity=1.0, unit_price=150.0, amount=150.0, total=150.0)
        ]
    )
    checks = validate_invoice(doc)
    
    passed = [c for c in checks if c.status == "PASS"]
    failed = [c for c in checks if c.status == "FAIL"]
    
    assert len(failed) == 0
    assert any(c.check_name == "Subtotal + Tax ≈ Total" and c.status == "PASS" for c in checks)
    assert any(c.check_name == "Sum of Line Items ≈ Subtotal" and c.status == "PASS" for c in checks)

def test_invoice_validation_multiple_line_items():
    # Multi line item invoice
    doc = DocumentExtraction(
        document_type="invoice",
        fields=[
            ExtractedField(name="subtotal", value="300.00", normalized_value=300.0),
            ExtractedField(name="tax", value="30.00", normalized_value=30.0),
            ExtractedField(name="total", value="330.00", normalized_value=330.0),
            ExtractedField(name="amount_paid", value="330.00", normalized_value=330.0),
            ExtractedField(name="amount_due", value="0.00", normalized_value=0.0)
        ],
        line_items=[
            LineItem(description="Item A", quantity=2.0, unit_price=50.0, amount=100.0, total=100.0),
            LineItem(description="Item B", quantity=4.0, unit_price=25.0, amount=100.0, total=100.0),
            LineItem(description="Item C", quantity=1.0, unit_price=100.0, amount=100.0, total=100.0)
        ]
    )
    checks = validate_invoice(doc)
    
    passed = [c for c in checks if c.status == "PASS"]
    failed = [c for c in checks if c.status == "FAIL"]
    
    assert len(failed) == 0
    assert len(passed) == 6  # 3 line item checks + 3 summary checks

def test_invoice_normalization_and_canonical_mapping():
    from app.services.groq_service import normalize_extraction_json
    
    # Raw JSON output from LLM using varying column key aliases
    raw_llm_data = {
        "document_type": "invoice",
        "fields": [
            {"name": "Invoice No", "value": "INV/2025/99"},
            {"name": "sub_total", "value": "200.00"},
            {"name": "tax_amount", "value": "20.00"},
            {"name": "grand_total", "value": "220.00"}
        ],
        "line_items": [
            {"item": "Widget X", "qty": "2", "rate": "50.00", "val": "100.00"},
            {"item": "Widget Y", "qty": "1", "rate": "100.00", "val": "100.00"}
        ]
    }
    
    extraction = normalize_extraction_json(raw_llm_data, "invoice", [])
    
    # Verify line items normalized
    assert len(extraction.line_items) == 2
    assert extraction.line_items[0].description == "Widget X"
    assert extraction.line_items[0].quantity == 2.0
    assert extraction.line_items[0].unit_price == 50.0
    assert extraction.line_items[0].total == 100.0
    
    # Verify canonical field promotion
    field_names = [f.name for f in extraction.fields]
    assert "subtotal" in field_names
    assert "tax" in field_names
    assert "total" in field_names
    
    # Verify invoice validation succeeds
    checks = validate_invoice(extraction)
    failed = [c for c in checks if c.status == "FAIL"]
    assert len(failed) == 0

def test_invoice_missing_values_remain_null():
    from app.services.groq_service import normalize_extraction_json
    
    raw_llm_data = {
        "document_type": "invoice",
        "fields": [
            {"name": "invoice_no", "value": "INV-123"},
            {"name": "subtotal", "value": None},
            {"name": "tax", "value": None},
            {"name": "total", "value": "100.00"}
        ],
        "line_items": [
            {"description": "Unknown Item", "quantity": None, "unit_price": None, "total": 100.00}
        ]
    }
    
    extraction = normalize_extraction_json(raw_llm_data, "invoice", [])
    
    # Check null preservation
    assert extraction.line_items[0].quantity is None
    assert extraction.line_items[0].unit_price is None
    
    subtotal_f = next(f for f in extraction.fields if f.name == "subtotal")
    assert subtotal_f.value is None
    assert subtotal_f.normalized_value is None
    
    checks = validate_invoice(extraction)
    na_checks = [c for c in checks if c.status == "NOT_APPLICABLE"]
    assert len(na_checks) >= 2

def test_label_aware_field_disambiguation():
    from app.services.groq_service import normalize_extraction_json
    
    # Raw JSON mimicking LLM misassignments based on proximity
    raw_llm_data = {
        "document_type": "invoice",
        "fields": [
            {
                "name": "buyer_name",
                "value": "SUJIT(9007785327)",
                "evidence": "Sales Man SUJIT(9007785327)"
            },
            {
                "name": "buyer_address",
                "value": "Area LOHAPPOOL",
                "evidence": "Market Area LOHAPPOOL"
            },
            {
                "name": "customer_party",
                "value": "Laxmi Narayan Bhandar 2",
                "evidence": "Buyer's Name Laxmi Narayan Bhandar 2"
            },
            {
                "name": "street_location",
                "value": "123 Market St",
                "evidence": "Buyer's Address 123 Market St"
            }
        ]
    }
    
    extraction = normalize_extraction_json(raw_llm_data, "invoice", [])
    
    field_dict = {f.name: f for f in extraction.fields}
    
    # Verify Sales Man was remapped to sales_person and non-monetary guarded
    assert "sales_person" in field_dict
    assert field_dict["sales_person"].value == "SUJIT(9007785327)"
    assert field_dict["sales_person"].normalized_value is None
    
    # Verify Market Area was remapped to market and non-monetary guarded
    assert "market" in field_dict
    assert field_dict["market"].value == "Area LOHAPPOOL"
    assert field_dict["market"].normalized_value is None
    
    # Verify Buyer Name was mapped correctly from evidence label
    assert "buyer_name" in field_dict
    assert field_dict["buyer_name"].value == "Laxmi Narayan Bhandar 2"
    
    # Verify Buyer Address was mapped correctly from evidence label
    assert "buyer_address" in field_dict
    assert field_dict["buyer_address"].value == "123 Market St"

def test_flexible_line_item_extraction_and_additional_fields():
    from app.services.groq_service import normalize_extraction_json
    
    raw_llm_data = {
        "document_type": "invoice",
        "fields": [
            {"name": "invoice_no", "value": "SCI/25-26/13331", "evidence": "Invoice No: SCI/25-26/13331"},
            {"name": "date", "value": "16-Jul-25", "evidence": "Dated: 16-Jul-25"},
            {"name": "mode_of_payment", "value": "Cash", "evidence": "Mode of Payment: Cash"},
            {"name": "reference_no", "value": "19", "evidence": "Ref No: 19"}
        ],
        "line_items": [
            {
                "goods": "Item Alpha",
                "qnt": "5",
                "rate": "100.00",
                "taxable_amount": "500.00",
                "disc": "10.00",
                "gst": "45.00",
                "net_amount": "535.00",
                "evidence": "Item Alpha | Qty 5 | Rate 100.00 | Disc 10.00 | Net 535.00",
                "page_number": 1
            }
        ]
    }
    
    extraction = normalize_extraction_json(raw_llm_data, "invoice", [])
    
    # Check flexible line item mapping
    assert len(extraction.line_items) == 1
    li = extraction.line_items[0]
    assert li.description == "Item Alpha"
    assert li.quantity == 5.0
    assert li.unit_price == 100.0
    assert li.amount == 500.0
    assert li.discount == 10.0
    assert li.tax == 45.0
    assert li.total == 535.0
    assert li.evidence == "Item Alpha | Qty 5 | Rate 100.00 | Disc 10.00 | Net 535.00"
    
    # Check non-monetary protections
    inv_f = next(f for f in extraction.fields if f.name == "invoice_no")
    assert inv_f.normalized_value is None
    date_f = next(f for f in extraction.fields if f.name == "date")
    assert date_f.normalized_value is None
    
    # Check preservation of additional fields
    f_names = [f.name for f in extraction.fields]
    assert "mode_of_payment" in f_names
    assert "reference_no" in f_names

def test_deterministic_subtotal_tax_validation_failure():
    # Test case from live invoice where 5815.17 + 523.36 != 6362.00
    doc = DocumentExtraction(
        document_type="invoice",
        fields=[
            ExtractedField(name="subtotal", value="5815.17", normalized_value=5815.17),
            ExtractedField(name="tax", value="523.36", normalized_value=523.36),
            ExtractedField(name="total", value="6362.00", normalized_value=6362.00)
        ],
        line_items=[]
    )
    
    checks = validate_invoice(doc)
    subtotal_tax_check = next(c for c in checks if c.check_name == "Subtotal + Tax ≈ Total")
    
    assert subtotal_tax_check.status == "FAIL"
    assert round(subtotal_tax_check.calculated_value, 2) == 6338.53
    assert subtotal_tax_check.reported_value == 6362.00

def test_line_items_alternate_keys_recovery():
    from app.services.groq_service import normalize_extraction_json
    
    # LLM returned line items under alternate key 'products'
    raw_llm_data = {
        "document_type": "invoice",
        "fields": [],
        "products": [
            {
                "product_name": "Industrial Bearing X",
                "pcs": "10",
                "rate": "250.00",
                "taxable_val": "2500.00",
                "gst": "450.00",
                "net_amount": "2950.00",
                "evidence": "Bearing X | Qty 10 | Rate 250.00 | Total 2950.00",
                "page_number": 1
            }
        ]
    }
    
    extraction = normalize_extraction_json(raw_llm_data, "invoice", [])
    
    assert len(extraction.line_items) == 1
    li = extraction.line_items[0]
    assert li.description == "Industrial Bearing X"
    assert li.quantity == 10.0
    assert li.unit_price == 250.0
    assert li.taxable_amount == 2500.0
    assert li.tax == 450.0
    assert li.total == 2950.0
    assert li.evidence == "Bearing X | Qty 10 | Rate 250.00 | Total 2950.00"

def test_generic_table_to_line_items_conversion():
    from app.services.groq_service import normalize_extraction_json
    
    # LLM returned generic tables array but empty line_items
    raw_llm_data = {
        "document_type": "invoice",
        "fields": [],
        "line_items": [],
        "tables": [
            {
                "name": "Invoice Items Table",
                "headers": ["Sr No", "Particulars", "HSN/SAC", "Qty", "Rate", "Taxable Value", "CGST", "SGST", "Total"],
                "rows": [
                    ["1", "Hydraulic Hose Assembly", "8481", "2", "1500.00", "3000.00", "270.00", "270.00", "3540.00"]
                ],
                "page_number": 1,
                "evidence": "1 Hydraulic Hose Assembly 8481 2 1500.00 3000.00 270.00 270.00 3540.00"
            }
        ]
    }
    
    extraction = normalize_extraction_json(raw_llm_data, "invoice", [])
    
    assert len(extraction.line_items) == 1
    li = extraction.line_items[0]
    assert li.description == "Hydraulic Hose Assembly"
    assert li.quantity == 2.0
    assert li.unit_price == 1500.0
    assert li.taxable_amount == 3000.0
    assert li.total == 3540.0
    assert li.raw_data is not None
    assert li.evidence == "1 Hydraulic Hose Assembly 8481 2 1500.00 3000.00 270.00 270.00 3540.00"

def test_line_items_unknown_columns_and_null_preservation():
    from app.services.groq_service import normalize_extraction_json
    
    # Row with custom/unknown columns and missing optional fields
    raw_llm_data = {
        "document_type": "invoice",
        "fields": [],
        "line_items": [
            {
                "item_description": "Custom Cable Harness",
                "quantity": None,
                "unit_price": None,
                "batch_code": "BATCH-2025-A",
                "hsn_code": "8544",
                "amount": "1200.00",
                "evidence": "Custom Cable Harness Batch-2025-A Amount 1200.00",
                "page_number": 2
            }
        ]
    }
    
    extraction = normalize_extraction_json(raw_llm_data, "invoice", [])
    
    assert len(extraction.line_items) == 1
    li = extraction.line_items[0]
    assert li.description == "Custom Cable Harness"
    assert li.quantity is None
    assert li.unit_price is None
    assert li.amount == 1200.0
    assert li.total == 1200.0
    assert li.raw_data == {"batch_code": "BATCH-2025-A", "hsn_code": "8544"}
    assert li.evidence == "Custom Cable Harness Batch-2025-A Amount 1200.00"
    assert li.page_number == 2

