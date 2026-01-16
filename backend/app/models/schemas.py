from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from enum import Enum

class FieldType(str, Enum):
    TEXT = "text"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    SELECT = "select"
    DATE = "date"
    NUMBER = "number"

class FormField(BaseModel):
    name: str
    field_type: FieldType
    required: bool = False
    options: List[str] = Field(default_factory=list)

class FormSchema(BaseModel):
    fields: List[FormField]
    form_type: str
    version: str

class ExtractedData(BaseModel):
    patient_info: Dict[str, Any] = Field(default_factory=dict)
    clinical_info: Dict[str, Any] = Field(default_factory=dict)
    provider_info: Dict[str, Any] = Field(default_factory=dict)
    insurance_info: Dict[str, Any] = Field(default_factory=dict)

class ValidationResult(BaseModel):
    is_valid: bool
    missing_fields: List[str] = Field(default_factory=list)
    invalid_fields: Dict[str, str] = Field(default_factory=dict)

class ProcessingResult(BaseModel):
    success: bool
    filled_pdf_path: Optional[str] = None
    extracted_data: Optional[ExtractedData] = None
    validation_result: Optional[ValidationResult] = None
    processing_time: float
    error_message: Optional[str] = None 