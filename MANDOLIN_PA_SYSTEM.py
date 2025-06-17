#!/usr/bin/env python3
"""
MANDOLIN PA AUTOMATION SYSTEM
An agent-based system to handle dynamic, conditional, and complex PA forms.
This system is designed to be universal and handle any PA form for any drug.
"""

import json
import fitz
import base64
from pathlib import Path
import google.generativeai as genai
from dotenv import load_dotenv
import os
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import datetime

load_dotenv()
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))

# --- Data Structures ---

@dataclass
class FormField:
    """Represents a single field identified on the PA form."""
    field_id: str
    page_num: int
    field_type: str  # e.g., 'text', 'checkbox', 'radio'
    semantic_purpose: str  # e.g., 'patient_first_name', 'diagnosis_code'
    options: List[str] = field(default_factory=list)  # For checkboxes/radios
    
@dataclass
class ConditionalRule:
    """Represents a conditional logic rule between fields."""
    primary_field: str
    primary_value: Any
    action: str  # e.g., 'DISABLE', 'ENABLE', 'REQUIRE'
    target_fields: List[str]

@dataclass
class FormSchema:
    """A structured representation of the entire PA form."""
    fields: Dict[str, FormField]
    conditional_rules: List[ConditionalRule]
    
@dataclass
class ExtractedData:
    """Structured data extracted from referral documents, keyed by semantic purpose."""
    data: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Correction:
    """Represents a single correction to be made to the form."""
    field_id: str
    semantic_purpose: str
    correct_value: Any
    reason: str

# --- Agent Components ---

