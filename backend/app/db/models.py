import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Text, JSON
from app.db.database import Base

class ProcessedDocument(Base):
    __tablename__ = "processed_documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_name = Column(String(255), unique=True, index=True, nullable=False)
    original_filename = Column(String(255), nullable=False)
    document_type = Column(String(50), nullable=False, index=True)
    file_type = Column(String(20), nullable=False)
    page_count = Column(Integer, default=1)
    processing_status = Column(String(20), nullable=False, index=True) # PASS or FAILED
    
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, default=datetime.utcnow)
    
    file_validation = Column(JSON, nullable=False)
    extracted_data = Column(JSON, nullable=False)
    validation_results = Column(JSON, nullable=False)
    processing_metadata = Column(JSON, nullable=False)
    
    error_message = Column(Text, nullable=True)
