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
import re

load_dotenv()
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))

# --- Data Structures ---

@dataclass
class FormField:
    """Represents a single field identified on the PA form."""
    field_id: str
    page_num: int
    field_type: str  # e.g., 'text', 'checkbox', 'radio'
    context: str  # The raw text label near the field
    semantic_purpose: Optional[str] = None # To be filled by the Refinement Agent
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
    # Removing conditional rules for now to improve reliability
    # conditional_rules: List[ConditionalRule]
    
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
                response = self.model.generate_content(model_input)
                
                # 5. Parse the response and create the FormSchema object
                # This is now a text-based parsing, not JSON
                form_fields = self._parse_text_to_fields(response.text)
                
                schema = FormSchema(fields=form_fields)
                print(f"✅ Schema created successfully with {len(schema.fields)} fields.")
                return schema

            except Exception as e:
                print(f"❌ Attempt {attempt + 1}/{max_retries} failed. Reason: {e}")
                if attempt + 1 == max_retries:
                    print(f"❌ Critical Error: AI failed to create form schema after {max_retries} attempts.")
                    # Return an empty schema on final failure
                    return FormSchema(fields={})

        return FormSchema(fields={})

    def _parse_text_to_fields(self, text: str) -> Dict[str, FormField]:
        """Parses a text-based list of fields into FormField objects."""
        fields = {}
        # This regex is designed to be very forgiving
        # It looks for lines starting with a field ID, then grabs the rest
        field_entries = re.findall(r"ID: (.*?)\nContext: (.*?)\nType: (.*?)\nPage: (.*?)\n", text, re.DOTALL)
        
        for entry in field_entries:
            try:
                field_id, context, field_type, page_num_str = entry
                field_id = field_id.strip()
                page_num = int(page_num_str.strip())
                
                fields[field_id] = FormField(
                    field_id=field_id,
                    page_num=page_num,
                    field_type=field_type.strip(),
                    context=context.strip()
                )
            except (ValueError, IndexError) as e:
                print(f"⚠️ Could not parse field entry: {entry} due to {e}")
                continue
        return fields

    def _build_schema_creation_prompt(self, raw_fields: List[Dict]) -> str:
        """Constructs the detailed prompt for schema generation."""
        
        raw_fields_json = json.dumps(raw_fields, indent=2)
        
        return f"""
        You are an expert in analyzing healthcare Prior Authorization (PA) forms.
        Your task is to analyze the provided images of a PA form and the raw field data to extract the basic properties of each field.

        **1. Goal**
        Create a simple text list of all fields. For each field, provide the following on separate lines:
        - `ID: [The Field ID]`
        - `Context: [The clean, readable text label]`
        - `Type: [The field type]`
        - `Page: [The page number]`

        **2. Raw Field Data (from the PDF):**
        ```json
        {raw_fields_json}
        ```

        **3. Task**
        Generate a simple text list of all fields. For each field, provide the following on separate lines:
        - `ID: [The Field ID]`
        - `Context: [The clean, readable text label]`
        - `Type: [The field type]`
        - `Page: [The page number]`

        **Example Output:**
        ID: T.7
        Context: First Name:
        Type: text
        Page: 0

        ID: C.1.Yes
        Context: Has the patient been diagnosed with moderately to severely active Crohn's disease?
        Type: checkbox
        Page: 1
        
        Return ONLY the list of fields in this text format.
        """