class FormUnderstandingAgent:
    """Analyzes a blank PA form to create a structured schema."""
    
    def __init__(self):
        # Using a more powerful model for complex reasoning
        self.model = genai.GenerativeModel('gemini-2.0-flash')

    def create_schema(self, pa_form_path: Path) -> FormSchema:
        """
        Analyzes the PA form and generates a complete schema.
        This is the most critical step for universality.
        """
        print(f"🧠 Activating Form Understanding Agent for: {pa_form_path.name}")
        
        doc = fitz.open(pa_form_path)
        
        # 1. Get all raw field information from the PDF
        raw_fields = []
        for page_num, page in enumerate(doc):
            for widget in page.widgets():
                field_info = {
                    "id": widget.field_name,
                    "type": widget.field_type_string,
                    "rect": [widget.rect.x0, widget.rect.y0, widget.rect.x1, widget.rect.y1],
                    "page": page_num
                }
                raw_fields.append(field_info)

        # 2. Convert all pages to images for the vision model
        page_images_b64 = []
        for page in doc:
            mat = fitz.Matrix(2.0, 2.0)  # 2x resolution
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            page_images_b64.append(base64.b64encode(img_data).decode())
        
        doc.close()

        # 3. Build the prompt for the multi-modal model
        prompt = self._build_schema_creation_prompt(raw_fields)
        
        # 4. Call the model with the prompt and all page images
        model_input = [prompt]
        for img_b64 in page_images_b64:
            model_input.append({"mime_type": "image/png", "data": img_b64})
            
        print("🤖 Asking AI to analyze form structure and logic...")

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.model.generate_content(model_input,
                    generation_config=genai.types.GenerationConfig(
                        response_mime_type="application/json"
                    )
                )
                
                # 5. Parse the response and create the FormSchema object
                schema_json = json.loads(response.text)
                
                form_fields = {
                    f['field_id']: FormField(**f) 
                    for f in schema_json.get('fields', [])
                }
                
                conditional_rules = [
                    ConditionalRule(**r)
                    for r in schema_json.get('conditional_rules', [])
                ]
                
                schema = FormSchema(fields=form_fields, conditional_rules=conditional_rules)
                print(f"✅ Schema created successfully with {len(schema.fields)} fields and {len(schema.conditional_rules)} rules.")
                return schema

            except Exception as e:
                print(f"❌ Attempt {attempt + 1}/{max_retries} failed. Reason: {e}")
                if attempt + 1 == max_retries:
                    print(f"❌ Critical Error: AI failed to create form schema after {max_retries} attempts.")
                    # Return an empty schema on final failure
                    return FormSchema(fields={}, conditional_rules=[])
                print("Retrying...")

        return FormSchema(fields={}, conditional_rules=[]) # Should not be reached

    def _build_schema_creation_prompt(self, raw_fields: List[Dict]) -> str:
        """Constructs the detailed prompt for schema generation."""
        
        raw_fields_json = json.dumps(raw_fields, indent=2)
        
        return f"""
        You are an expert in analyzing healthcare Prior Authorization (PA) forms.
        Your task is to analyze the provided images of a PA form and the raw field data extracted from the PDF.
        Create a structured JSON schema that describes the form's fields and their relationships.

        **Step 1: Understand the Goal**
        The goal is to create a JSON object representing the form's structure so that a different AI can use it to (1) know what information to look for in a patient's medical records and (2) know how to fill out the form correctly, including handling conditional logic.

        **Step 2: Analyze the Form Fields**
        Here is a JSON list of all the interactive form fields detected in the PDF. Use this as your ground-truth for field IDs.
        ```json
        {raw_fields_json}
        ```

        **Step 3: Create the JSON Schema**
        Based on the images and the field data, generate a single JSON object with two main keys: "fields" and "conditional_rules".

        **"fields" Key:**
        This should be a list of objects, where each object represents a single form field. For each field, provide:
        - `field_id`: (string) The exact ID of the field from the raw data (e.g., "T.7", "Presc Info T.1"). THIS IS CRITICAL.
        - `page_num`: (integer) The page number the field is on.
        - `field_type`: (string) The type of the field. Use one of: 'text', 'checkbox', 'radio', 'dropdown', 'signature'.
        - `semantic_purpose`: (string) This is the MOST IMPORTANT part. Describe what the field is for using a consistent snake_case convention. Examples: 'patient_first_name', 'patient_dob', 'insurance_member_id', 'drug_name', 'diagnosis_code_icd10', 'clinical_question_previous_medications'.
        - `options`: (list of strings, OPTIONAL) If the field is a checkbox or radio button, list the possible options. For example, for a "Yes/No" question, this would be `["Yes", "No"]`.

        **"conditional_rules" Key:**
        This should be a list of objects, where each object defines a rule governing field interactions.
        - `primary_field`: (string) The ID of the field that triggers the rule.
        - `primary_value`: (string/boolean) The value of the primary field that activates the rule (e.g., "Yes", true).
        - `action`: (string) The action to take. Use one of: 'DISABLE' (the target fields cannot be filled), 'ENABLE' (the target fields can now be filled), 'REQUIRE' (the target fields must be filled).
        - `target_fields`: (list of strings) A list of the field IDs that are affected by this rule.

        **Example of a Conditional Rule:**
        If checking a box named "has_allergies_yes" (semantic_purpose: 'has_allergies', option: 'Yes') makes a text field "allergies_details" appear, the rule would be:
        `{{ "primary_field": "has_allergies_yes", "primary_value": true, "action": "REQUIRE", "target_fields": ["allergies_details"] }}`

        If there are two radio buttons for a question, "q1_yes" and "q1_no", they are mutually exclusive. You can represent this with two rules:
        `{{ "primary_field": "q1_yes", "primary_value": true, "action": "DISABLE", "target_fields": ["q1_no"] }}`
        `{{ "primary_field": "q1_no", "primary_value": true, "action": "DISABLE", "target_fields": ["q1_yes"] }}`

        **Final Instructions:**
        - Be meticulous. The accuracy of this schema is critical for the entire automation process.
        - Use ONLY the field IDs provided in the raw data JSON. Do not invent new ones.
        - The `semantic_purpose` should be descriptive and consistent.
        - Return ONLY the final JSON object, and nothing else.
        """

