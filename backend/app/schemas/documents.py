from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from app.schemas.extraction import DocumentExtraction
from app.schemas.validation import ValidationSummary

class FileValidationResult(BaseModel):
    is_valid: bool
    file_exists: bool
    is_not_empty: bool
    supported_extension: bool
    signature_valid: bool
    page_count: int
    page_count_valid: bool
    decodable: bool
    readable: bool
    file_size_bytes: int
    detected_mime: str
    errors: List[str] = []

class ProcessingMetadata(BaseModel):
    processing_time_seconds: float
    timestamp: str
    extractor_used: str
    pages_processed: int
    environment: str

class DocumentResponse(BaseModel):
    id: Optional[str] = None
    document_name: str
    document_type: str
    original_filename: str
    file_type: str
    page_count: int
    processing_status: str = Field(..., description="PASS or FAILED")
    uploaded_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    file_validation: FileValidationResult
    extracted_data: DocumentExtraction
    validation: ValidationSummary
    processing_metadata: ProcessingMetadata
    error_message: Optional[str] = None

class DocumentListItem(BaseModel):
    id: str
    document_name: str
    original_filename: str
    document_type: str
    file_type: str
    page_count: int
    processing_status: str
    uploaded_at: datetime
    processed_at: datetime
    error_message: Optional[str] = None

class DocumentListResponse(BaseModel):
    total_count: int
    passed_count: int
    failed_count: int
    documents: List[DocumentListItem]
