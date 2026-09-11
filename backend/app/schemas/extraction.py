from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field as PydanticField

class ExtractedField(BaseModel):
    name: str = PydanticField(..., description="Canonical or raw field name")
    value: Optional[Any] = PydanticField(default=None, description="Exact string/value from document or null if missing/unreadable")
    normalized_value: Optional[float] = PydanticField(default=None, description="Parsed numeric value if applicable")
    evidence: Optional[str] = PydanticField(default=None, description="Surrounding text or snippet as evidence")
    page_number: Optional[int] = PydanticField(default=1, description="Page number where field was found")
    confidence: Optional[float] = PydanticField(default=1.0, description="Confidence score 0.0 to 1.0")
    status: Optional[str] = PydanticField(default="EXTRACTED", description="EXTRACTED, UNREADABLE, or MISSING")

class LineItem(BaseModel):
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    discount: Optional[float] = None
    tax: Optional[float] = None
    taxable_amount: Optional[float] = None
    amount: Optional[float] = None
    total: Optional[float] = None
    raw_data: Optional[Dict[str, Any]] = None
    evidence: Optional[str] = None
    page_number: Optional[int] = 1

class TableRow(BaseModel):
    cells: List[Optional[str]] = []

class FinancialTable(BaseModel):
    name: Optional[str] = None
    headers: List[str] = []
    rows: List[List[Optional[str]]] = []
    page_number: Optional[int] = 1
    evidence: Optional[str] = None

class Period(BaseModel):
    label: str = PydanticField(..., description="Period label, e.g., '2024', '2023-24', 'Q1 2025'")
    fields: List[ExtractedField] = []

class Note(BaseModel):
    title: Optional[str] = None
    content: str
    page_number: Optional[int] = 1

class RawTextPage(BaseModel):
    page_number: int
    text: str

class DocumentExtraction(BaseModel):
    document_type: str = PydanticField(..., description="invoice, balance_sheet, profit_loss, cash_flow")
    fields: List[ExtractedField] = []
    line_items: List[LineItem] = []
    tables: List[FinancialTable] = []
    periods: List[Period] = []
    notes: List[Note] = []
    raw_text_by_page: List[RawTextPage] = []
    metadata: Dict[str, Any] = {}
