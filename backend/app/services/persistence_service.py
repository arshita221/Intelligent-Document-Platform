from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from app.db.models import ProcessedDocument
from app.schemas.documents import DocumentResponse, DocumentListItem, DocumentListResponse, FileValidationResult, ProcessingMetadata
from app.schemas.extraction import DocumentExtraction
from app.schemas.validation import ValidationSummary
from app.core.logging_config import logger

def save_processed_document(
    db: Session,
    document_name: str,
    original_filename: str,
    document_type: str,
    file_type: str,
    page_count: int,
    processing_status: str,
    file_validation: FileValidationResult,
    extracted_data: DocumentExtraction,
    validation_results: ValidationSummary,
    processing_metadata: ProcessingMetadata,
    error_message: Optional[str] = None
) -> ProcessedDocument:
    """Persists processing result to database using SQLAlchemy."""
    doc_record = ProcessedDocument(
        document_name=document_name,
        original_filename=original_filename,
        document_type=document_type,
        file_type=file_type,
        page_count=page_count,
        processing_status=processing_status,
        uploaded_at=datetime.utcnow(),
        processed_at=datetime.utcnow(),
        file_validation=file_validation.model_dump(),
        extracted_data=extracted_data.model_dump(),
        validation_results=validation_results.model_dump(),
        processing_metadata=processing_metadata.model_dump(),
        error_message=error_message
    )
    db.add(doc_record)
    db.commit()
    db.refresh(doc_record)
    logger.info(f"Successfully persisted document '{document_name}' to database.")
    return doc_record

def get_document_by_name(db: Session, document_name: str) -> Optional[ProcessedDocument]:
    """Retrieves document by unique document_name."""
    return db.query(ProcessedDocument).filter(ProcessedDocument.document_name == document_name).first()

def list_all_documents(db: Session) -> DocumentListResponse:
    """Queries all processed documents for dashboard view."""
    records = db.query(ProcessedDocument).order_by(ProcessedDocument.uploaded_at.desc()).all()
    
    total = len(records)
    passed = sum(1 for r in records if r.processing_status == "PASS")
    failed = sum(1 for r in records if r.processing_status == "FAILED")

    items = [
        DocumentListItem(
            id=r.id,
            document_name=r.document_name,
            original_filename=r.original_filename,
            document_type=r.document_type,
            file_type=r.file_type,
            page_count=r.page_count,
            processing_status=r.processing_status,
            uploaded_at=r.uploaded_at,
            processed_at=r.processed_at,
            error_message=r.error_message
        )
        for r in records
    ]

    return DocumentListResponse(
        total_count=total,
        passed_count=passed,
        failed_count=failed,
        documents=items
    )