class SchemaRefinementAgent:
    """Takes a raw schema and enriches it with semantic meaning."""
    def __init__(self):
        self.model = genai.GenerativeModel('gemini-2.0-flash')
        
    def refine_schema(self, schema: FormSchema) -> FormSchema:
        """Adds the `semantic_purpose` to each field in the schema."""
        print(f"🧐 Activating Schema Refinement Agent for {len(schema.fields)} fields.")
        if not schema.fields:
            return schema

        # Create a simplified list of fields for the prompt
        field_contexts = [
            {"field_id": f.field_id, "context": f.context} 
            for f in schema.fields.values()
        ]
        
        prompt = self._build_refinement_prompt(field_contexts)
        
        try:
            response = self.model.generate_content(prompt)
            
            # Update the original schema with the new semantic purposes
            refined_fields = self._parse_refinement_text(response.text)
            
            for field_id, semantic_purpose in refined_fields.items():
                if field_id in schema.fields:
                    schema.fields[field_id].semantic_purpose = semantic_purpose
            
            print("✅ Schema refined successfully.")
            return schema

        except Exception as e:
            print(f"❌ Error during Schema Refinement AI call: {e}")
            return schema # Return the original schema on failure

    def _parse_refinement_text(self, text: str) -> Dict[str, str]:
        """Parses the text output from the refinement agent."""
        refined_fields = {}
        # Regex to find "ID: [id] -> Purpose: [purpose]" lines
        matches = re.findall(r"ID: (.*?) -> Purpose: (.*?)\n", text)
        for match in matches:
            field_id, purpose = match
            refined_fields[field_id.strip()] = purpose.strip()
        return refined_fields

    def _build_refinement_prompt(self, field_contexts: List[Dict]) -> str:
        """Builds the prompt to assign semantic purpose to fields."""
        
        return f"""
        You are a schema mapping expert for an AI automation system.
        Your task is to assign a `semantic_purpose` to a list of form fields based on their context (the text labels next to them).

        **1. Goal:**
        Analyze the list of fields below. For each field, determine its purpose and assign it a `semantic_purpose` using a specific convention.

        **2. Field Naming Convention (CRITICAL):**
        You MUST use the following naming convention:
        - **For standard demographic or medical data:** Use clear, snake_case names like `patient_first_name`, `prescriber_npi`, `drug_name`.
        - **For clinical "Yes/No" or multiple-choice questions:** You MUST use the prefix `clinical_question_` followed by a summary of the question. Examples: `clinical_question_has_used_biologic`, `clinical_question_is_active_infection`, `clinical_question_patient_has_crohns_disease`.

        **3. List of Fields to Analyze:**
        ```json
        {json.dumps(field_contexts, indent=2)}
        ```

        **4. Output Format:**
        Your output MUST be a simple text list. For each field, provide a single line in the format:
        `ID: [original_field_id] -> Purpose: [assigned_semantic_purpose]`

        **Example Output:**
        ID: T.7 -> Purpose: patient_first_name
        ID: Presc_Info_T.12 -> Purpose: prescriber_npi
        ID: C.1.Yes -> Purpose: clinical_question_has_active_crohns_disease
        
        Assign a `semantic_purpose` to every field in the input list.
        Now, begin.
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

class ClinicalQAAgent:
    """A specialized agent to answer specific clinical questions from the referral packet."""
    def __init__(self):
        self.model = genai.GenerativeModel('gemini-2.0-flash')
    
    def answer_questions(self, referral_path: Path, clinical_questions: Dict[str, FormField]) -> Dict[str, Any]:
        """
        Given the referral documents and a list of clinical questions from the form schema,
        find the answers.
        """
        print(f"🩺 Activating Clinical Q&A Agent for {len(clinical_questions)} questions.")
        if not clinical_questions:
            return {}

        # This agent also needs to see the document
        doc = fitz.open(referral_path)
        page_images_b64 = []
        for page in doc:
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            page_images_b64.append(base64.b64encode(img_data).decode())
        doc.close()

        prompt = self._build_qa_prompt(clinical_questions)
        
        model_input = [prompt]
        for img_b64 in page_images_b64:
            model_input.append({"mime_type": "image/png", "data": img_b64})

        print("🤖 Asking AI to answer targeted clinical questions...")
        try:
            response = self.model.generate_content(model_input,
                generation_config=genai.types.GenerationConfig(
                    response_mime_type="application/json"
                )
            )
            answers = json.loads(response.text)
            print(f"✅ Clinical Q&A complete. Found answers for {len(answers)} questions.")
            return answers
        except Exception as e:
            print(f"❌ Error during Clinical Q&A AI call: {e}")
            return {}

    def _build_qa_prompt(self, clinical_questions: Dict[str, FormField]) -> str:
        """Constructs a prompt to answer very specific clinical questions."""
        
        question_list = {
            purpose: f.context or f.semantic_purpose 
            for purpose, f in clinical_questions.items()
        }
        
        return f"""
        You are a clinical review specialist. Your task is to answer a specific list of "Yes/No" questions based on a patient's medical records.

        **1. Your Task:**
        For each question listed below, you must carefully read the provided medical document images and determine the correct answer.

        **2. Clinical Questions to Answer:**
        ```json
        {json.dumps(question_list, indent=2)}
        ```

        **3. Rules for Answering:**
        - **Provide Direct Answers**: Your answers in the final JSON should be `true` (for Yes), `false` (for No), or `null` if the information is not found.
        - **Infer When Necessary**: Unlike simple data extraction, you may need to make logical inferences. For example, if the records show the patient is taking a biologic drug, the answer to "Has the patient used a biologic?" is `true`, even if that exact phrase isn't written.
        - **Justify Your Answers (Implicitly)**: Base your answer on the entirety of the clinical context provided.

        **4. Output Format:**
        Your output MUST be a single JSON object. The keys of this object MUST be the semantic purposes from the question list, and the values must be your answers (`true`, `false`, or `null`).

        **Example Output:**
        {{
          "clinical_question_has_used_biologic": true,
          "clinical_question_has_tb_test": true,
          "clinical_question_is_active_infection": false,
          "clinical_question_has_tried_advil": null
        }}

        Now, begin your clinical review.
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
    """Handles the mechanical process of filling the PDF."""

    def fill_form(self,
                  schema: FormSchema,
                  data_to_fill: Dict[str, Any],
                  output_path: Path,
                  base_form_path: Path, # Path to the PDF to be opened
                  is_correction: bool = False):
        """
        Fills the PDF form fields based on the provided data.
        It opens `base_form_path` and saves the result to `output_path`.
        """
        if not base_form_path.exists():
            print(f"❌ Input form not found at {base_form_path}")
            return

        doc = fitz.open(str(base_form_path))
        
        if is_correction:
            print(f"✍️ Applying corrections to existing form: {base_form_path.name}")
        else:
            print(f"✍️ Filling new form: {base_form_path.name}")

        try:
            for purpose, value in data_to_fill.items():
                # Find the field(s) with this semantic purpose
                target_fields = [f for f in schema.fields.values() if f.semantic_purpose == purpose]
                
                if not target_fields:
                    continue

                for field in target_fields:
                    try:
                        page = doc[field.page_num]
                        
                        # Correct way to find the widget
                        widget = None
                        for w in page.widgets():
                            if w.field_name == field.field_id:
                                widget = w
                                break
                        
                        if widget is None:
                            # This can happen if the field ID from the schema isn't a real widget
                            # It's a low-probability error but good to handle.
                            print(f"  ⚠️ Widget not found for field ID: {field.field_id}")
                            continue
                        
                        # Handle different field types
                        if widget.field_type == fitz.PDF_WIDGET_TYPE_CHECKBOX:
                            if isinstance(value, str) and value.lower() in ['yes', 'true', 'on']:
                                widget.field_value = True
                            elif value is True:
                                widget.field_value = True
                            else:
                                widget.field_value = False
                        
                        elif widget.field_type == fitz.PDF_WIDGET_TYPE_RADIOBUTTON:
                            if value in widget.choices:
                                widget.field_value = value
                        else: # Text fields
                            widget.field_value = str(value)
                        
                        widget.update()
                        
                    except Exception as e:
                        print(f"  ❌ Failed to fill field '{purpose}' ({field.field_id}): {e}")

            # Set the NeedAppearances flag to ensure viewers update field values
            doc.need_appearances = True
            
            # Save with garbage collection to clean up
            doc.save(str(output_path), garbage=4, deflate=True, clean=True)
            
            if is_correction:
                print("✅ Corrections applied successfully.")
            else:
                print(f"✅ Form filled and saved to: {output_path}")

        except Exception as e:
            print(f"❌ Critical Error during form filling process: {e}")
        finally:
            # Correctly check if the document is still open before closing
            if 'doc' in locals() and not doc.is_closed:
                doc.close()

