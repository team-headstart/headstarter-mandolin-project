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
    
    def to_dict(self):
        return {
            "field_id": self.field_id,
            "page_num": self.page_num,
            "field_type": self.field_type,
            "context": self.context,
            "semantic_purpose": self.semantic_purpose,
            "options": self.options,
        }

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
    
    def to_dict(self):
        return {
            "fields": {field_id: field.to_dict() for field_id, field in self.fields.items()}
        }

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

    def to_dict(self):
        return {
            "field_id": self.field_id,
            "semantic_purpose": self.semantic_purpose,
            "correct_value": self.correct_value,
            "reason": self.reason
        }

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
        print(f" Activating Form Understanding Agent for: {pa_form_path.name}")
        
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
            
        print(" Asking AI to analyze form structure and logic...")

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.model.generate_content(model_input)
                
                # 5. Parse the response and create the FormSchema object
                # This is now a text-based parsing, not JSON
                form_fields = self._parse_text_to_fields(response.text)
                
                schema = FormSchema(fields=form_fields)
                print(f" Schema created successfully with {len(schema.fields)} fields.")
                return schema

            except Exception as e:
                print(f" Attempt {attempt + 1}/{max_retries} failed. Reason: {e}")
                if attempt + 1 == max_retries:
                    print(f" Critical Error: AI failed to create form schema after {max_retries} attempts.")
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
                
                if not context.strip():
                    print(f" Skipping field '{field_id}' due to empty context.")
                    continue

                fields[field_id] = FormField(
                    field_id=field_id,
                    page_num=int(page_num_str.strip()),
                    field_type=field_type.strip(),
                    context=context.strip()
                )
            except (ValueError, IndexError) as e:
                print(f" Could not parse field entry: {entry} due to {e}")
                continue
        return fields

    def _build_schema_creation_prompt(self, raw_fields: List[Dict]) -> str:
        """Constructs the detailed prompt for schema generation."""
        
        raw_fields_json = json.dumps(raw_fields, indent=2)
        
        return f"""
        You are an expert in analyzing healthcare Prior Authorization (PA) forms.
        Your task is to analyze the provided images of a PA form and the raw field data to extract the VISUAL text label for each field.

        **1. Goal**
        Create a simple text list of all fields. For each field, you MUST find the corresponding text label on the form image and provide it as the context. DO NOT simply use the field ID as the context.

        **2. Raw Field Data (from the PDF):**
        ```json
        {raw_fields_json}
        ```

        **3. Task & Output Format**
        Generate a simple text list of all fields. For each field, provide the following on separate lines:
        - `ID: [The Field ID]`
        - `Context: [The VISUAL, HUMAN-READABLE TEXT LABEL from the form image]`
        - `Type: [The field type]`
        - `Page: [The page number]`

        **Example GOOD vs. BAD Output:**

        *   **GOOD:**
            ID: T.7
            Context: Patient First Name:
            Type: text
            Page: 0

        *   **BAD (YOU MUST AVOID THIS):**
            ID: T.7
            Context: T.7
            Type: text
            Page: 0
        
        Return ONLY the list of fields in this text format.
        """

