import os
import shutil
import tempfile
import json
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.services.document_service import process_document_pipeline
from app.services.persistence_service import get_document_by_name, list_all_documents
from app.schemas.documents import DocumentResponse, DocumentListResponse, FileValidationResult, ProcessingMetadata
from app.schemas.extraction import DocumentExtraction
from app.schemas.validation import ValidationSummary
from app.core.logging_config import logger

router = APIRouter(prefix="/documents", tags=["Documents"])

@router.post("/process", response_model=DocumentResponse, status_code=status.HTTP_200_OK)
async def process_document(
    file: UploadFile = File(...),
    document_type: str = Form(...),
    db: Session = Depends(get_db)
):
    """
    Ingests, validates, extracts AI financial data, validates math, and persists results.
    Returns DocumentResponse (processing_status: PASS or FAILED).
    """
    logger.info(f"Received upload request for filename='{file.filename}', document_type='{document_type}'")
    
    # Create safe temporary file for processing
    suffix = os.path.splitext(file.filename)[1] if file.filename else ".tmp"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        response_data, status_code = process_document_pipeline(
            file_path=tmp_path,
            original_filename=file.filename or "uploaded_document",
            document_type=document_type,
            db=db
        )
        if status_code in (400, 500):
            json_compatible_detail = json.loads(response_data.model_dump_json())
            raise HTTPException(status_code=status_code, detail=json_compatible_detail)

        return response_data
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

@router.get("/{document_name}", response_model=DocumentResponse)
def get_document(document_name: str, db: Session = Depends(get_db)):
    """Retrieves a processed document result by unique document_name."""
    record = get_document_by_name(db, document_name)
    if not record:
        raise HTTPException(status_code=404, detail=f"Document '{document_name}' not found.")
        
    return DocumentResponse(
        id=record.id,
        document_name=record.document_name,
        document_type=record.document_type,
        original_filename=record.original_filename,
        file_type=record.file_type,
        page_count=record.page_count,
        processing_status=record.processing_status,
        uploaded_at=record.uploaded_at,
        processed_at=record.processed_at,
        file_validation=FileValidationResult(**record.file_validation),
        extracted_data=DocumentExtraction(**record.extracted_data),
        validation=ValidationSummary(**record.validation_results),
        processing_metadata=ProcessingMetadata(**record.processing_metadata),
        error_message=record.error_message
    )

@router.get("", response_model=DocumentListResponse)
def list_documents(db: Session = Depends(get_db)):
    """Retrieves list of all processed documents from the database."""
    return list_all_documents(db)