class DataExtractionAgent:
    """Extracts required information from referral packets based on a form schema."""
    
    def __init__(self):
        self.model = genai.GenerativeModel('gemini-2.0-flash')

    def extract_data(self, referral_path: Path, schema: FormSchema) -> ExtractedData:
        """
        Performs targeted extraction from the referral packet.
        It only looks for the information needed by the form schema.
        """
        print(f"🔎 Activating Data Extraction Agent for: {referral_path.name}")

        if not schema.fields:
            print("⚠️ Warning: Form schema is empty. Skipping extraction.")
            return ExtractedData()

        # 1. Convert referral document to images
        doc = fitz.open(referral_path)
        page_images_b64 = []
        for page in doc:
            mat = fitz.Matrix(2.0, 2.0)  # 2x resolution
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            page_images_b64.append(base64.b64encode(img_data).decode())
        doc.close()

        # 2. Build the targeted extraction prompt
        prompt = self._build_extraction_prompt(schema)
        
        # 3. Call the model with the prompt and all page images
        model_input = [prompt]
        for img_b64 in page_images_b64:
            model_input.append({"mime_type": "image/png", "data": img_b64})
            
        print("🤖 Asking AI to perform targeted data extraction...")
        try:
            response = self.model.generate_content(model_input,
                generation_config=genai.types.GenerationConfig(
                    response_mime_type="application/json"
                )
            )
            
            # 4. Parse the response and create the ExtractedData object
            extracted_json = json.loads(response.text)
            extracted_data = ExtractedData(data=extracted_json)
            
            print(f"✅ Targeted data extracted for {len(extracted_data.data)} fields.")
            return extracted_data

        except Exception as e:
            print(f"❌ Critical Error: AI failed to extract data. Reason: {e}")
            return ExtractedData()

    def _build_extraction_prompt(self, schema: FormSchema) -> str:
        """Constructs a targeted prompt to extract only necessary data."""
        
        desired_fields = {}
        for field in schema.fields.values():
            desired_fields[field.semantic_purpose] = f"Description: The information needed for the form field labeled '{field.semantic_purpose}'. This could be a date, name, diagnosis, answer to a clinical question, etc."

        desired_fields_json = json.dumps(desired_fields, indent=2)

        return f"""
        You are a medical data extraction specialist. Your task is to analyze the provided images of a patient's referral packet and extract specific pieces of information needed to fill out a Prior Authorization form.

        **Step 1: Understand the Goal**
        You have been given a "shopping list" of required information, defined in the JSON object below. For each key in the JSON, you must find the corresponding value in the provided documents.

        **Step 2: This is the Information You Must Find**
        The keys of this JSON object are the `semantic_purpose` of each field on the form. Find the value for each.
        ```json
        {desired_fields_json}
        ```

        **Step 3: Extraction Rules**
        1.  **Accuracy is Paramount**: Only extract information that is clearly present in the documents. DO NOT INFER, GUESS, OR MAKE UP a value if it's not there.
        2.  **Handle Bad Handwriting**: Do your best to interpret handwritten notes.
        3.  **Use `null` for Missing Information**: If you cannot find a piece of information for a specific key, you MUST return `null` for that key. Do not omit the key.
        4.  **Format Correctly**: For dates, use MM/DD/YYYY format. For names, preserve the exact spelling.
        5.  **Distinguish Patient vs. Provider**: Pay close attention to context to avoid mixing up patient information with prescriber information.

        **Step 4: Generate the Final JSON Output**
        Your final output must be a single JSON object. The keys of this object MUST be the `semantic_purpose` strings from the "shopping list" above. The values will be the data you extracted from the documents.

        Example Output Format:
        {{
            "patient_first_name": "John",
            "patient_last_name": "Doe",
            "diagnosis_code_icd10": "M54.5",
            "clinical_question_has_tried_other_meds": "Yes",
            "prescriber_npi": null  // Example of missing information
        }}

        Return ONLY the final JSON object.
        """