class SchemaRefinementAgent:
    """Takes a raw schema and uses an LLM to assign meaningful semantic purposes."""

    def __init__(self):
        self.model = genai.GenerativeModel('gemini-2.5-pro')

    def refine_schema(self, schema: FormSchema) -> FormSchema:
        print(f" Activating Schema Refinement Agent for {len(schema.fields)} fields.")
        if not schema.fields:
            return schema

        field_contexts = [{
            "field_id": field.field_id,
            "context": field.context
        } for field in schema.fields.values()]
        
        prompt = self._build_prompt(field_contexts)
        
        try:
            response = self.model.generate_content(prompt)
            
            # Update the original schema with the new semantic purposes
            # Use splitlines() to handle newlines correctly
            for line in response.text.strip().splitlines():
                if '|' in line:
                    parts = [p.strip() for p in line.split('|')]
                    if len(parts) == 2:
                        field_id, purpose = parts
                        if field_id in schema.fields and purpose.lower() != 'null':
                            schema.fields[field_id].semantic_purpose = purpose
            
            # Heuristic to find radio button groups
            self._group_radio_buttons(schema)

            print(" Schema refinement complete.")
            return schema
        except Exception as e:
            print(f" Schema refinement failed: {e}")
            return schema # Return original schema on failure

    def _group_radio_buttons(self, schema: FormSchema):
        """A heuristic to add options to radio buttons based on shared purposes."""
        purpose_groups = {}
        for field in schema.fields.values():
            if field.field_type == 'radio' and field.semantic_purpose:
                # Group by the purpose, but remove the specific option (e.g., _yes, _no)
                base_purpose = '_'.join(field.semantic_purpose.split('_')[:-1])
                if base_purpose not in purpose_groups:
                    purpose_groups[base_purpose] = []
                purpose_groups[base_purpose].append(field)
        
        for base_purpose, group in purpose_groups.items():
            if len(group) > 1: # It's a real group
                options = [f.semantic_purpose for f in group]
                for field in group:
                    field.options = options


    def _build_prompt(self, field_contexts: list) -> str:
        """Constructs the prompt for the refinement agent."""
        
        context_str = "\n".join([f"- ID: {f['field_id']}, Context: \"{f['context']}\"" for f in field_contexts])
        
        return f"""
        You are an expert in medical data mapping. Your task is to assign a precise `semantic_purpose` to a list of form fields based on their context.

        **1. Goal**
        For each field, determine its exact purpose and assign a standardized key.

        **2. Standardized Keys**
        Use keys like these: `patient_last_name`, `prescriber_npi`, `drug_name`, `clinical_question_[question_summary]`.
        For Yes/No questions, append `_yes` or `_no` to the key. Example: `clinical_question_is_patient_over_18_yes`.

        **3. Input**
        A list of fields with their `ID` and `Context` (the text label from the form).

        **4. Output Format**
        Return ONLY a pipe-separated list of mappings, one per line:
        `field_id | semantic_purpose`
        If a field is not for data entry (e.g., a title, instruction), assign `null` as the purpose.

        **Example Input:**
        - ID: T.7, Context: "Patient First Name:"
        - ID: C.1, Context: "Yes" (For the question "Is the patient over 18?")

        **Example Output:**
        T.7 | patient_first_name
        C.1 | clinical_question_is_patient_over_18_yes

        **Fields to Process:**
        {context_str}
        """

class DataExtractionAgent:
    """Uses an LLM to extract structured data from referral documents."""
    def __init__(self):
        # Using a powerful model for extraction accuracy
        self.model = genai.GenerativeModel('gemini-2.5-pro')

    def extract_data(self, referral_path: Path, schema: FormSchema) -> ExtractedData:
        """Performs targeted data extraction based on a refined schema."""
        print(f" Activating Data Extraction Agent for: {referral_path.name}")
        
        if not any(f.semantic_purpose for f in schema.fields.values()):
            print(" Skipping extraction: No semantic purposes found in schema.")
            return ExtractedData()

        # 1. Convert referral document to images
        doc = fitz.open(referral_path)
        page_images_b64 = []
        for page in doc:
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_data = pix.tobytes("png")
            page_images_b64.append(base64.b64encode(img_data).decode())
        doc.close()

        # 2. Build and execute the prompt
        prompt = self._build_extraction_prompt(schema)
        model_input = [prompt]
        for img_b64 in page_images_b64:
            model_input.append({"mime_type": "image/png", "data": img_b64})

        print(" Asking AI to extract patient data...")
        
        try:
            response = self.model.generate_content(model_input,
                generation_config=genai.types.GenerationConfig(
                    response_mime_type="application/json"
                )
            )
            return self._parse_extraction_response(response.text)
        except Exception as e:
            print(f" Data extraction failed: {e}")
            return ExtractedData()

    def _parse_extraction_response(self, response_text: str) -> ExtractedData:
        try:
            data = json.loads(response_text)
            print(" Data extraction successful.")
            
            # The AI doesn't always follow the "extracted_data" nesting instruction.
            # This makes our parsing more robust.
            if "extracted_data" in data and isinstance(data["extracted_data"], dict):
                # Ideal case: the AI followed instructions perfectly.
                return ExtractedData(data=data["extracted_data"])
            elif isinstance(data, dict) and any(data.values()):
                # Common case: the AI returned a flat JSON object with the data.
                print("   AI did not use the 'extracted_data' key. Processing flat JSON response.")
                return ExtractedData(data=data)
            else:
                # The JSON is valid but empty or in an unexpected format.
                print("   AI returned a valid but empty or unrecognized JSON structure.")
                return ExtractedData()

        except json.JSONDecodeError as e:
            print(f" Error decoding JSON from extraction response: {e}")
            print(f"   Raw response: {response_text}")
            return ExtractedData()

    def _build_extraction_prompt(self, schema: FormSchema) -> str:
        """Builds a targeted prompt for data extraction."""
        
        data_points_to_extract = {
            field.semantic_purpose: field.context
            for field in schema.fields.values() if field.semantic_purpose and not field.semantic_purpose.startswith("clinical_")
        }
        
        data_points_str = "\n".join([f'- `{key}` (related to "{label}")' for key, label in data_points_to_extract.items()])

        return f"""
        You are a specialized data extraction bot for medical documents.
        Your task is to analyze the provided images of a patient's referral document and extract specific pieces of information.

        **1. Goal**
        Find and extract the values for the following data points. The text in parentheses is the label from the form where this data will be placed, use it as a hint to find the correct value.

        **Data to Extract:**
        {data_points_str}

        **2. Rules**
        - Read the entire document carefully to find the most accurate information.
        - Provide the data in the requested JSON format.
        - If you cannot find a value for a specific field, return `null` for that key. Do not make up information.
        - For dates, use the format `MM/DD/YYYY`.
        
        **3. Output Format**
        You MUST return your findings as a single JSON object.

        **Example JSON Output:**
        ```json
        {{
          "extracted_data": {{
            "patient_last_name": "Chen",
            "patient_first_name": "Amy",
            "patient_dob": "05/23/1983",
            "prescriber_npi": "1234567890"
          }}
        }}
        ```

        Now, analyze the document and return the extracted data.
        """

