import os
import fitz  # PyMuPDF
from PIL import Image
from typing import Tuple, List, Dict, Any
from app.schemas.documents import FileValidationResult
from app.core.config import settings
from app.core.logging_config import logger

SUPPORTED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}

def validate_uploaded_file(file_path: str, filename: str) -> FileValidationResult:
    """
    Validates file existence, non-emptiness, magic bytes signature,
    extension, PDF validity & page count, and image decodability.
    """
    errors: List[str] = []
    
    # 1. Existence
    file_exists = os.path.exists(file_path)
    if not file_exists:
        errors.append("File does not exist on disk.")
        return FileValidationResult(
            is_valid=False, file_exists=False, is_not_empty=False,
            supported_extension=False, signature_valid=False, page_count=0,
            page_count_valid=False, decodable=False, readable=False,
            file_size_bytes=0, detected_mime="unknown", errors=errors
        )
        
    file_size_bytes = os.path.getsize(file_path)
    is_not_empty = file_size_bytes > 0
    if not is_not_empty:
        errors.append("File is empty (0 bytes).")
        
    # Check max file size limit
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    if file_size_bytes > max_bytes:
        errors.append(f"File size ({file_size_bytes / (1024*1024):.2f} MB) exceeds maximum allowed ({settings.MAX_FILE_SIZE_MB} MB).")

    # 2. Extension check
    ext = os.path.splitext(filename)[1].lower()
    supported_extension = ext in SUPPORTED_EXTENSIONS
    if not supported_extension:
        errors.append(f"Unsupported file extension '{ext}'. Only PDF, JPG, PNG are supported.")

    # 3. Signature & Content validation (Magic bytes)
    detected_mime = "unknown"
    signature_valid = False
    page_count = 0
    page_count_valid = True
    decodable = False
    readable = False

    try:
        with open(file_path, "rb") as f:
            header = f.read(16)
            
        if header.startswith(b"%PDF"):
            detected_mime = "application/pdf"
            signature_valid = True
        elif header.startswith(b"\x89PNG\r\n\x1a\n"):
            detected_mime = "image/png"
            signature_valid = True
        elif header.startswith(b"\xff\xd8\xff"):
            detected_mime = "image/jpeg"
            signature_valid = True
        else:
            errors.append("Invalid file header/signature. File content does not match PDF, JPG, or PNG.")
    except Exception as e:
        errors.append(f"Error reading file signature: {str(e)}")

    # 4. Deep format validation
    if signature_valid and is_not_empty:
        if detected_mime == "application/pdf":
            try:
                doc = fitz.open(file_path)
                page_count = len(doc)
                decodable = True
                
                if page_count == 0:
                    errors.append("PDF contains 0 pages.")
                    page_count_valid = False
                elif page_count > 3:
                    errors.append(f"PDF contains {page_count} pages. Maximum allowed length is 3 pages.")
                    page_count_valid = False
                else:
                    page_count_valid = True

                # Check readability (text or renderable images)
                has_text_or_image = False
                for page_idx in range(page_count):
                    page = doc[page_idx]
                    text = page.get_text()
                    if text.strip() or page.get_images():
                        has_text_or_image = True
                        break
                        
                # Even if completely blank scanned page, if we can render image it's readable
                readable = decodable and page_count_valid
                doc.close()
            except Exception as e:
                decodable = False
                readable = False
                errors.append(f"Corrupt or unreadable PDF document: {str(e)}")

        elif detected_mime in ("image/jpeg", "image/png"):
            page_count = 1
            page_count_valid = True
            try:
                with Image.open(file_path) as img:
                    img.verify() # Verify image integrity
                
                # Re-open for dimension check since verify closes/invalidates img
                with Image.open(file_path) as img:
                    w, h = img.size
                    if w > 0 and h > 0:
                        decodable = True
                        readable = True
                    else:
                        errors.append("Image dimensions are invalid (0x0).")
            except Exception as e:
                decodable = False
                readable = False
                errors.append(f"Corrupt or unreadable image file: {str(e)}")

    is_valid = (
        file_exists and is_not_empty and supported_extension and signature_valid
        and decodable and page_count_valid and readable and len(errors) == 0
    )

    return FileValidationResult(
        is_valid=is_valid,
        file_exists=file_exists,
        is_not_empty=is_not_empty,
        supported_extension=supported_extension,
        signature_valid=signature_valid,
        page_count=page_count,
        page_count_valid=page_count_valid,
        decodable=decodable,
        readable=readable,
        file_size_bytes=file_size_bytes,
        detected_mime=detected_mime,
        errors=errors
    )