class ValidationAgent:
    """Analyzes a filled form to identify errors and propose corrections."""
    def __init__(self):
        self.model = genai.GenerativeModel('gemini-2.0-flash')

    def validate_and_correct(self, 
                             filled_form_path: Path, 
                             schema: FormSchema, 
                             extracted_data: ExtractedData) -> List[Correction]:
        """
        Looks at the filled form and compares it to the source data,
        identifying mistakes and proposing a list of corrections.
        """
        print(f"🕵️ Activating Validation Agent for: {filled_form_path.name}")
        
        if not filled_form_path.exists():
            print("❌ Validation failed: Filled form PDF not found.")
            return []

        # 1. Convert filled PDF to image for analysis
        doc = fitz.open(filled_form_path)
        page_images_b64 = []
        for page in doc:
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            page_images_b64.append(base64.b64encode(img_data).decode())
        doc.close()

        # 2. Build the validation prompt
        prompt = self._build_validation_prompt(schema, extracted_data)

        # 3. Call the model
        model_input = [prompt]
        for img_b64 in page_images_b64:
            model_input.append({"mime_type": "image/png", "data": img_b64})

        print("🤖 Asking AI to audit the filled form...")
        try:
            response = self.model.generate_content(model_input,
                generation_config=genai.types.GenerationConfig(
                    response_mime_type="application/json"
                )
            )
            
            corrections_json = json.loads(response.text)
            corrections = [Correction(**c) for c in corrections_json.get('corrections', [])]
            
            print(f"✅ Validation complete. Found {len(corrections)} potential corrections.")
            return corrections

        except Exception as e:
            print(f"❌ Error during validation AI call: {e}")
            return []

    def _build_validation_prompt(self, schema: FormSchema, extracted_data: ExtractedData) -> str:
        """Constructs the prompt for the validation agent."""

        schema_dict = {fid: f.__dict__ for fid, f in schema.fields.items()}

        return f"""
        You are a meticulous quality assurance auditor for a healthcare automation company.
        Your task is to review a PA form that has been filled out by an AI and identify any errors.

        You will be given three pieces of information:
        1.  The `Form Schema`: A JSON description of what each field on the form means.
        2.  The `Extracted Data`: The ground-truth information extracted from the patient's medical records.
        3.  The `Filled Form Images`: Images of the actual PDF form after the AI filled it out.

        Your job is to find mismatches, empty fields that should be filled, and data placed in the wrong fields.

        **1. Form Schema:**
        ```json
        {json.dumps(schema_dict, indent=2)}
        ```

        **2. Extracted Data (Ground Truth):**
        ```json
        {json.dumps(extracted_data.data, indent=2)}
        ```

        **3. Analysis Task:**
        Carefully examine the `Filled Form Images`. For every field defined in the `Form Schema`, perform the following checks:
        - **Check for Mismatches**: Does the value visible in the form image for a field (e.g., 'prescriber_zip') match the corresponding value in the `Extracted Data`?
        - **Check for Hallucinations**: Is there data in a field on the form that doesn't belong there? For example, is a ZIP code in an email field?
        - **Check for Missing Data**: Is a field on the form empty, even though you have the data for it in the `Extracted Data`? (e.g., the NPI field is blank, but you have the NPI number).
        - **Check for Incorrect Checkboxes/Radios**: Based on the `Extracted Data`, is the correct checkbox or radio button selected? For example, if the extracted 'prescriber_specialty' is 'Gastroenterologist', ensure that specific box is checked.

        **4. Output Format:**
        Your output MUST be a JSON object containing a single key, "corrections". This key should hold a list of objects, where each object represents a single error you found.
        For each correction, provide:
        - `field_id`: (string) The ID of the field that needs to be corrected (from the schema).
        - `semantic_purpose`: (string) The semantic purpose of the field (from the schema).
        - `correct_value`: (string/boolean) The correct value that SHOULD be in the field.
        - `reason`: (string) A brief explanation of why this is a correction (e.g., "Field was empty but data was available," or "Incorrect value found in field; was '20176' but should be 'Intake@thealth.com'").

        **Example Output:**
        {{
          "corrections": [
            {{
              "field_id": "Presc_Info_T.6",
              "semantic_purpose": "prescriber_zip",
              "correct_value": "20176",
              "reason": "Field was empty but data was available."
            }},
            {{
              "field_id": "Presc_Info_T.12",
              "semantic_purpose": "prescriber_npi",
              "correct_value": "1331124163",
              "reason": "Field was empty, but found NPI number in extracted data."
            }},
            {{
              "field_id": "Specialty.Check.1",
              "semantic_purpose": "prescriber_specialty_gastroenterologist",
              "correct_value": true,
              "reason": "Checkbox was not checked despite specialty matching."
            }}
          ]
        }}
        
        If you find no errors, return an empty list: `{{ "corrections": [] }}`.
        Now, begin your audit.
        """

class FormFillingAgent:
    """Fills the PA form using the schema and extracted data, handling logic."""

    def fill_form(self, 
                  pa_form_path: Path, 
                  schema: FormSchema, 
                  data_to_fill: Dict[str, Any], 
                  output_path: Path,
                  is_correction: bool = False):
        """
        Fills the PDF form. Can be used for initial fill or for applying corrections.
        """
        if is_correction:
            print(f"✍️ Applying corrections to: {output_path.name}")
        else:
            print(f"✍️ Activating Form Filling Agent for: {output_path.name}")

        # If it's a correction, we work on the existing file. Otherwise, create a new one.
        if is_correction and pa_form_path.exists():
            doc = fitz.open(pa_form_path)
        elif not is_correction and pa_form_path.exists():
            doc = fitz.open(pa_form_path)
        else:
            print("❌ Source PDF not found.")
            return

        filled_count = 0
        
        # Create a map of semantic purpose to field object for easy lookup
        purpose_to_field_map: Dict[str, FormField] = {
            field.semantic_purpose: field for field in schema.fields.values()
        }

        for purpose, value in data_to_fill.items():
            if value is None or value == 'null':
                continue

            if purpose in purpose_to_field_map:
                field = purpose_to_field_map[purpose]
                page = doc[field.page_num]
                
                # Correctly find the widget by iterating
                widget = None
                for w in page.widgets():
                    if w.field_name == field.field_id:
                        widget = w
                        break

                if not widget:
                    print(f"  ❌ Could not find widget for field ID: {field.field_id} on page {field.page_num}")
                    continue

                try:
                    # Update widget value
                    if field.field_type in ('text', 'dropdown'):
                        widget.field_value = str(value)
                    elif field.field_type == 'checkbox':
                        widget.field_value = bool(value)
                    elif field.field_type == 'radio':
                        # For radio buttons, the name refers to the group. We need to select the right option.
                        if widget.field_value == value:
                             widget.field_value = True

                    widget.update()
                    print(f"  ✅ Filled '{purpose}': {str(value)}")
                    filled_count += 1
                except Exception as e:
                    print(f"  ❌ Failed to fill field '{purpose}' ({field.field_id}): {e}")

        doc.save(str(output_path), garbage=4, deflate=True, clean=True)
        doc.close()
        
        if is_correction:
            print(f"✅ Corrections applied. Final PDF saved to {output_path}")
        else:
            print(f"✅ Initial form filled with {filled_count} data points and saved to {output_path}")