class ClinicalQAAgent:
    """A specialized agent to answer clinical 'Yes/No' questions."""
    def __init__(self):
        self.model = genai.GenerativeModel('gemini-2.5-pro')

    def answer_questions(self, referral_path: Path, clinical_questions: Dict[str, FormField]) -> Dict[str, Any]:
        """
        Analyzes the referral document to answer a specific list of clinical questions.
        """
        print(f" Activating Clinical QA Agent for {len(clinical_questions)} questions.")
        if not clinical_questions:
            return {}
        
        # 1. Convert referral document to images
        doc = fitz.open(referral_path)
        page_images_b64 = []
        for page in doc:
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_data = pix.tobytes("png")
            page_images_b64.append(base64.b64encode(img_data).decode())
        doc.close()
        
        # 2. Build and execute the prompt
        prompt = self._build_qa_prompt(clinical_questions)
        model_input = [prompt]
        for img_b64 in page_images_b64:
            model_input.append({"mime_type": "image/png", "data": img_b64})

        print(" Asking AI to answer clinical questions...")

        try:
            response = self.model.generate_content(model_input,
                generation_config=genai.types.GenerationConfig(
                    response_mime_type="application/json"
                )
            )
            answers = json.loads(response.text)
            print(" Clinical questions answered successfully.")
            return answers.get("answers", {})
        except Exception as e:
            print(f" Clinical QA failed: {e}")
            return {}

    def _build_qa_prompt(self, clinical_questions: Dict[str, FormField]) -> str:
        """Builds a targeted prompt for answering clinical questions."""
        
        question_list_str = "\n".join(
            [f'- `{q.semantic_purpose}`: {q.context}' for q in clinical_questions.values()]
        )
        
        return f"""
        You are a clinical expert AI. Your task is to analyze a patient's medical record and answer a series of Yes/No questions based on the provided information.

        **1. Goal**
        For each clinical question below, carefully review the entire patient record to find the answer.

        **Questions to Answer:**
        {question_list_str}

        **2. Rules**
        - You must answer with "Yes", "No", or "Not Found".
        - Base your answers ONLY on the provided document. Do not make assumptions.
        - The `semantic_purpose` is the key you will use in your JSON output.

        **3. Output Format**
        You MUST return your findings as a single JSON object.

        **Example JSON Output:**
        ```json
        {{
          "answers": {{
            "clinical_question_has_prior_treatment_yes": "Yes",
            "clinical_question_meets_criteria_xyz_no": "No",
            "clinical_question_is_diagnosis_confirmed_yes": "Not Found"
          }}
        }}
        ```
        Now, analyze the document and provide your answers.
        """

