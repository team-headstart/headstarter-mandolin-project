import PyPDF2
import re
from datetime import datetime
import pytesseract
from pdf2image import convert_from_path
import tempfile
import os
import fitz 
import json

class PDFFormExtractor:
    def __init__(self):
        pass  # No hardcoded fields!

    def _validate_file_path(self, file_path):
        """Validate if file exists and is accessible"""
        # Normalize path by replacing backslashes with forward slashes
        normalized_path = file_path.replace('\\', '/')
        
        if not os.path.exists(normalized_path):
            raise FileNotFoundError(f"File not found: {normalized_path}")
        
        if not os.access(normalized_path, os.R_OK):
            raise PermissionError(f"No permission to read file: {normalized_path}")
            
        return normalized_path

    def extract_data_from_pdf(self, pdf_path):
        """
        Extract required data from a PDF document
        """
        try:
            # Validate and normalize file path
            pdf_path = self._validate_file_path(pdf_path)
            
            # Convert PDF to images for OCR
            try:
                images = convert_from_path(pdf_path)
            except Exception as e:
                raise Exception(f"Failed to convert PDF to images: {str(e)}")
            
            text = ""
            
            # Extract text from each page
            for i, image in enumerate(images):
                # Save image temporarily
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
                    image.save(temp_file.name, 'PNG')
                    temp_path = temp_file.name
                
                try:
                    # Use OCR to extract text
                    page_text = pytesseract.image_to_string(image)
                    text += page_text + "\n"
                except Exception as e:
                    print(f"Warning: Failed to extract text from page {i+1}: {str(e)}")
                finally:
                    # Clean up temporary file
                    try:
                        os.unlink(temp_path)
                    except Exception as e:
                        print(f"Warning: Failed to delete temporary file: {str(e)}")

            if not text.strip():
                raise Exception("No text could be extracted from the PDF")

            # Extract required information using regex patterns
            self._extract_patient_info(text)
            self._extract_treatment_dates(text)
            self._extract_insurance_info(text)

            return self.required_fields

        except Exception as e:
            raise Exception(f"Error extracting data from PDF: {str(e)}")

    def _extract_patient_info(self, text):
        """Extract patient name and address information"""
        # Extract first and last name - updated pattern to match "Abdulla, Shakh" format
        name_pattern = r"(?i)(?:patient\s*name|patient\s*information):?\s*([A-Za-z]+),\s*([A-Za-z]+)"
        name_match = re.search(name_pattern, text)
        if name_match:
            self.required_fields['patient_last_name'] = name_match.group(1)
            self.required_fields['patient_first_name'] = name_match.group(2)
        else:
            # Try alternative pattern for name in text
            alt_name_pattern = r"(?i)([A-Za-z]+),\s*([A-Za-z]+)\s*(?:\(MR\s*#|DOB:)"
            alt_match = re.search(alt_name_pattern, text)
            if alt_match:
                self.required_fields['patient_last_name'] = alt_match.group(1)
                self.required_fields['patient_first_name'] = alt_match.group(2)

        # Extract address - updated pattern to match full address format
        address_pattern = r"(?i)address:?\s*(\d+\s+[A-Za-z\s]+(?:Avenue|Ave|Street|St|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Place|Pl|Court|Ct|Circle|Cir|Way|Terrace|Ter)[,\s]+[A-Za-z\s]+(?:[A-Z]{2})?\s+\d{5}(?:-\d{4})?)"
        address_match = re.search(address_pattern, text)
        if address_match:
            self.required_fields['patient_address'] = address_match.group(1).strip()
        else:
            # Try alternative pattern for address in text
            alt_address_pattern = r"(?i)(\d+\s+[A-Za-z\s]+(?:Avenue|Ave|Street|St|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Place|Pl|Court|Ct|Circle|Cir|Way|Terrace|Ter)[,\s]+[A-Za-z\s]+(?:[A-Z]{2})?\s+\d{5}(?:-\d{4})?)"
            alt_address_match = re.search(alt_address_pattern, text)
            if alt_address_match:
                self.required_fields['patient_address'] = alt_address_match.group(1).strip()

        # Extract MRN (Medical Record Number) as insurance member ID
        mrn_pattern = r"(?i)(?:MRN|MR\s*#?):?\s*(\d+)"
        mrn_match = re.search(mrn_pattern, text)
        if mrn_match:
            self.required_fields['insurance_member_id'] = mrn_match.group(1)
        else:
            # Try alternative pattern for MRN in parentheses
            alt_mrn_pattern = r"(?i)\(MR\s*#\s*(\d+)\)"
            alt_mrn_match = re.search(alt_mrn_pattern, text)
            if alt_mrn_match:
                self.required_fields['insurance_member_id'] = alt_mrn_match.group(1)

    def _extract_treatment_dates(self, text):
        """Extract treatment dates"""
        # Extract start of treatment from medication orders
        start_pattern = r"(?i)(?:starting|start)\s*(?:when|on|date)?:?\s*(\d{1,2}/\d{1,2}/\d{2,4})"
        start_match = re.search(start_pattern, text)
        if start_match:
            self.required_fields['start_of_treatment'] = self._parse_date(start_match.group(1))
        else:
            # Try alternative pattern for electronic signature date
            alt_start_pattern = r"(?i)electronically\s+signed\s+by.*?on\s+(\d{1,2}/\d{1,2}/\d{2,4})"
            alt_start_match = re.search(alt_start_pattern, text)
            if alt_start_match:
                self.required_fields['start_of_treatment'] = self._parse_date(alt_start_match.group(1))

        # Extract last treatment date
        last_pattern = r"(?i)(?:last|final)\s*(?:treatment|released|administered)?\s*(?:date|on)?:?\s*(\d{1,2}/\d{1,2}/\d{2,4})"
        last_match = re.search(last_pattern, text)
        if last_match:
            self.required_fields['last_treatment_date'] = self._parse_date(last_match.group(1))
        else:
            # Try alternative pattern for "Last released" format
            alt_last_pattern = r"(?i)last\s+released:?\s*(\d{1,2}/\d{1,2}/\d{2,4})"
            alt_last_match = re.search(alt_last_pattern, text)
            if alt_last_match:
                self.required_fields['last_treatment_date'] = self._parse_date(alt_last_match.group(1))

    def _extract_insurance_info(self, text):
        """Extract insurance information"""
        # Extract member ID (MRN) if not already found
        if not self.required_fields['insurance_member_id']:
            member_id_pattern = r"(?i)(?:MRN|MR\s*#?):?\s*(\d+)"
            member_id_match = re.search(member_id_pattern, text)
            if member_id_match:
                self.required_fields['insurance_member_id'] = member_id_match.group(1)

        # Extract group number
        group_pattern = r"(?i)(?:group|plan)\s*(?:number|#)?:?\s*([A-Za-z0-9-]+)"
        group_match = re.search(group_pattern, text)
        if group_match:
            self.required_fields['insurance_group'] = group_match.group(1)
        else:
            # Try alternative pattern for insurance information
            alt_group_pattern = r"(?i)(?:insurance|coverage)\s*(?:group|plan)?:?\s*([A-Za-z0-9-]+)"
            alt_group_match = re.search(alt_group_pattern, text)
            if alt_group_match:
                self.required_fields['insurance_group'] = alt_group_match.group(1)

    def _parse_date(self, date_str):
        """Parse date string into a standardized format"""
        try:
            # Try different date formats
            for fmt in ['%m/%d/%Y', '%m-%d-%Y', '%m/%d/%y', '%m-%d-%y']:
                try:
                    return datetime.strptime(date_str, fmt).strftime('%m/%d/%Y')
                except ValueError:
                    continue
            return date_str
        except Exception:
            return date_str

    def fill_pdf_form(self, input_pdf, output_pdf, field_values):
        doc = fitz.open(input_pdf)
        for page in doc:
            widgets = page.widgets()
            if not widgets:
                continue
            for widget in widgets:
                field_name = widget.field_name
                if field_name in field_values:
                    rect = widget.rect
                    widget.delete()
                    page.insert_textbox(
                        rect,
                        str(field_values[field_name]),
                        fontsize=12,
                        fontname="helv",
                        color=(0, 0, 0),
                        align=fitz.TEXT_ALIGN_LEFT,
                    )
        doc.save(output_pdf)

