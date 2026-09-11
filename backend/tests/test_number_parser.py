import pytest
from app.utils.number_parser import parse_financial_number, normalize_field_value

def test_parse_financial_number_valid_amounts():
    assert parse_financial_number("$10,000.00") == 10000.0
    assert parse_financial_number("₹ 1,23,456.78") == 123456.78
    assert parse_financial_number("(5,000)") == -5000.0
    assert parse_financial_number("-1,234.50") == -1234.50
    assert parse_financial_number("100.50 USD") == 100.50
    assert parse_financial_number("5000") == 5000.0
    assert parse_financial_number(1500) == 1500.0
    assert parse_financial_number("Nil") == 0.0
    assert parse_financial_number("Zero") == 0.0

def test_parse_financial_number_guards_non_monetary_strings():
    # Invoice numbers & slash codes
    assert parse_financial_number("SCI/25-26/13331", field_name="invoice_no") is None
    assert parse_financial_number("INV/2025/001") is None
    
    # Dates
    assert parse_financial_number("16-Jul-25", field_name="dated") is None
    assert parse_financial_number("As at March 31, 2017", field_name="report_date") is None
    assert parse_financial_number("2025-11-18") is None
    
    # Phone numbers & names
    assert parse_financial_number("SUJIT(9007785327)", field_name="salesman") is None
    assert parse_financial_number("+1-800-555-0199") is None
    
    # Non-monetary text & terms
    assert parse_financial_number("Area LOHAPPOOL", field_name="market") is None
    assert parse_financial_number("Cash", field_name="mode/terms of payment") is None
    assert parse_financial_number("Destination", field_name="dispatched through") is None
    assert parse_financial_number("Dated", field_name="buyer's order no.") is None

def test_normalize_field_value_helper():
    assert normalize_field_value("5,000", field_name="amount") == 5000.0
    assert normalize_field_value("SCI/25-26/13331", field_name="invoice_no") is None