class ValidationAgent:
    """Visually inspects a filled form, compares it to source data, and suggests corrections."""
    
    def __init__(self):
        # Using the most powerful model for this critical validation task
        self.model = genai.GenerativeModel('gemini-2.5-pro')

    def validate_and_correct(self, 
                             filled_form_path: Path, 
                             schema: FormSchema, 
                             extracted_data: ExtractedData) -> List[Correction]:
        """
        The core 'fill and verify' loop. Compares the filled form to the
        source data and generates a list of corrections.
        """
        print(f" Activating Validation Agent for: {filled_form_path.name}")
        
        if not extracted_data.data:
            print(" Skipping validation: No data was extracted.")
            return []
            
        # 1. Convert the FILLED PDF to an image
        doc = fitz.open(filled_form_path)
        page_images_b64 = []
        for page in doc:
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_data = pix.tobytes("png")
            page_images_b64.append(base64.b64encode(img_data).decode())
        doc.close()
        
        # 2. Build the detailed validation prompt
        prompt = self._build_validation_prompt(schema, extracted_data)
        
        # 3. Call the model
        model_input = [prompt]
        for img_b64 in page_images_b64:
            model_input.append({"mime_type": "image/png", "data": img_b64})

        print(" Asking AI to validate the filled form...")
        
        try:
            response = self.model.generate_content(model_input,
                generation_config=genai.types.GenerationConfig(
                    response_mime_type="application/json"
                )
            )
            
            # 4. Parse the corrections from the response
            response_data = json.loads(response.text)
            corrections_data = response_data.get("corrections", [])
            
            corrections = [Correction(**c) for c in corrections_data]
            if corrections:
                print(f" Validation complete. Found {len(corrections)} corrections.")
            else:
                print(" Validation complete. No corrections needed.")
            return corrections
            
        except Exception as e:
            print(f" Validation failed: {e}")
            return []

    def _build_validation_prompt(self, schema: FormSchema, extracted_data: ExtractedData) -> str:
        """Constructs the prompt for the validation agent."""

        schema_dict = schema.to_dict()
        extracted_dict = extracted_data.data
        
        # We need to create a simplified structure for the prompt that links
        # the semantic purpose to the field ID for the AI.
        validation_map = {}
        for field in schema.fields.values():
            if field.semantic_purpose in extracted_dict:
                validation_map[field.semantic_purpose] = {
                    "field_id": field.field_id,
                    "expected_value": extracted_dict[field.semantic_purpose],
                    "context": field.context
                }

        validation_map_json = json.dumps(validation_map, indent=2)

        return f"""
        You are a meticulous quality assurance auditor for medical forms.
        Your task is to compare a filled-out PDF form against the original source data and identify any mistakes.

        **1. Goal**
        You will be given:
        1.  Images of the **FILLED** PA form.
        2.  A JSON object (`validation_map`) containing the `field_id`, the `expected_value` that SHOULD be on the form, and the `context` (the label for that field).

        Your job is to visually inspect the images and create a list of corrections for any fields that are incorrect, misplaced, or illegible.

        **2. The `validation_map` (Source of Truth):**
        ```json
        {validation_map_json}
        ```

        **3. Types of Errors to Look For:**
        - **Incorrect Value:** The wrong information is entered (e.g., wrong birth date).
        - **Misplaced Value:** The data is in the wrong field (e.g., patient's name in the doctor's name field).
        - **Formatting Error:** The data is correct but formatted poorly (e.g., date is `2023-05-19` instead of `05/19/2023`).
        - **Illegible Text:** The text is garbled, cut off, or unreadable.
        - **Checkbox/Radio Error:** The wrong option is selected, or multiple radio buttons in a group are selected.

        **4. Output Format**
        You MUST return your findings as a single JSON object containing a list called `corrections`.
        Each item in the list must have the following keys:
        - `field_id`: The ID of the field that needs fixing.
        - `semantic_purpose`: The semantic key for the data.
        - `correct_value`: The value that SHOULD be in the field.
        - `reason`: A brief explanation of why the correction is needed (e.g., "Incorrect value filled", "Text is misplaced").

        **Example JSON Output:**
        ```json
        {{
          "corrections": [
            {{
              "field_id": "T.8",
              "semantic_purpose": "patient_dob",
              "correct_value": "05/23/1983",
              "reason": "Incorrect value filled. Form shows 05/22/1983."
            }},
            {{
              "field_id": "T.12",
              "semantic_purpose": "drug_name",
              "correct_value": "Vyepti",
              "reason": "Text is cut off and illegible."
            }}
          ]
        }}
        ```
        If no errors are found, return an empty list: `{{"corrections": []}}`.

        Now, meticulously audit the form images against the `validation_map`.
        """