def debug_extraction_and_fields(source_pdf, template_pdf):
    """
    Print the full OCR-extracted text from the source PDF and all form field names from the template PDF.
    """
    print("\n--- DEBUG: OCR-Extracted Text from Source PDF ---")
    try:
        images = convert_from_path(source_pdf)
        text = ""
        for i, image in enumerate(images):
            page_text = pytesseract.image_to_string(image)
            print(f"\n[Page {i+1}]\n{text}")
            text += page_text + "\n"
        print("\n--- END OF OCR TEXT ---\n")
    except Exception as e:
        print(f"Error extracting text from {source_pdf}: {e}")

    print("\n--- DEBUG: PDF Form Field Names in Template PDF ---")
    try:
        doc = fitz.open(template_pdf)
        for page_num, page in enumerate(doc, 1):
            widgets = page.widgets()
            if widgets:
                for widget in widgets:
                    print(f"Page {page_num}: Field Name = '{widget.field_name}'")
        print("--- END OF FIELD NAMES ---\n")
    except Exception as e:
        print(f"Error reading form fields from {template_pdf}: {e}")

def get_template_field_names(template_pdf):
    doc = fitz.open(template_pdf)
    field_names = set()
    for page in doc:
        widgets = page.widgets()
        if widgets:
            for widget in widgets:
                if widget.field_name:
                    field_names.add(widget.field_name)
    return list(field_names)