# --- Main Orchestrator ---

class MandolinPASystem:
    """Orchestrates the PA automation process using specialized agents."""

    def __init__(self):
        self.understanding_agent = FormUnderstandingAgent()
        self.extraction_agent = DataExtractionAgent()
        self.validation_agent = ValidationAgent()
        self.filling_agent = FormFillingAgent()

    def process_pa(self, patient_name: str, referral_path: Path, pa_form_path: Path, output_dir: Path):
        """
        Runs the end-to-end automated PA process for a single patient.
        """
        print(f"\n{'='*60}")
        print(f"🚀 PROCESSING PA FOR: {patient_name.upper()}")
        print(f"{'='*60}\n")

        # Step 1: Understand the form's structure and logic
        form_schema = self.understanding_agent.create_schema(pa_form_path)

        # Step 2: Extract only the necessary data from the referral packet
        extracted_data = self.extraction_agent.extract_data(referral_path, form_schema)

        # Step 3: Perform initial form fill
        temp_output_path = output_dir / f"{patient_name}_PA_filled_v1.pdf"
        self.filling_agent.fill_form(pa_form_path, form_schema, extracted_data.data, temp_output_path)

        # Step 4: Validate the filled form and generate corrections
        corrections = self.validation_agent.validate_and_correct(temp_output_path, form_schema, extracted_data)

        # Step 5: Apply corrections to generate the final version
        final_output_path = output_dir / f"{patient_name}_PA_filled.pdf"
        if corrections:
            # Create a dictionary of corrections to pass to the filling agent
            correction_data = {c.semantic_purpose: c.correct_value for c in corrections}
            # The source for corrections is the v1 filled form
            self.filling_agent.fill_form(temp_output_path, form_schema, correction_data, final_output_path, is_correction=True)
        else:
            # If no corrections, the v1 is the final version
            print("✅ No corrections needed. Finalizing document.")
            import shutil
            shutil.copy(temp_output_path, final_output_path)

        # Clean up the temporary file
        if temp_output_path.exists():
            temp_output_path.unlink()

        # Step 6: Generate a report (can be enhanced)
        self.generate_report(patient_name, form_schema, extracted_data, output_dir)
        
        print(f"\n🎉 AUTOMATION COMPLETE FOR {patient_name.upper()}")

    def generate_report(self, patient_name: str, schema: FormSchema, extracted_data: ExtractedData, output_dir: Path):
        report_path = output_dir / f"{patient_name}_processing_report.md"
        # Basic report, can be improved
        with open(report_path, 'w') as f:
            f.write(f"# PA Processing Report for {patient_name}\n")
            f.write(f"Generated on: {datetime.datetime.now()}\n\n")
            f.write(f"## Form Schema Summary\n")
            f.write(f"- Identified {len(schema.fields)} fields.\n")
            f.write(f"- Identified {len(schema.conditional_rules)} conditional rules.\n\n")
            f.write(f"## Extraction Summary\n")
            f.write(f"- Extracted {len(extracted_data.data)} data points.\n")
        print(f"📄 Report generated at {report_path}")


def main():
    """Main function to run the Mandolin PA System."""
    print("🏥 MANDOLIN PRIOR AUTHORIZATION AUTOMATION SYSTEM 🏥")
    print("="*60)

    system = MandolinPASystem()
    output_dir = Path("output_mandolin")
    output_dir.mkdir(exist_ok=True)

    # This can be expanded to process a directory of patients
    patient_dir = Path("Input Data/Akshay")
    patient_name = "Akshay"
    referral_path = patient_dir / "referral_package.pdf"
    pa_path = patient_dir / "pa.pdf"

    if referral_path.exists() and pa_path.exists():
        system.process_pa(patient_name, referral_path, pa_path, output_dir)
    else:
        print(f"❌ Critical files not found for patient {patient_name} in {patient_dir}")

if __name__ == "__main__":
    main() 