class FormFillingAgent:
    """A non-AI agent that mechanically fills PDF form fields using PyMuPDF."""

    def fill_form(self,
                  schema: FormSchema,
                  data_to_fill: Dict[str, Any],
                  output_path: Path,
                  base_form_path: Path, # Path to the PDF to be opened
                  is_correction: bool = False):
        """
        Fills or corrects a PDF form. If `is_correction` is true, it opens
        the file at `output_path` to modify it. Otherwise, it uses the `base_form_path`.
        """
        
        if is_correction:
            print(f" Correcting {len(data_to_fill)} fields in: {output_path.name}")
            doc = fitz.open(output_path)
        else:
            print(f" Filling {len(data_to_fill)} fields in a new form.")
            doc = fitz.open(base_form_path)

        purpose_to_field_map = {field.semantic_purpose: field for field in schema.fields.values() if field.semantic_purpose}

        for purpose, value in data_to_fill.items():
            if value is None: continue

            if purpose in purpose_to_field_map:
                field = purpose_to_field_map[purpose]
                page = doc[field.page_num]
                
                try:
                    widget = next((w for w in page.widgets() if w.field_name == field.field_id), None)
                    if widget:
                        # Handle radio buttons specially
                        if widget.field_type_string == "radio":
                            # This logic finds the correct radio button in a group to turn on
                            # It assumes the `value` matches one of the `options`
                            for opt_purpose in field.options:
                                opt_field = purpose_to_field_map.get(opt_purpose)
                                if not opt_field: continue
                                
                                opt_widget = next((w for w in page.widgets() if w.field_name == opt_field.field_id), None)
                                if opt_widget:
                                    # Turn on the selected one, turn off others
                                    opt_widget.field_value = (opt_purpose == purpose)
                                    opt_widget.update()
                        else:
                            # For all other fields (text, checkbox)
                            widget.field_value = value
                            widget.update() # Apply the change
                except Exception as e:
                    print(f"  Could not fill field '{field.field_id}' for purpose '{purpose}'. Reason: {e}")

        # Flatten form fields to make them non-editable after filling
        if doc.is_form:
            doc.flatten_widgets()

        # Save the file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(output_path), garbage=4, deflate=True)
        doc.close()