class MANDOLIN_PA_SYSTEM:
    def __init__(self):
        self.form_understander = FormUnderstandingAgent()
        self.schema_refiner = SchemaRefinementAgent()
        self.data_extractor = DataExtractionAgent()
        self.clinical_qa = ClinicalQAAgent()
        self.validator = ValidationAgent()
        self.form_filler = FormFillingAgent()

    def process_pa(self, patient_name: str, referral_path: Path, pa_form_path: Path, output_dir: Path):
        """Main processing pipeline for a single patient."""
        print("="*60)
        print(f"🚀 PROCESSING PA FOR: {patient_name.upper()}")
        print("="*60 + "\n")

        # Ensure output directory exists
        output_dir.mkdir(exist_ok=True)

        # 1. Understand and Refine Schema
        raw_schema = self.form_understander.create_schema(pa_form_path)
        if not raw_schema.fields:
            print("❌ Halting process due to schema creation failure.")
            return

        schema = self.schema_refiner.refine_schema(raw_schema)

        # 2. Extract Data
        extracted_data = self.data_extractor.extract_data(referral_path, schema)

        # 3. Clinical Q&A
        clinical_questions = {k: v for k, v in schema.fields.items() if v.semantic_purpose and v.semantic_purpose.startswith("clinical_question_")}
        if clinical_questions:
            clinical_answers = self.clinical_qa.answer_questions(referral_path, clinical_questions)
            extracted_data.data.update(clinical_answers)

        # 4. First Pass: Fill the form
        temp_output_path = output_dir / f"{patient_name}_PA_filled_v1.pdf"
        self.form_filler.fill_form(
            schema=schema,
            data_to_fill=extracted_data.data,
            output_path=temp_output_path,
            base_form_path=pa_form_path,
            is_correction=False
        )

        # 5. Validation and Correction Loop
        final_output_path = output_dir / f"{patient_name}_PA_filled.pdf"
        corrections = self.validator.validate_and_correct(temp_output_path, schema, extracted_data)

        if corrections:
            print(f"✍️ Applying {len(corrections)} corrections...")
            correction_data = {c.semantic_purpose: c.correct_value for c in corrections}
            
            self.form_filler.fill_form(
                schema=schema, 
                data_to_fill=correction_data, 
                output_path=final_output_path,
                base_form_path=temp_output_path, # Use the v1 form as the base
                is_correction=True
            )
        else:
            print("✅ No corrections needed. Finalizing document.")
            # If no corrections, the v1 file is the final one
            if temp_output_path.exists():
                temp_output_path.rename(final_output_path)

        # 6. Generate final report
        self.generate_report(patient_name, schema, extracted_data, output_dir)
        
        print(f"\n🎉 AUTOMATION COMPLETE FOR {patient_name.upper()}\n")

    def generate_report(self, patient_name: str, schema: FormSchema, extracted_data: ExtractedData, output_dir: Path):
        """Generates a markdown report of the automation process."""
        report_path = output_dir / f"{patient_name}_processing_report.md"
        # Basic report, can be improved
        with open(report_path, 'w') as f:
            f.write(f"# PA Processing Report for {patient_name}\n")
            f.write(f"Generated on: {datetime.datetime.now()}\n\n")
            f.write(f"## Form Schema Summary\n")
            f.write(f"- Identified {len(schema.fields)} fields.\n")
            f.write(f"## Extraction Summary\n")
            f.write(f"- Extracted {len(extracted_data.data)} data points.\n")
        print(f"📄 Report generated at {report_path}")

def main():
    """Main function to run the Mandolin PA System."""
    print("🏥 MANDOLIN PRIOR AUTHORIZATION AUTOMATION SYSTEM 🏥")
    print("="*60)

    system = MANDOLIN_PA_SYSTEM()
    output_dir = Path("Output Data")
    output_dir.mkdir(exist_ok=True)

    patients_to_process = ["Akshay", "Adbulla"]

    for patient_name in patients_to_process:
        print(f"\n\n--- Starting processing for patient: {patient_name.upper()} ---")
        patient_dir = Path(f"Input Data/{patient_name}")
        
        # Handle case-sensitive PA form names
        if (patient_dir / "PA.pdf").exists():
            pa_path = patient_dir / "PA.pdf"
        elif (patient_dir / "pa.pdf").exists():
            pa_path = patient_dir / "pa.pdf"
        else:
            print(f"❌ PA form not found for patient {patient_name}")
            continue

        referral_path = patient_dir / "referral_package.pdf"
        
        if referral_path.exists():
            system.process_pa(patient_name, referral_path, pa_path, output_dir)
        else:
            print(f"❌ Referral package not found for patient {patient_name}")

if __name__ == "__main__":
    main()