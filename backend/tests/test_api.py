import io
import fitz
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app.db.database import init_db

@pytest.fixture(autouse=True)
def setup_test_db():
    init_db()

client = TestClient(app)

def test_health_check_endpoint():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert data["database"] == "healthy"

def test_list_documents_empty():
    response = client.get("/api/v1/documents")
    assert response.status_code == 200
    data = response.json()
    assert "total_count" in data
    assert "documents" in data

def test_process_invalid_doc_type():
    response = client.post(
        "/api/v1/documents/process",
        data={"document_type": "unknown_type"},
        files={"file": ("test.pdf", b"%PDF-1.4...", "application/pdf")}
    )
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data

def test_process_invalid_file_extension():
    response = client.post(
        "/api/v1/documents/process",
        data={"document_type": "invoice"},
        files={"file": ("test.txt", b"Hello text file", "text/plain")}
    )
    assert response.status_code == 400

@patch("app.services.document_service.extract_with_groq")
def test_process_document_success(mock_extract, mock_invoice_passing):
    mock_extract.return_value = mock_invoice_passing
    
    # Generate valid 1-page PDF buffer
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Invoice #INV-2024-001 Subtotal: $1500 Tax: $150 Total: $1650")
    pdf_bytes = doc.tobytes()
    doc.close()

    response = client.post(
        "/api/v1/documents/process",
        data={"document_type": "invoice"},
        files={"file": ("sample_invoice.pdf", pdf_bytes, "application/pdf")}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["processing_status"] == "PASS"
    assert data["document_type"] == "invoice"
    assert data["file_validation"]["is_valid"] is True
    assert data["file_validation"]["page_count"] == 1
    assert len(data["validation"]["checks"]) >= 3

    # Test retrieval endpoint GET /api/v1/documents/{document_name}
    doc_name = data["document_name"]
    get_res = client.get(f"/api/v1/documents/{doc_name}")
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert get_data["document_name"] == doc_name
