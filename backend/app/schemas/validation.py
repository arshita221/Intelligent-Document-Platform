from typing import Dict, Optional, Any, List
from pydantic import BaseModel, Field

class ValidationCheck(BaseModel):
    check_name: str
    formula: str
    operands: Dict[str, Optional[float]]
    calculated_value: Optional[float] = None
    reported_value: Optional[float] = None
    variance: Optional[float] = None
    tolerance: float = 1.0
    status: str = Field(..., description="PASS, FAIL, or NOT_APPLICABLE")
    details: Optional[str] = None
    period: Optional[str] = None

class ValidationSummary(BaseModel):
    overall_status: str = Field(..., description="PASS or FAILED")
    passed_count: int = 0
    failed_count: int = 0
    not_applicable_count: int = 0
    checks: List[ValidationCheck] = []
