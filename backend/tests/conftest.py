import pytest
import os
import fitz
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.database import Base
from app.schemas.extraction import DocumentExtraction, ExtractedField, LineItem, Period, RawTextPage
from app.schemas.validation import ValidationSummary

TEST_DATABASE_URL = "sqlite:///./test_financial_docs.db"

@pytest.fixture(scope="session")
def test_engine():
    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("./test_financial_docs.db"):
        os.remove("./test_financial_docs.db")

@pytest.fixture
def db_session(test_engine):
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()

# Mock Extraction Fixtures for each document type
@pytest.fixture
def mock_invoice_passing():
    return DocumentExtraction(
        document_type="invoice",
        fields=[
            ExtractedField(name="invoice_number", value="INV-2024-001", page_number=1),
            ExtractedField(name="subtotal", value="1500.00", normalized_value=1500.0, page_number=1),
            ExtractedField(name="tax", value="150.00", normalized_value=150.0, page_number=1),
            ExtractedField(name="total", value="1650.00", normalized_value=1650.0, page_number=1),
            ExtractedField(name="amount_paid", value="1650.00", normalized_value=1650.0, page_number=1),
            ExtractedField(name="amount_due", value="0.00", normalized_value=0.0, page_number=1)
        ],
        line_items=[
            LineItem(description="Web Development", quantity=10.0, unit_price=100.0, amount=1000.0, total=1000.0, page_number=1),
            LineItem(description="Cloud Hosting", quantity=5.0, unit_price=100.0, amount=500.0, total=500.0, page_number=1)
        ]
    )

@pytest.fixture
def mock_invoice_failing():
    return DocumentExtraction(
        document_type="invoice",
        fields=[
            ExtractedField(name="subtotal", value="1000.00", normalized_value=1000.0),
            ExtractedField(name="tax", value="100.00", normalized_value=100.0),
            ExtractedField(name="total", value="1500.00", normalized_value=1500.0) # 1000+100 != 1500 -> FAIL
        ],
        line_items=[
            LineItem(quantity=5.0, unit_price=100.0, total=600.0) # 5*100 != 600 -> FAIL
        ]
    )

@pytest.fixture
def mock_balance_sheet_multi_period():
    return DocumentExtraction(
        document_type="balance_sheet",
        periods=[
            Period(
                label="2024",
                fields=[
                    ExtractedField(name="capital", value="500000", normalized_value=500000.0),
                    ExtractedField(name="liabilities", value="300000", normalized_value=300000.0),
                    ExtractedField(name="assets", value="800000", normalized_value=800000.0),
                    ExtractedField(name="current_assets", value="500000", normalized_value=500000.0),
                    ExtractedField(name="non_current_assets", value="300000", normalized_value=300000.0),
                    ExtractedField(name="current_liabilities", value="200000", normalized_value=200000.0),
                    ExtractedField(name="non_current_liabilities", value="100000", normalized_value=100000.0)
                ]
            ),
            Period(
                label="2023",
                fields=[
                    ExtractedField(name="capital", value="400000", normalized_value=400000.0),
                    ExtractedField(name="liabilities", value="200000", normalized_value=200000.0),
                    ExtractedField(name="assets", value="600000", normalized_value=600000.0)
                ]
            )
        ]
    )

@pytest.fixture
def mock_profit_loss_passing():
    return DocumentExtraction(
        document_type="profit_loss",
        periods=[
            Period(
                label="2024",
                fields=[
                    ExtractedField(name="revenue", value="100000", normalized_value=100000.0),
                    ExtractedField(name="other_income", value="20000", normalized_value=20000.0),
                    ExtractedField(name="total_income", value="120000", normalized_value=120000.0),
                    ExtractedField(name="operating_expenses", value="70000", normalized_value=70000.0),
                    ExtractedField(name="provisions", value="10000", normalized_value=10000.0),
                    ExtractedField(name="total_expenditure", value="80000", normalized_value=80000.0),
                    ExtractedField(name="profit_before_tax", value="40000", normalized_value=40000.0)
                ]
            )
        ]
    )

@pytest.fixture
def mock_cash_flow_passing():
    return DocumentExtraction(
        document_type="cash_flow",
        periods=[
            Period(
                label="2024",
                fields=[
                    ExtractedField(name="operating_cash_flow", value="50000", normalized_value=50000.0),
                    ExtractedField(name="investing_cash_flow", value="(20,000)", normalized_value=-20000.0),
                    ExtractedField(name="financing_cash_flow", value="(10,000)", normalized_value=-10000.0),
                    ExtractedField(name="net_increase", value="20000", normalized_value=20000.0),
                    ExtractedField(name="opening_cash", value="15000", normalized_value=15000.0),
                    ExtractedField(name="closing_cash", value="35000", normalized_value=35000.0)
                ]
            )
        ]
    )
