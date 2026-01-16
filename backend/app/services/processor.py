import base64
from datetime import datetime
import logging
import os
import json
import re
from typing import Optional, List, Dict, Any

import fitz  # PyMuPDF
from PIL import Image
import pytesseract
import google.generativeai as genai
from thefuzz import process as fuzzy_process, fuzz
from mistralai import Mistral

from ..models.schemas import (
    FormSchema,
    ExtractedData,
    ValidationResult,
    ProcessingResult,
    FormField,
    FieldType
)
from ..core.config import settings
from ..core.prompts import get_system_data_collection_prompt, get_data_collection_prompt

class PAFormProcessor:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
        # Add console handler if not already present
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        
        # Configure Gemini API
        try:
            genai.configure(api_key=settings.GEMINI_API_KEY)
            self.gemini_model = genai.GenerativeModel('gemini-1.5-flash')
            self.logger.info("Gemini API configured successfully.")
        except Exception as e:
            self.logger.error(f"Failed to configure Gemini API: {e}")
            self.gemini_model = None

        # Configure Mistral API for OCR
        try:
            self.mistral_client = Mistral(api_key=settings.MISTRAL_API_KEY)
            self.mistral_ocr_model = "mistral-ocr-latest"
            self.logger.info("Mistral API client configured successfully.")
        except Exception as e:
            self.logger.error(f"Failed to configure Mistral API client: {e}")
            self.mistral_client = None

    async def process_prior_auth(self, pa_form_path: str, referral_path: str, output_dir: str) -> ProcessingResult:
        """
        Main method to process a Prior Authorization form
        
        Args:
            pa_form_path: Path to the PA form PDF
            referral_path: Path to the referral document
            output_dir: Directory to save output files
            
        Returns:
            ProcessingResult object containing processing results and any errors
        """
        start_time = datetime.now()
        
        try:
            self.logger.info("=== Starting Prior Authorization Processing ===")
            
            # Step 1: Analyze PA form structure
            self.logger.info(f"Step 1: Analyzing PA form structure from {pa_form_path}")
            form_schema = await self._analyze_form(pa_form_path)
            if not form_schema:
                raise Exception("Failed to analyze PA form structure")
            
            # Step 2: Extract text from referral
            self.logger.info(f"Step 2: Processing referral document from {referral_path}")
            referral_text = await self._extract_referral_text(referral_path)
            if not referral_text:
                raise Exception("Failed to extract text from referral document")
            
            # Step 3: Extract and map data
            self.logger.info("Step 3: Extracting and mapping data")
            extracted_data = await self._extract_form_data(referral_text, form_schema)
            if not extracted_data:
                raise Exception("Failed to extract data from referral using AI.")
            
            # Step 4: Validate extracted data
            self.logger.info("Step 4: Validating extracted data")
            validation_result = await self._validate_data(extracted_data, form_schema)
            
            # Step 5: Fill the form
            self.logger.info("Step 5: Filling PA form")
            filled_pdf_path = await self._fill_form(pa_form_path, extracted_data, form_schema, output_dir)
            if not filled_pdf_path:
                self.logger.warning("Form filling did not produce a file.")

            processing_time = (datetime.now() - start_time).total_seconds()
            
            self.logger.info("=== Processing Completed Successfully ===")
            return ProcessingResult(
                success=True,
                filled_pdf_path=filled_pdf_path,
                extracted_data=extracted_data,
                validation_result=validation_result,
                processing_time=processing_time
            )
            
        except Exception as e:
            self.logger.error(f"Processing failed: {str(e)}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            
            return ProcessingResult(
                success=False,
                filled_pdf_path=None,
                extracted_data=None,
                validation_result=None,
                processing_time=(datetime.now() - start_time).total_seconds(),
                error_message=str(e)
            )

    async def _analyze_form(self, pdf_path: str) -> Optional[FormSchema]:
        """
        Analyze the PDF to identify form fields (widgets).
        
        This method focuses on existing interactive form fields in the PDF.
        """
        self.logger.info(f"Analyzing PDF for interactive fields: {pdf_path}")
        try:
            doc = fitz.open(pdf_path)
            all_fields: List[FormField] = []
            
            for page in doc:
                for widget in page.widgets():
                    field_type = self._map_widget_type(widget.field_type)
                    if not widget.field_name:
                        self.logger.warning(f"Skipping unnamed widget of type {field_type.value} on page {page.number}")
                        continue

                    form_field = FormField(
                        name=widget.field_name,
                        field_type=field_type,
                        required=bool(widget.field_flags & fitz.PDF_FIELD_IS_REQUIRED),
                        options=widget.choice_values if widget.field_type in [
                            fitz.PDF_WIDGET_TYPE_COMBOBOX, 
                            fitz.PDF_WIDGET_TYPE_LISTBOX,
                            fitz.PDF_WIDGET_TYPE_RADIOBUTTON
                        ] else [],
                    )
                    all_fields.append(form_field)

            if not all_fields:
                self.logger.warning("No interactive form fields found. Forcing creation of a default schema for OCR-based filling.")
                # If a form has no fields, we can't extract data for it with this method.
                # In a real scenario, you might have a different flow for non-widgeted forms,
                # perhaps one that uses AI to identify field locations.
                # For now, we'll create a generic schema.
                return self._create_generic_schema()

            self.logger.info(f"Successfully analyzed form, found {len(all_fields)} interactive fields.")
            return FormSchema(
                fields=all_fields,
                form_type="interactive",
                version="1.0"
            )

        except Exception as e:
            self.logger.error(f"Error analyzing PDF form {pdf_path}: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            return None

    def _map_widget_type(self, widget_type: int) -> FieldType:
        """Maps PyMuPDF widget type to our FieldType enum."""
        mapping = {
            fitz.PDF_WIDGET_TYPE_TEXT: FieldType.TEXT,
            fitz.PDF_WIDGET_TYPE_CHECKBOX: FieldType.CHECKBOX,
            fitz.PDF_WIDGET_TYPE_RADIOBUTTON: FieldType.RADIO,
            fitz.PDF_WIDGET_TYPE_COMBOBOX: FieldType.SELECT,
            fitz.PDF_WIDGET_TYPE_LISTBOX: FieldType.SELECT,
        }
        return mapping.get(widget_type, FieldType.TEXT)

    async def _extract_referral_text(self, referral_path: str) -> Optional[str]:
        """
        Extracts text from a referral document using the dedicated Mistral OCR API.
        This handles PDF and common image files by sending them directly to the API.
        """
        self.logger.info(f"Extracting text from '{referral_path}' using Mistral OCR API.")
        if not self.mistral_client:
            self.logger.error("Mistral client not initialized. Cannot perform OCR.")
            return None

        if not os.path.exists(referral_path):
            self.logger.error(f"File not found: {referral_path}")
            return None

        try:
            # 1. Read the file in binary
            with open(referral_path, "rb") as f:
                file_bytes = f.read()

            # 2. Encode to base64
            base64_encoded_file = base64.b64encode(file_bytes).decode("utf-8")

            # 3. Determine MIME type
            _, file_extension = os.path.splitext(referral_path.lower())
            mime_types = {
                ".pdf": "application/pdf",
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
            }
            mime_type = mime_types.get(file_extension)
            if not mime_type:
                self.logger.warning(
                    f"Unsupported file type for Mistral OCR: {file_extension}"
                )
                return None

            # 4. Format data URI
            data_uri = f"data:{mime_type};base64,{base64_encoded_file}"

            # 5. Call the dedicated OCR endpoint asynchronously
            self.logger.info(f"Sending {file_extension} to Mistral OCR API...")
            
            ocr_response = await self.mistral_client.ocr.process_async(
                model=self.mistral_ocr_model,
                document={"type": "document_url", "document_url": data_uri},
            )
            
            # 6. Parse the response and join text from all pages
            all_text_parts = [page.markdown for page in ocr_response.pages]
            final_text = "\n\n--- Page Break ---\n\n".join(all_text_parts)
            
            self.logger.info(
                f"Successfully extracted {len(final_text)} characters using Mistral OCR API."
            )
            return final_text

        except Exception as e:
            self.logger.error(
                f"Error during Mistral OCR extraction from {referral_path}: {e}"
            )
            import traceback

            self.logger.error(f"Traceback: {traceback.format_exc()}")
            return None

    def _schema_to_json(self, fields: List[Dict[str, Any]]) -> str:
        """Converts a list of fields into a categorized JSON string for the AI prompt."""
        schema_dict: Dict[str, Dict[str, str]] = {
            "patient_info": {},
            "provider_info": {},
            "insurance_info": {},
            "clinical_info": {},
        }

        for field in fields:
            name = field["name"]
            name_lower = name.lower()
            # Use a more robust categorization based on common medical form sections
            if any(k in name_lower for k in ["patient", "member", "subscriber", "dob", "name", "address", "phone", "sex", "gender"]):
                schema_dict["patient_info"][name] = ""
            elif any(k in name_lower for k in ["provider", "doctor", "physician", "prescriber", "npi", "clinic", "facility"]):
                schema_dict["provider_info"][name] = ""
            elif any(k in name_lower for k in ["insurance", "carrier", "policy", "group", "payer", "plan"]):
                 schema_dict["insurance_info"][name] = ""
            else:  # Default to clinical info
                schema_dict["clinical_info"][name] = ""
                
        return json.dumps(schema_dict, indent=2)

    def _clean_json_response(self, raw_response: str) -> Optional[Dict[str, Any]]:
        """
        Cleans the raw string response from the LLM to extract a valid JSON object.
        """
        self.logger.debug(f"Raw AI Response:\n{raw_response}")

        # Use a regex to find the JSON block, allowing for markdown ```json ... ```
        match = re.search(r"```json\s*(\{.*?\})\s*```", raw_response, re.DOTALL)
        if match:
            json_str = match.group(1)
        else:
            # If no markdown, assume the whole string is a JSON object,
            # but find the first '{' and last '}' to be safe.
            start = raw_response.find("{")
            end = raw_response.rfind("}")
            if start != -1 and end != -1:
                json_str = raw_response[start : end + 1]
            else:
                self.logger.error("No JSON object found in the AI response.")
                return None

        try:
            parsed_json = json.loads(json_str)
            self.logger.info("--- SUCCESSFULLY PARSED JSON FROM AI ---")
            self.logger.info(json.dumps(parsed_json, indent=2))
            self.logger.info("--- END AI JSON ---")
            return parsed_json
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to decode JSON from AI response: {e}")
            self.logger.error(f"Problematic JSON string: {json_str}")
            return None

    async def _extract_form_data(
        self, referral_text: str, form_schema: FormSchema
    ) -> Optional[ExtractedData]:
        """
        Extracts and maps data from referral text to form schema using an LLM.
        This now uses a generic, high-quality schema to query the AI, decoupling it
        from the PDF's specific (and often poor) field names.
        """
        if not self.gemini_model:
            self.logger.error("Gemini model is not initialized. Cannot extract data.")
            return None
            
        self.logger.info("Generating a high-quality generic schema for AI extraction.")
        
        # Instead of using the PDF's schema directly, create a clean, generic one.
        # This is the key to getting good results from the AI.
        generic_fields = self._get_generic_medical_fields()
        schema_json = self._schema_to_json(generic_fields)
        
        system_prompt = get_system_data_collection_prompt()
        user_prompt = get_data_collection_prompt(schema_json, referral_text)

        try:
            self.logger.info("Sending request to Gemini API with generic schema...")
            
            response = await self.gemini_model.generate_content_async(
                [system_prompt, user_prompt]
            )
            
            self.logger.info("Received response from Gemini API.")
            
            extracted_json = self._clean_json_response(response.text)
            
            if not extracted_json:
                return None

            return ExtractedData.model_validate(extracted_json)

        except Exception as e:
            self.logger.error(f"Error during AI data extraction: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            return None

    def _get_generic_medical_fields(self) -> List[Dict[str, Any]]:
        """
        Returns a list of generic, human-readable fields commonly found on PA forms.
        This standardizes the data extraction task for the AI.
        """
        return [
            # Patient Info
            {"name": "Patient First Name"}, {"name": "Patient Last Name"}, {"name": "Patient DOB"},
            {"name": "Patient Sex"}, {"name": "Patient Address"}, {"name": "Patient City"},
            {"name": "Patient State"}, {"name": "Patient Zip Code"}, {"name": "Patient Phone Number"},

            # Provider Info
            {"name": "Prescribing Provider First Name"}, {"name": "Prescribing Provider Last Name"},
            {"name": "Provider NPI"}, {"name": "Provider Phone Number"}, {"name": "Provider Fax Number"},
            {"name": "Clinic Name"},
            
            # Insurance Info
            {"name": "Insurance Plan Name"}, {"name": "Insurance Member ID"}, {"name": "Insurance Group Number"},
            
            # Clinical Info
            {"name": "Primary Diagnosis (ICD-10 Code)"}, {"name": "Secondary Diagnosis (ICD-10 Code)"},
            {"name": "Medication Requested"}, {"name": "Dosage"}, {"name": "Frequency"},
            {"name": "Has the patient tried other treatments?"},
            {"name": "List previous treatments and reasons for failure"},
            {"name": "Is this a renewal or continuation of therapy?"},
            {"name": "Date of last treatment"},
            {"name": "Clinical notes justifying medical necessity"}
        ]

    def _create_generic_schema(self) -> FormSchema:
        """Creates a generic schema for non-interactive forms."""
        # This is a placeholder. In a real application, you might have a predefined
        # set of common fields to look for.
        generic_fields = [
            FormField(name="Patient First Name", field_type=FieldType.TEXT),
            FormField(name="Patient Last Name", field_type=FieldType.TEXT),
            FormField(name="Patient DOB", field_type=FieldType.DATE),
            FormField(name="Diagnosis Code (ICD-10)", field_type=FieldType.TEXT),
            FormField(name="Prescribed Medication", field_type=FieldType.TEXT),
            FormField(name="Provider NPI", field_type=FieldType.TEXT),
            FormField(name="Insurance Member ID", field_type=FieldType.TEXT),
        ]
        return FormSchema(fields=generic_fields, form_type="generic-non-interactive", version="1.0")

    async def _validate_data(self, extracted_data: ExtractedData, form_schema: FormSchema) -> ValidationResult:
        """(STUB) Validate extracted data against form schema"""
        self.logger.info("Data validation is not yet implemented.")
        # For now, we assume all data is valid.
        # A full implementation would check required fields, data formats (e.g., dates), etc.
        required_fields = [f.name for f in form_schema.fields if f.required]
        missing_fields = []
        all_data = self._get_all_extracted_data_as_dict(extracted_data)

        for req_field in required_fields:
            if not all_data.get(req_field):
                missing_fields.append(req_field)
        
        if missing_fields:
            self.logger.warning(f"Validation found missing required fields: {missing_fields}")
            return ValidationResult(is_valid=False, missing_fields=missing_fields, invalid_fields={})

        return ValidationResult(is_valid=True, missing_fields=[], invalid_fields={})

    async def _fill_form(self, pdf_path: str, extracted_data: ExtractedData, 
                         form_schema: FormSchema, output_dir: str) -> Optional[str]:
        """
        Orchestrates filling the PDF form based on its type (interactive or flat).
        """
        self.logger.info(f"Preparing to fill form. Form type: '{form_schema.form_type}'")

        if "interactive" in form_schema.form_type:
            return self._fill_widget_form(pdf_path, extracted_data, form_schema, output_dir)
        else:
            # For now, we are explicit that flat form filling is not supported yet.
            # This can be the next feature to be implemented.
            self.logger.warning("Filling for non-interactive (flat) PDFs is not yet implemented.")
            # return self._fill_flat_form(pdf_path, extracted_data, form_schema, output_dir)
            return None

    def _get_all_extracted_data_as_dict(self, extracted_data: ExtractedData) -> Dict[str, Any]:
        """Combines all data from the ExtractedData object into a single dictionary."""
        all_data = {}
        all_data.update(extracted_data.patient_info)
        all_data.update(extracted_data.provider_info)
        all_data.update(extracted_data.insurance_info)
        all_data.update(extracted_data.clinical_info)
        return all_data

    def _clean_field_name(self, field_name: str) -> str:
        """
        Cleans a PDF field name for better fuzzy matching. This new strategy
        is less destructive and aims to convert technical names into more
        human-readable strings.
        """
        # 1. Replace common separators with spaces
        s = re.sub(r'[._-]+', ' ', field_name)
        
        # 2. Split on camelCase (e.g., "PatientFirstName" -> "Patient First Name"), but keep acronyms like "NPI" together.
        s = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', s)
        
        # 3. Add a space between letters and numbers to separate them (if not already handled by camelCase)
        s = re.sub(r'([a-zA-Z])(\d)', r'\1 \2', s)
        s = re.sub(r'(\d)([a-zA-Z])', r'\1 \2', s)
        
        # 4. Remove any remaining non-alphanumeric characters (keeps spaces)
        s = re.sub(r'[^\w\s]', '', s)
        
        # 5. Convert to lowercase and remove extra whitespace
        s = s.lower()
        s = ' '.join(s.split())
        
        return s.strip()

    def _get_manual_field_mapping(self) -> Dict[str, str]:
        """
        Returns a manual mapping dictionary that maps AI keys to specific PDF field names.
        This bypasses the flawed fuzzy matching for better accuracy.
        """
        return {
            # Patient Information
            "Patient First Name": "T2",
            "Patient Last Name": "T3", 
            "Patient DOB": "T4",
            "Patient Sex": "T6",
            "Patient Address": "T7",
            "Patient City": "T8",
            "Patient State": "T9",
            "Patient Zip Code": "T10",
            "Patient Phone Number": "T11",
            
            # Provider Information
            "Prescribing Provider First Name": "Provider Admin T.5",
            "Prescribing Provider Last Name": "Provider Admin T.6",
            "Provider NPI": "Provider Admin T.13",
            "Provider Phone Number": "Provider Admin T.8",
            "Provider Fax Number": "Provider Admin T.14",
            "Clinic Name": "Provider Admin T.11A",
            
            # Insurance Information
            "Insurance Plan Name": "Provider Admin T.17A",
            "Insurance Member ID": "Provider Admin T.9",
            "Insurance Group Number": "Provider Admin T.15",
            
            # Clinical Information
            "Primary Diagnosis (ICD-10 Code)": "T104",
            "Secondary Diagnosis (ICD-10 Code)": "T105",
            "Medication Requested": "T106",
            "Dosage": "Provider Admin T.16",
            "Frequency": "Provider Admin T.18",
            "List previous treatments and reasons for failure": "Provider Admin T.29a",
            "Date of last treatment": "T13",
            "Clinical notes justifying medical necessity": "T12",
            
            # Checkboxes
            "Has the patient tried other treatments?": "Provider Admin CB.1",
            "Is this a renewal or continuation of therapy?": "CB98a",
        }

    def _analyze_form_fields(self, pdf_path: str) -> List[Dict[str, Any]]:
        """
        Analyze the PDF form to extract comprehensive field metadata including:
        - Field name, type, position
        - Nearby text/labels for context
        - Current values
        - Field dimensions
        """
        self.logger.info("=== ANALYZING FORM FIELDS ===")
        doc = fitz.open(pdf_path)
        field_metadata = []
        
        for page_num, page in enumerate(doc):
            self.logger.info(f"Analyzing page {page_num + 1}")
            
            # Get all text on the page for context
            page_text = page.get_text()
            
            for widget in page.widgets():
                if not widget.field_name:
                    continue
                    
                # Get field position and dimensions
                rect = widget.rect
                field_info = {
                    "field_name": widget.field_name,
                    "field_type": self._get_field_type_name(widget.field_type),
                    "page": page_num + 1,
                    "position": {
                        "x": rect.x0,
                        "y": rect.y0,
                        "width": rect.width,
                        "height": rect.height
                    },
                    "current_value": widget.field_value if hasattr(widget, 'field_value') else None,
                    "nearby_text": self._extract_nearby_text(page, rect, page_text),
                    "field_flags": widget.field_flags,
                    "choice_values": widget.choice_values if hasattr(widget, 'choice_values') else []
                }
                
                field_metadata.append(field_info)
                self.logger.debug(f"Field: {widget.field_name} ({field_info['field_type']}) at ({rect.x0:.1f}, {rect.y0:.1f})")
        
        self.logger.info(f"Total fields analyzed: {len(field_metadata)}")
        return field_metadata

    def _get_field_type_name(self, field_type: int) -> str:
        """Convert field type enum to readable name."""
        type_map = {
            fitz.PDF_WIDGET_TYPE_TEXT: "text",
            fitz.PDF_WIDGET_TYPE_CHECKBOX: "checkbox", 
            fitz.PDF_WIDGET_TYPE_RADIOBUTTON: "radio",
            fitz.PDF_WIDGET_TYPE_COMBOBOX: "combobox",
            fitz.PDF_WIDGET_TYPE_LISTBOX: "listbox"
        }
        return type_map.get(field_type, "unknown")

    def _extract_nearby_text(self, page, rect, page_text: str) -> str:
        """
        Extract text near the field for context.
        This helps AI understand what the field is asking for.
        """
        try:
            # Create a slightly larger rectangle around the field
            expanded_rect = fitz.Rect(
                rect.x0 - 50,  # 50 points left
                rect.y0 - 20,  # 20 points above
                rect.x1 + 50,  # 50 points right
                rect.y1 + 20   # 20 points below
            )
            
            # Extract text from this area
            nearby_text = page.get_text("text", clip=expanded_rect)
            return nearby_text.strip()
        except Exception as e:
            self.logger.warning(f"Failed to extract nearby text: {e}")
            return ""

    def _fill_widget_form(
        self,
        pdf_path: str,
        extracted_data: ExtractedData,
        form_schema: FormSchema,
        output_dir: str,
    ) -> Optional[str]:
        """
        Fill the form using AI-powered intelligent mapping based on field analysis.
        """
        try:
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)

            file_name = os.path.basename(pdf_path)
            output_path = os.path.join(output_dir, f"filled_{file_name}")

            # Step 1: Analyze form fields
            self.logger.info("Step 1: Analyzing form field metadata...")
            field_metadata = self._analyze_form_fields(pdf_path)
            
            if not field_metadata:
                self.logger.error("No form fields found to analyze")
                return None

            # For now, let's just log the field analysis and use a simple mapping
            # We'll implement the AI mapping in the next step
            self.logger.info("Field analysis complete. Using simple mapping for now...")
            
            # Simple mapping based on field analysis
            final_mapping = self._simple_field_mapping(field_metadata, extracted_data)
            
            if not final_mapping:
                self.logger.warning("No fields were mapped")
                return None

            self.logger.info(f"Successfully mapped {len(final_mapping)} fields")

            # Fill the form
            doc = fitz.open(pdf_path)
            filled_count = 0
            
            for page in doc:
                for widget in page.widgets():
                    if widget.field_name in final_mapping:
                        value = final_mapping[widget.field_name]
                        should_update = False

                        # Fill widget based on type
                        if widget.field_type in [
                            fitz.PDF_WIDGET_TYPE_TEXT,
                            fitz.PDF_WIDGET_TYPE_COMBOBOX,
                            fitz.PDF_WIDGET_TYPE_LISTBOX,
                        ]:
                            if value and str(value).strip():
                                widget.field_value = str(value).strip()
                                should_update = True
                                self.logger.info(f"  TEXT FIELD: '{widget.field_name}' -> '{widget.field_value}'")
                        elif widget.field_type == fitz.PDF_WIDGET_TYPE_CHECKBOX:
                            val_lower = str(value).lower().strip()
                            if val_lower in ["yes", "true", "on", "x", "checked"]:
                                widget.field_value = True
                                should_update = True
                                self.logger.info(f"  CHECKBOX: '{widget.field_name}' -> CHECKED")
                            elif val_lower in ["no", "false", "off", "unchecked"]:
                                widget.field_value = False
                                should_update = True
                                self.logger.info(f"  CHECKBOX: '{widget.field_name}' -> UNCHECKED")

                        # Update the widget
                        if should_update:
                            try:
                                widget.update()
                                filled_count += 1
                                self.logger.info(f"  ✓ SUCCESS: Updated '{widget.field_name}'")
                            except Exception as e:
                                self.logger.error(f"  ✗ ERROR: Failed to update '{widget.field_name}': {e}")

            self.logger.info(f"=== FILLING COMPLETE: Successfully filled {filled_count} out of {len(final_mapping)} mapped fields ===")

            doc.save(output_path, garbage=4, deflate=True, clean=True)
            self.logger.info(f"Successfully filled interactive form and saved to: {output_path}")
            return output_path

        except Exception as e:
            self.logger.error(f"Failed to fill widget form: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            return None

    def _simple_field_mapping(self, field_metadata: List[Dict[str, Any]], extracted_data: ExtractedData) -> Dict[str, str]:
        """
        AI-powered intelligent mapping based on field analysis metadata.
        This replaces the simple mapping with a more sophisticated approach.
        """
        referral_data = self._get_all_extracted_data_as_dict(extracted_data)
        final_mapping = {}
        
        # Log field analysis for debugging
        self.logger.info("=== FIELD ANALYSIS RESULTS ===")
        for field in field_metadata[:10]:  # Show first 10 fields
            self.logger.info(f"Field: {field['field_name']} ({field['field_type']}) at ({field['position']['x']:.1f}, {field['position']['y']:.1f})")
            if field['nearby_text']:
                self.logger.info(f"  Nearby text: {field['nearby_text'][:100]}...")
        
        # Use AI to intelligently map fields based on metadata
        if self.gemini_model:
            final_mapping = self._ai_intelligent_mapping(field_metadata, referral_data)
        else:
            self.logger.warning("Gemini model not available, falling back to basic mapping")
            final_mapping = self._basic_fallback_mapping(field_metadata, referral_data)
        
        return final_mapping

    def _ai_intelligent_mapping(self, field_metadata: List[Dict[str, Any]], referral_data: Dict[str, Any]) -> Dict[str, str]:
        """
        Use AI to intelligently map extracted data to PDF fields based on field metadata.
        """
        self.logger.info("=== USING AI INTELLIGENT MAPPING ===")
        
        # Prepare the mapping prompt
        mapping_prompt = self._create_mapping_prompt(field_metadata, referral_data)
        
        try:
            self.logger.info("Sending field mapping request to Gemini API...")
            
            response = self.gemini_model.generate_content(mapping_prompt)
            
            self.logger.info("Received mapping response from Gemini API.")
            
            # Parse the mapping response
            mapping_result = self._parse_mapping_response(response.text)
            
            if mapping_result:
                self.logger.info(f"AI mapping successful: {len(mapping_result)} fields mapped")
                for pdf_field, value in mapping_result.items():
                    self.logger.info(f"  AI MAPPING: '{pdf_field}' -> '{value}'")
                return mapping_result
            else:
                self.logger.warning("AI mapping failed, falling back to basic mapping")
                return self._basic_fallback_mapping(field_metadata, referral_data)
                
        except Exception as e:
            self.logger.error(f"Error during AI mapping: {e}")
            self.logger.warning("Falling back to basic mapping")
            return self._basic_fallback_mapping(field_metadata, referral_data)

    def _create_mapping_prompt(self, field_metadata: List[Dict[str, Any]], referral_data: Dict[str, Any]) -> str:
        """
        Create a prompt for AI to intelligently map extracted data to PDF fields.
        """
        # Create a summary of available fields
        field_summary = []
        for field in field_metadata:
            field_info = {
                "name": field["field_name"],
                "type": field["field_type"],
                "nearby_text": field["nearby_text"][:200] if field["nearby_text"] else "",
                "position": f"({field['position']['x']:.1f}, {field['position']['y']:.1f})"
            }
            field_summary.append(field_info)
        
        # Create a summary of extracted data
        data_summary = {}
        for key, value in referral_data.items():
            if value and str(value).strip():
                data_summary[key] = str(value).strip()
        
        prompt = f"""
You are an expert at mapping medical form data to PDF form fields. Your task is to map the extracted referral data to the correct PDF form fields based on the field metadata.

EXTRACTED REFERRAL DATA:
{json.dumps(data_summary, indent=2)}

PDF FORM FIELDS (with metadata):
{json.dumps(field_summary, indent=2)}

INSTRUCTIONS:
1. Analyze each PDF field's name, type, and nearby text to understand what information it's asking for
2. Match the extracted referral data to the most appropriate PDF field
3. Consider field types (text, checkbox, etc.) when making matches
4. For checkboxes, use "yes"/"no" or "true"/"false" values
5. Only map fields where you have high confidence in the match
6. Return a JSON object with PDF field names as keys and values as the data to fill

MAPPING RULES:
- Patient name fields often have "name", "first", "last" in nearby text
- Date fields often have "date", "dob", "birth" in nearby text  
- Address fields often have "address", "street", "city", "state", "zip" in nearby text
- Phone fields often have "phone", "tel" in nearby text
- Diagnosis fields often have "diagnosis", "icd", "code" in nearby text
- Medication fields often have "medication", "drug", "prescription" in nearby text
- Provider fields often have "provider", "doctor", "physician", "npi" in nearby text
- Insurance fields often have "insurance", "member", "group", "policy" in nearby text

Return ONLY a JSON object with the mapping, no other text:
"""
        
        return prompt

    def _parse_mapping_response(self, response_text: str) -> Optional[Dict[str, str]]:
        """
        Parse the AI response to extract the field mapping.
        """
        try:
            # Clean the response to extract JSON
            cleaned_json = self._clean_json_response(response_text)
            if cleaned_json:
                return cleaned_json
            else:
                self.logger.error("Failed to parse mapping response as JSON")
                return None
        except Exception as e:
            self.logger.error(f"Error parsing mapping response: {e}")
            return None

    def _basic_fallback_mapping(self, field_metadata: List[Dict[str, Any]], referral_data: Dict[str, Any]) -> Dict[str, str]:
        """
        Basic fallback mapping when AI mapping fails.
        """
        self.logger.info("Using basic fallback mapping...")
        
        # Create a mapping based on field names and nearby text
        mapping = {}
        
        # Common field patterns
        field_patterns = {
            "Patient First Name": ["first", "given", "patient.*name"],
            "Patient Last Name": ["last", "surname", "family"],
            "Patient DOB": ["dob", "birth", "date.*birth"],
            "Patient Sex": ["sex", "gender"],
            "Patient Address": ["address", "street"],
            "Patient City": ["city"],
            "Patient State": ["state"],
            "Patient Zip Code": ["zip", "postal"],
            "Patient Phone Number": ["phone", "tel"],
            "Provider NPI": ["npi"],
            "Provider Phone Number": ["provider.*phone", "doctor.*phone"],
            "Provider Fax Number": ["fax"],
            "Clinic Name": ["clinic", "facility", "practice"],
            "Insurance Member ID": ["member", "id"],
            "Insurance Group Number": ["group"],
            "Primary Diagnosis (ICD-10 Code)": ["diagnosis", "icd", "primary"],
            "Medication Requested": ["medication", "drug", "prescription"],
            "Dosage": ["dosage", "dose"],
            "Frequency": ["frequency", "schedule"],
        }
        
        for ai_key, patterns in field_patterns.items():
            if ai_key in referral_data and referral_data[ai_key]:
                value = str(referral_data[ai_key]).strip()
                
                # Find the best matching field
                best_match = None
                best_score = 0
                
                for field in field_metadata:
                    field_name = field["field_name"].lower()
                    nearby_text = field["nearby_text"].lower() if field["nearby_text"] else ""
                    
                    # Check if any pattern matches
                    for pattern in patterns:
                        if (re.search(pattern, field_name) or 
                            re.search(pattern, nearby_text)):
                            score = len(pattern)  # Simple scoring
                            if score > best_score:
                                best_score = score
                                best_match = field["field_name"]
                
                if best_match:
                    mapping[best_match] = value
                    self.logger.info(f"BASIC MAPPING: '{ai_key}' -> '{best_match}'")
        
        return mapping 