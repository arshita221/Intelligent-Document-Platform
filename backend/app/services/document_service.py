import time
import os
from datetime import datetime
from typing import Tuple, Optional
from sqlalchemy.orm import Session
from app.utils.file_validation import validate_uploaded_file
from app.utils.helpers import generate_document_name
from app.extraction.pdf_processor import process_pdf_document
from app.extraction.image_processor import process_image_document
from app.services.gemini_service import extract_with_gemini
from app.validation.engine import run_financial_validation
from app.services import persistence_service
from app.schemas.documents import DocumentResponse, FileValidationResult, ProcessingMetadata
from app.schemas.extraction import DocumentExtraction, RawTextPage
from app.schemas.validation import ValidationSummary, ValidationCheck
from app.core.config import settings
from app.core.logging_config import logger

VALID_DOC_TYPES = {"invoice", "balance_sheet", "profit_loss", "cash_flow"}

def process_document_pipeline(
    file_path: str,
    original_filename: str,
    document_type: str,
    db: Session
) -> Tuple[DocumentResponse, int]:
    """
    Complete end-to-end document processing pipeline.
    Returns (DocumentResponse, http_status_code).
    """
    start_time = time.time()
    doc_type_clean = document_type.lower().strip()

    # Validate document_type input
    if doc_type_clean not in VALID_DOC_TYPES:
        err_msg = f"Invalid document_type '{document_type}'. Supported: invoice, balance_sheet, profit_loss, cash_flow."
        logger.error(err_msg)
        dummy_validation = FileValidationResult(
            is_valid=False, file_exists=True, is_not_empty=True, supported_extension=False,
            signature_valid=False, page_count=0, page_count_valid=False, decodable=False,
            readable=False, file_size_bytes=0, detected_mime="unknown", errors=[err_msg]
        )
        empty_extraction = DocumentExtraction(document_type=doc_type_clean)
        empty_validation = ValidationSummary(overall_status="FAILED", checks=[])
        metadata = ProcessingMetadata(
            processing_time_seconds=0.0, timestamp=datetime.utcnow().isoformat(),
            extractor_used="none", pages_processed=0, environment=settings.ENVIRONMENT
        )
        return DocumentResponse(
            document_name=generate_document_name(original_filename),
            document_type=doc_type_clean,
            original_filename=original_filename,
            file_type="unknown",
            page_count=0,
            processing_status="FAILED",
            file_validation=dummy_validation,
            extracted_data=empty_extraction,
            validation=empty_validation,
            processing_metadata=metadata,
            error_message=err_msg
        ), 400

    # 1. Layer: File Validation
    logger.info(f"Starting file validation for '{original_filename}'...")
    val_result = validate_uploaded_file(file_path, original_filename)
    document_name = generate_document_name(original_filename)

    if not val_result.is_valid:
        logger.warning(f"File validation failed for '{original_filename}': {val_result.errors}")
        empty_extraction = DocumentExtraction(document_type=doc_type_clean)
        empty_validation = ValidationSummary(overall_status="FAILED", checks=[])
        proc_metadata = ProcessingMetadata(
            processing_time_seconds=round(time.time() - start_time, 3),
            timestamp=datetime.utcnow().isoformat(),
            extractor_used="none",
            pages_processed=val_result.page_count,
            environment=settings.ENVIRONMENT
        )
        
        # Save failed record in database
        saved = persistence_service.save_processed_document(
            db=db,
            document_name=document_name,
            original_filename=original_filename,
            document_type=doc_type_clean,
            file_type=val_result.detected_mime,
            page_count=val_result.page_count,
            processing_status="FAILED",
            file_validation=val_result,
            extracted_data=empty_extraction,
            validation_results=empty_validation,
            processing_metadata=proc_metadata,
            error_message="; ".join(val_result.errors)
        )

        resp = DocumentResponse(
            id=saved.id,
            document_name=document_name,
            document_type=doc_type_clean,
            original_filename=original_filename,
            file_type=val_result.detected_mime,
            page_count=val_result.page_count,
            processing_status="FAILED",
            uploaded_at=saved.uploaded_at,
            processed_at=saved.processed_at,
            file_validation=val_result,
            extracted_data=empty_extraction,
            validation=empty_validation,
            processing_metadata=proc_metadata,
            error_message="; ".join(val_result.errors)
        )
        return resp, 400

    # 2. Layer: Document / Page Processing
    raw_text_pages = []
    page_images = []
    is_scanned = False

    if val_result.detected_mime == "application/pdf":
        raw_text_pages, page_images, is_scanned = process_pdf_document(file_path)
    else:
        img_bytes, mime, info = process_image_document(file_path)
        page_images = [img_bytes]
        raw_text_pages = [RawTextPage(page_number=1, text="")]
        is_scanned = True

    # 3 & 4. Layer: AI Structured Extraction
    extractor_name = "gemini-2.5-flash"
    try:
        extraction_data = extract_with_gemini(
            document_type=doc_type_clean,
            raw_text_pages=raw_text_pages,
            page_images=page_images,
            is_scanned=is_scanned
        )
    except Exception as exc:
        logger.error(f"Extraction error for '{original_filename}': {str(exc)}")
        empty_extraction = DocumentExtraction(document_type=doc_type_clean, raw_text_by_page=raw_text_pages)
        empty_validation = ValidationSummary(overall_status="FAILED", checks=[])
        proc_metadata = ProcessingMetadata(
            processing_time_seconds=round(time.time() - start_time, 3),
            timestamp=datetime.utcnow().isoformat(),
            extractor_used=extractor_name,
            pages_processed=len(page_images),
            environment=settings.ENVIRONMENT
        )
        saved = persistence_service.save_processed_document(
            db=db,
            document_name=document_name,
            original_filename=original_filename,
            document_type=doc_type_clean,
            file_type=val_result.detected_mime,
            page_count=val_result.page_count,
            processing_status="FAILED",
            file_validation=val_result,
            extracted_data=empty_extraction,
            validation_results=empty_validation,
            processing_metadata=proc_metadata,
            error_message=f"AI extraction failed: {str(exc)}"
        )
        resp = DocumentResponse(
            id=saved.id,
            document_name=document_name,
            document_type=doc_type_clean,
            original_filename=original_filename,
            file_type=val_result.detected_mime,
            page_count=val_result.page_count,
            processing_status="FAILED",
            uploaded_at=saved.uploaded_at,
            processed_at=saved.processed_at,
            file_validation=val_result,
            extracted_data=empty_extraction,
            validation=empty_validation,
            processing_metadata=proc_metadata,
            error_message=f"AI extraction failed: {str(exc)}"
        )
        return resp, 500

    # 5 & 6. Layer: Deterministic Financial Validation
    validation_summary = run_financial_validation(extraction_data)

    # Overall processing status
    overall_status = "PASS" if (val_result.is_valid and validation_summary.overall_status == "PASS") else "FAILED"

    proc_metadata = ProcessingMetadata(
        processing_time_seconds=round(time.time() - start_time, 3),
        timestamp=datetime.utcnow().isoformat(),
        extractor_used=extractor_name,
        pages_processed=len(page_images),
        environment=settings.ENVIRONMENT
    )

    # 7. Layer: Database Persistence
    saved_doc = persistence_service.save_processed_document(
        db=db,
        document_name=document_name,
        original_filename=original_filename,
        document_type=doc_type_clean,
        file_type=val_result.detected_mime,
        page_count=val_result.page_count,
        processing_status=overall_status,
        file_validation=val_result,
        extracted_data=extraction_data,
        validation_results=validation_summary,
        processing_metadata=proc_metadata,
        error_message=None if overall_status == "PASS" else "Financial validation failed."
    )

    resp = DocumentResponse(
        id=saved_doc.id,
        document_name=document_name,
        document_type=doc_type_clean,
        original_filename=original_filename,
        file_type=val_result.detected_mime,
        page_count=val_result.page_count,
        processing_status=overall_status,
        uploaded_at=saved_doc.uploaded_at,
        processed_at=saved_doc.processed_at,
        file_validation=val_result,
        extracted_data=extraction_data,
        validation=validation_summary,
        processing_metadata=proc_metadata,
        error_message=saved_doc.error_message
    )

    return resp, 200
