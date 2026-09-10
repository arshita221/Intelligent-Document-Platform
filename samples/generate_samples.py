import os
import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFont

SAMPLES_DIR = os.path.dirname(os.path.abspath(__file__))

def create_sample_pdf_invoice():
    doc = fitz.open()
    page = doc.new_page(width=595, height=842) # A4
    text = """
    ACME CORPORATION - INVOICE
    Invoice Number: INV-2025-8899
    Date: 2025-01-15
    Due Date: 2025-02-15
    Seller: Acme Corp, 100 Innovation Way, Tech City
    Buyer: Global Logistics Inc, 500 Freight Road
    Currency: USD

    LINE ITEMS:
    ---------------------------------------------------------
    Description                  Qty    Unit Price    Total
    1. Cloud Server Infrastructure  5.0    $100.00       $500.00
    2. API Gateway Services        10.0    $50.00        $500.00
    3. Enterprise Support Package   1.0    $500.00       $500.00

    ---------------------------------------------------------
    Subtotal:                   $1,500.00
    Tax (10% GST):              $150.00
    Total Amount:               $1,650.00
    Amount Paid:                $1,650.00
    Amount Due:                 $0.00
    """
    page.insert_text((50, 50), text, fontsize=12)
    pdf_path = os.path.join(SAMPLES_DIR, "sample_invoice.pdf")
    doc.save(pdf_path)
    doc.close()
    print(f"Generated {pdf_path}")

def create_sample_pdf_balance_sheet():
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    text = """
    NEXUS TECH SOLUTIONS - BALANCE SHEET
    As of December 31, 2024 (Amount in USD)

    PERIOD: 2024

    ASSETS:
    Current Assets:               $500,000
    Non-Current Assets:           $300,000
    ----------------------------------------
    Total Assets:                 $800,000

    CAPITAL & LIABILITIES:
    Capital / Shareholder Equity:  $500,000
    Current Liabilities:          $200,000
    Non-Current Liabilities:      $100,000
    ----------------------------------------
    Total Liabilities:            $300,000
    Total Capital & Liabilities:  $800,000
    """
    page.insert_text((50, 50), text, fontsize=12)
    pdf_path = os.path.join(SAMPLES_DIR, "sample_balance_sheet.pdf")
    doc.save(pdf_path)
    doc.close()
    print(f"Generated {pdf_path}")

def create_sample_pdf_profit_loss():
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    text = """
    DELTA GLOBAL LTD - PROFIT & LOSS STATEMENT
    For the Financial Year Ended March 31, 2024

    PERIOD: 2024

    INCOME:
    Revenue / Sales:              $100,000
    Other Income:                 $20,000
    ----------------------------------------
    Total Income:                 $120,000

    EXPENDITURE:
    Operating Expenses:           $70,000
    Provisions & Contingencies:   $10,000
    ----------------------------------------
    Total Expenditure:            $80,000

    NET PROFIT:
    Profit Before Tax:            $40,000
    Tax Expense:                  $10,000
    Net Profit After Tax:         $30,000
    """
    page.insert_text((50, 50), text, fontsize=12)
    pdf_path = os.path.join(SAMPLES_DIR, "sample_profit_loss.pdf")
    doc.save(pdf_path)
    doc.close()
    print(f"Generated {pdf_path}")

def create_sample_pdf_cash_flow():
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    text = """
    HORIZON VENTURES - STATEMENT OF CASH FLOWS
    For Year Ended December 31, 2024

    PERIOD: 2024

    CASH FLOW FROM ACTIVITIES:
    Operating Cash Flow:                       $50,000
    Investing Cash Flow (Equipment Purchase):  (20,000)
    Financing Cash Flow (Debt Repayment):      (10,000)
    Foreign Exchange Effect:                    $0
    ---------------------------------------------------
    Net Increase in Cash:                      $20,000

    CASH RECONCILIATION:
    Opening Cash Balance:                      $15,000
    Net Increase:                              $20,000
    Adjustments:                                $0
    ---------------------------------------------------
    Closing Cash Balance:                      $35,000
    """
    page.insert_text((50, 50), text, fontsize=12)
    pdf_path = os.path.join(SAMPLES_DIR, "sample_cash_flow.pdf")
    doc.save(pdf_path)
    doc.close()
    print(f"Generated {pdf_path}")

if __name__ == "__main__":
    create_sample_pdf_invoice()
    create_sample_pdf_balance_sheet()
    create_sample_pdf_profit_loss()
    create_sample_pdf_cash_flow()