class MANDOLIN_PA_SYSTEM:
    def __init__(self):
        self.understanding_agent = FormUnderstandingAgent()
        self.refinement_agent = SchemaRefinementAgent()
        self.extraction_agent = DataExtractionAgent()
        self.qa_agent = ClinicalQAAgent()
        self.filling_agent = FormFillingAgent()
        self.validation_agent = ValidationAgent()
        self.schema_cache = {}
        self.processed_patients = []

    def process_pa(self, patient_name: str, referral_path: Path, pa_form_path: Path, output_dir: Path):
        """
        Executes the full, multi-agent pipeline for processing a single PA request.
        """
        print("\n" + "="*50)
        print(f" Starting Mandolin Pipeline for Patient: {patient_name}")
        print(f"   Referral Doc: {referral_path.name}")
        print(f"   PA Form: {pa_form_path.name}")
        print("="*50 + "\n")

        # --- Phase 1: Schema Creation (or loading from cache) ---
        if pa_form_path.name in self.schema_cache:
            schema = self.schema_cache[pa_form_path.name]
            print(" Loaded schema from cache.")
        else:
            raw_schema = self.understanding_agent.create_schema(pa_form_path)
            schema = self.refinement_agent.refine_schema(raw_schema)
            self.schema_cache[pa_form_path.name] = schema
        
        if not schema.fields:
            print(f" Halting processing for {patient_name}: Schema creation failed.")
            return

        # --- Phase 2: Parallel Data Extraction ---
        # 2a. Extract structured data (demographics, etc.)
        extracted_data = self.extraction_agent.extract_data(referral_path, schema)
        
        # 2b. Answer specific clinical questions
        clinical_questions = {
            f.semantic_purpose: f for f in schema.fields.values() 
            if f.semantic_purpose and f.semantic_purpose.startswith("clinical_")
        }
        clinical_answers = self.qa_agent.answer_questions(referral_path, clinical_questions)
        
        # Merge all data into one dictionary for filling
        all_data_to_fill = {**extracted_data.data, **clinical_answers}

        if not all_data_to_fill:
            print(f" Halting processing for {patient_name}: No data could be extracted.")
            self.generate_report(patient_name, schema, extracted_data, output_dir)
            return

        # --- Phase 3: Initial Form Filling ---
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"{patient_name.replace(' ', '_')}_PA_{timestamp}.pdf"
        output_path = output_dir / output_filename
        
        self.filling_agent.fill_form(
            schema=schema,
            data_to_fill=all_data_to_fill,
            output_path=output_path,
            base_form_path=pa_form_path
        )

        # --- Phase 4: Validation and Correction ---
        corrections = self.validation_agent.validate_and_correct(output_path, schema, extracted_data)
        if corrections:
            # Create a dictionary of corrections to pass to the filling agent
            correction_data = {c.semantic_purpose: c.correct_value for c in corrections}
            self.filling_agent.fill_form(
                schema=schema,
                data_to_fill=correction_data,
                output_path=output_path, # Overwrite the previous file
                base_form_path=pa_form_path,
                is_correction=True
            )

        # --- Phase 5: Reporting ---
        self.generate_report(patient_name, schema, extracted_data, output_dir)
        
        print("\n" + "="*50)
        print(f" Mandolin Pipeline finished for {patient_name}.")
        print("="*50 + "\n")

    def generate_report(self, patient_name: str, schema: FormSchema, extracted_data: ExtractedData, output_dir: Path):
        """Generates a markdown report of missing information."""
        
        # Find purposes that were in the schema but not found in the extracted data
        schema_purposes = {f.semantic_purpose for f in schema.fields.values() if f.semantic_purpose}
        extracted_purposes = set(extracted_data.data.keys())
        missing_purposes = schema_purposes - extracted_purposes
        
        missing_info = {
            purpose: schema.fields[field_id].context
            for field_id, field in schema.fields.items()
            if (purpose := field.semantic_purpose) in missing_purposes
        }

        if not missing_info:
            return

        report_path = output_dir / f"{patient_name.replace(' ', '_')}_processing_report.md"
        with open(report_path, 'w') as f:
            f.write(f"# Processing Report for {patient_name}\n\n")
            f.write("The following information could not be found in the referral documents:\n\n")
            for purpose, context in missing_info.items():
                f.write(f"- **{context}** (Needed for field with purpose: `{purpose}`)\n")
        print(f" Report generated for missing information at: {report_path.name}")


def main():
    """Main function to run the Mandolin PA processing pipeline."""
    # Define directories
    base_dir = Path(__file__).parent
    input_dir = base_dir / "Input Data"
    output_dir = base_dir / "Output Data"
    
    # Create output directory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Process each patient folder in the input directory
    pipeline = MANDOLIN_PA_SYSTEM()
    for patient_dir in input_dir.iterdir():
        if patient_dir.is_dir():
            patient_name = patient_dir.name
            
            # Find the referral and form files
            referral_doc_path = next(patient_dir.glob("*_Referral_*"), None)
            pa_form_path = next(patient_dir.glob("*_FORM_*"), None)
            
            if referral_doc_path and pa_form_path:
                pipeline.process_pa(
                    patient_name=patient_name,
                    referral_path=referral_doc_path,
                    pa_form_path=pa_form_path,
                    output_dir=output_dir
                )
            else:
                print(f" Skipping {patient_name}: Could not find required Referral and/or FORM file.")

if __name__ == "__main__":
    main()