def extract_text_from_pdf(pdf_path):
    images = convert_from_path(pdf_path)
    text = ""
    for image in images:
        text += pytesseract.image_to_string(image) + "\n"
    return text

def extract_field_values_from_text(field_names, text):
    # This is a naive implementation. You should customize the regex for your forms.
    field_values = {}
    for field in field_names:
        # Try to find a line that contains the field name (case-insensitive)
        pattern = rf"{field}[:\s]+(.+)"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            # Optionally, clean up value (remove trailing junk, etc.)
            field_values[field] = value
        else:
            field_values[field] = ""  # Or None
    return field_values

def extract_data_according_to_template(source_pdf, template_pdf):
    field_names = get_template_field_names(template_pdf)
    text = extract_text_from_pdf(source_pdf)
    field_values = extract_field_values_from_text(field_names, text)
    return field_values

def extract_template_to_json(template_pdf, output_json):
    doc = fitz.open(template_pdf)
    fields = []
    for page_num, page in enumerate(doc, 1):
        widgets = page.widgets()
        if widgets:
            for widget in widgets:
                field_info = {
                    "field_name": widget.field_name,
                    "question": widget.field_name,  # You can improve this by prettifying or mapping
                    "type": widget.field_type if hasattr(widget, "field_type") else "text",
                    "page": page_num
                }
                fields.append(field_info)
    with open(output_json, "w") as f:
        json.dump(fields, f, indent=2)
    print(f"Extracted template schema to {output_json}")

def main():
    try:
        source_pdf = "source.pdf"
        template_pdf = "template.pdf"
        output_pdf = "filled_form.pdf"

        # Extract data dynamically
        extracted_data = extract_data_according_to_template(source_pdf, template_pdf)
        print("Extracted data:", extracted_data)

        # Fill the form
        extractor = PDFFormExtractor()
        extractor.fill_pdf_form(template_pdf, output_pdf, extracted_data)
        print(f"Form filled successfully. Output saved to: {output_pdf}")

    except Exception as e:
        print(f"Error: {str(e)}")
        return 1
    return 0

if __name__ == "__main__":
    exit(main()) 