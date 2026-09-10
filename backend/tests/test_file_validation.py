import os
import tempfile
import pytest
import fitz  # PyMuPDF
from PIL import Image
from app.utils.file_validation import validate_uploaded_file

def test_file_validation_valid_pdf():
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name
        tmp.close()

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Invoice #101 Total: $500")
    doc.save(tmp_path)
    doc.close()

    try:
        res = validate_uploaded_file(tmp_path, "sample_invoice.pdf")
        assert res.is_valid is True
        assert res.file_exists is True
        assert res.is_not_empty is True
        assert res.supported_extension is True
        assert res.signature_valid is True
        assert res.page_count == 1
        assert res.page_count_valid is True
        assert res.decodable is True
        assert len(res.errors) == 0
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def test_file_validation_pdf_too_many_pages():
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name
        tmp.close()

    doc = fitz.open()
    for i in range(4): # 4 pages > 3 allowed
        page = doc.new_page()
        page.insert_text((50, 50), f"Page {i+1}")
    doc.save(tmp_path)
    doc.close()

    try:
        res = validate_uploaded_file(tmp_path, "long_doc.pdf")
        assert res.is_valid is False
        assert res.page_count == 4
        assert res.page_count_valid is False
        assert any("Maximum allowed length is 3 pages" in err for err in res.errors)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def test_file_validation_valid_image_png():
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name
        tmp.close()

    img = Image.new("RGB", (200, 200), color="white")
    img.save(tmp_path, format="PNG")

    try:
        res = validate_uploaded_file(tmp_path, "receipt.png")
        assert res.is_valid is True
        assert res.detected_mime == "image/png"
        assert res.page_count == 1
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def test_file_validation_empty_file():
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name # 0 bytes

    try:
        res = validate_uploaded_file(tmp_path, "empty.pdf")
        assert res.is_valid is False
        assert res.is_not_empty is False
        assert any("empty" in err for err in res.errors)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def test_file_validation_unsupported_extension():
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
        tmp.write(b"Hello world")
        tmp_path = tmp.name

    try:
        res = validate_uploaded_file(tmp_path, "notes.txt")
        assert res.is_valid is False
        assert res.supported_extension is False
        assert any("Unsupported file extension" in err for err in res.errors)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def test_file_validation_corrupt_pdf():
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(b"%PDF-1.4 Fake corrupt data header without valid objects")
        tmp_path = tmp.name

    try:
        res = validate_uploaded_file(tmp_path, "corrupt.pdf")
        assert res.is_valid is False
        assert res.decodable is False
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
