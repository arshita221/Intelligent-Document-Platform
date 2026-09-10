import fitz  # PyMuPDF
import io
from PIL import Image
from typing import List, Tuple, Dict, Any
from app.schemas.extraction import RawTextPage

def process_pdf_document(file_path: str) -> Tuple[List[RawTextPage], List[bytes], bool]:
    """
    Processes a PDF file using PyMuPDF.
    Returns:
    - raw_text_pages: List of RawTextPage containing page index and native text.
    - page_images: List of page image bytes (PNG format).
    - is_scanned: True if native text is absent/minimal across pages.
    """
    doc = fitz.open(file_path)
    raw_text_pages: List[RawTextPage] = []
    page_images: List[bytes] = []
    
    total_char_count = 0
    page_count = len(doc)
    
    for idx in range(page_count):
        page = doc[idx]
        text = page.get_text("text") or ""
        total_char_count += len(text.strip())
        raw_text_pages.append(RawTextPage(page_number=idx + 1, text=text))
        
        # Render page to PNG image (dpi=200 for OCR quality)
        pix = page.get_pixmap(dpi=200)
        img_bytes = pix.tobytes("png")
        page_images.append(img_bytes)
        
    doc.close()
    
    # If total characters across pages is under 50, treat as scanned document
    is_scanned = (total_char_count < 50)
    
    return raw_text_pages, page_images, is_scanned
