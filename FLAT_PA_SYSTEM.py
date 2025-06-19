#!/usr/bin/env python3
"""
MANDOLIN PA AUTOMATION SYSTEM
A text-anchor-based system for filling flat (non-interactive) PDF forms.
This system uses a deterministic approach to locate fields based on their
text labels, ensuring high accuracy and perfect alignment.
"""

import json
import fitz  # PyMuPDF
import base64
from pathlib import Path
import google.generativeai as genai
from dotenv import load_dotenv
import os
from typing import Dict, List, Optional, Any, Tuple, Literal
from dataclasses import dataclass, field
import datetime
import re
from PIL import Image

# --- Setup ---
load_dotenv()
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))

# --- Data Structures ---

@dataclass
class FormLabel:
    """
    Represents a single text label identified on the PA form using PyMuPDF.
    This is the core "anchor" for all operations.
    """
    text: str
    page_num: int
    # Exact coordinates [x0, y0, x1, y1] from the PDF's text rendering
    coordinates: Tuple[float, float, float, float]
    # The semantic purpose (e.g., 'patient_last_name') assigned by the mapper.
    semantic_purpose: Optional[str] = None
    # The data extracted from a referral doc that corresponds to this label's purpose.
    extracted_value: Optional[Any] = None

    def to_dict(self):
        return {
            "text": self.text,
            "page_num": self.page_num,
            "coordinates": self.coordinates,
            "semantic_purpose": self.semantic_purpose,
            "extracted_value": self.extracted_value,
        }

@dataclass
class FormSchema:
    """
    A structured representation of all text labels found on the form.
    In this architecture, the labels ARE the schema.
    """
    labels: List[FormLabel]

    def to_dict(self):
        return { "labels": [label.to_dict() for label in self.labels] }

    def get_labels_by_purpose(self) -> Dict[str, FormLabel]:
        """Returns a mapping of semantic_purpose -> FormLabel for quick lookup."""
        return {label.semantic_purpose: label for label in self.labels if label.semantic_purpose}

# --- Agent Components ---

class TextAnchorAgent:
    """Finds the precise coordinates of text labels on a PDF using PyMuPDF."""
    def find_text_anchors(self, pa_form_path: Path) -> List[FormLabel]:
        """Extracts all text blocks from a PDF and returns them as FormLabel objects."""
        print(f" Activating Text Anchor Agent for: {pa_form_path.name}")
        labels = []
        doc = fitz.open(pa_form_path)

        for page_num, page in enumerate(doc):
            # Use get_text("dict") for more structured data including font size
            blocks = page.get_text("dict", flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_LIGATURES)["blocks"]
            for block in blocks:
                if "lines" not in block: continue
                for line in block["lines"]:
                    # Heuristic to combine spans that form a single logical label
                    text_parts = []
                    bbox_parts = []
                    for span in line["spans"]:
                        text = span["text"].strip()
                        if text:
                           text_parts.append(text)
                           bbox_parts.append(fitz.Rect(span["bbox"]))
                    
                    if text_parts:
                        full_text = " ".join(text_parts)
                        # Combine bboxes to get the full label's coordinates
                        if bbox_parts:
                            combined_bbox = fitz.Rect()
                            for r in bbox_parts:
                                combined_bbox.include_rect(r)

                            labels.append(
                                FormLabel(
                                    text=full_text,
                                    page_num=page_num,
                                    coordinates=tuple(combined_bbox)
                                )
                            )
        
        doc.close()
        # Filter out very long text blocks that are likely paragraphs, not labels
        labels = [l for l in labels if len(l.text) < 100]
        print(f" Found {len(labels)} potential text anchors.")
        return labels

class SemanticMapperAgent:
    """Uses a powerful AI model to assign a semantic purpose to each text label."""
    def __init__(self):
        self.model = genai.GenerativeModel('gemini-2.5-pro')

    def map_semantics(self, labels: List[FormLabel]) -> List[FormLabel]:
        """Assigns a semantic purpose to each label based on its text content."""
        print(f"  Activating Semantic Mapper...")
        if not labels:
            return []

        prompt = self._build_mapping_prompt(labels)

        try:
            # The response is expected to be JSON now for better reliability
            response = self.model.generate_content(prompt,
                generation_config=genai.types.GenerationConfig(
                    response_mime_type="application/json"
                )
            )
            # The AI returns a dictionary of { "original_text": "semantic_purpose" }
            mappings = json.loads(response.text)
            
            # Create a dictionary for quick lookup of labels by their text
            label_dict = {label.text: label for label in labels}

            # Update the original label objects with the new semantic purpose
            for text, purpose in mappings.items():
                if text in label_dict and purpose and purpose.lower() != 'null':
                    label_dict[text].semantic_purpose = purpose
            
            # Return the updated list of label objects
            updated_labels = list(label_dict.values())
            
            # Count how many labels were successfully mapped
            mapped_count = sum(1 for label in updated_labels if label.semantic_purpose)
            print(f" Semantic mapping complete. {mapped_count} labels were assigned a purpose.")
            return updated_labels

        except (Exception, json.JSONDecodeError) as e:
            print(f" Semantic mapping AI call failed: {e}")
            # On failure, return the original, unmapped labels
            return labels

    def _build_mapping_prompt(self, labels: List[FormLabel]) -> str:
        """Builds the prompt for the LLM to map text to a semantic purpose."""
        # Create a simple list of the text from each label
        label_texts = [label.text for label in labels]
        # Use json.dumps to ensure proper escaping for the prompt
        label_texts_json = json.dumps(label_texts, indent=2)

        return f"""
You are an expert in medical form data mapping. Your task is to analyze a list of text labels extracted from a PDF form and assign a precise `semantic_purpose` to each one.

**Instructions:**
1.  Review the list of label texts provided below.
2.  For each text, determine its purpose in the context of a standard medical Prior Authorization form.
3.  Use the standardized purpose keys from the examples (e.g., `patient_last_name`, `prescriber_npi`).
4.  If a label's purpose is ambiguous, not for data entry (e.g., "Instructions", "Page 2 of 3"), or is not a fillable field's label, assign the value `null`.
5.  Pay close attention to context. "Last name:" under "Member Information" should be `patient_last_name`, while under "Prescriber Information" it should be `prescriber_last_name`. The list order should provide this context.

**Crucial: Output Format**
- You MUST return a single JSON object.
- The keys of the object should be the original label texts from the input list.
- The values should be the `semantic_purpose` string you assign.

**Example Input List:**
[
    "Member Information",
    "Last name:",
    "First name:",
    "Prescriber information",
    "Last name:",
    "Phone number:"
]

**Example JSON Output:**
```json
{{
  "Member Information": "null",
  "Last name:": "patient_last_name",
  "First name:": "patient_first_name",
  "Prescriber information": "null",
  "Last name:": "prescriber_last_name",
  "Phone number:": "prescriber_phone"
}}
```

**Labels to Process:**
{label_texts_json}
"""

class DataExtractionAgent:
    """Uses an LLM to extract structured data from referral documents."""
    def __init__(self):
        
        self.model = genai.GenerativeModel('gemini-2.0-flash')

    def extract_data(self, referral_path: Path, required_purposes: List[str]) -> Dict[str, Any]:
        """Performs targeted data extraction based on a list of required semantic purposes."""
        print(f" Activating Data Extraction Agent for: {referral_path.name}")

        if not required_purposes:
            print(" Warning: No required data points provided. Skipping extraction.")
            return {}

        doc = fitz.open(referral_path)
        page_images = [page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0)) for page in doc]
        doc.close()

        prompt = self._build_extraction_prompt(required_purposes)
        
        # Prepare the multi-modal input for the Gemini model
        model_input = [prompt] + [Image.frombytes("RGB", [pix.width, pix.height], pix.samples) for pix in page_images]

        print(f" Asking AI to extract {len(required_purposes)} data points...")

        try:
            response = self.model.generate_content(model_input,
                generation_config=genai.types.GenerationConfig(
                    response_mime_type="application/json"
                )
            )
            extracted_data = json.loads(response.text)
            
            # The AI sometimes nests the result, so we handle that gracefully.
            final_data = extracted_data.get("extracted_data", extracted_data)
            
            print(" Data extraction successful.")
            return final_data if isinstance(final_data, dict) else {}

        except (Exception, json.JSONDecodeError) as e:
            print(f" Data extraction failed: {e}")
            return {}

    def _build_extraction_prompt(self, required_purposes: List[str]) -> str:
        """Builds a targeted prompt for data extraction."""
        # Use json.dumps to format the list of purposes for the prompt
        purposes_json = json.dumps(required_purposes, indent=2)
        return f"""
You are a specialized data extraction bot for medical documents. Your task is to analyze the provided images of a patient's referral document and extract specific pieces of information.

**1. Goal:**
Find and extract the values for the data points corresponding to these semantic purposes:
{purposes_json}

**2. Rules:**
- Read the entire document carefully to find the most accurate information.
- If you cannot find a value for a specific field, return `null` for that key. Do not make up information.
- For dates, use the format `MM/DD/YYYY`.
- For clinical questions (those starting with `clinical_question_`), answer based on the document content with "Yes", "No", or a specific value if requested.

**3. Output Format:**
You MUST return your findings as a single JSON object. The keys of the object MUST be the semantic purposes from the input list.

**Example JSON Output:**
```json
{{
  "patient_last_name": "Chen",
  "patient_dob": "05/23/1983",
  "prescriber_npi": "1234567890"
}}
```

Now, analyze the document and return the extracted data.
"""

class TextAnchorFillingAgent:
    """Fills a flat PDF form deterministically using text anchors."""
    def fill_form(self,
                  schema: FormSchema,
                  output_path: Path,
                  base_form_path: Path):
        
        print(f" Activating Text-Anchor Form Filling Agent.")
        
        labels_with_values = [label for label in schema.labels if label.extracted_value is not None]

        if not labels_with_values:
            print(" No data to fill. Aborting form filling.")
            return

        doc = fitz.open(base_form_path)
        
        for label in labels_with_values:
            page = doc[label.page_num]
            text_to_insert = str(label.extracted_value)
            
            # --- This is the core logic of the Text-Anchor system ---
            # Get the label's bounding box to use as an anchor
            anchor_rect = fitz.Rect(label.coordinates)
            
            # Define an insertion point to the right of the label
            # Padding is a small percentage of the label's width, with a minimum
            padding = max(anchor_rect.width * 0.1, 5) 
            insertion_point = fitz.Point(anchor_rect.x1 + padding, anchor_rect.y1)
            
            # Use the height of the anchor as a reference for font size
            font_size = max(anchor_rect.height * 0.8, 9)

            # Insert the text using the calculated position and font size
            page.insert_text(
                insertion_point,
                text_to_insert,
                fontname="helv", # Use a standard font
                fontsize=font_size,
                color=(0, 0, 0) # Black
            )
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(output_path), garbage=4, deflate=True, clean=True)
        doc.close()
        print(f" Form filling complete. {len(labels_with_values)} fields filled. Saved to: {output_path}")


class MandolinPipeline:
    """
    Orchestrates the entire PA form processing workflow using the
    text-anchor architecture. This approach is simpler and more reliable.
    """
    def __init__(self):
        self.text_anchor_agent = TextAnchorAgent()
        self.mapper = SemanticMapperAgent()
        self.extractor = DataExtractionAgent()
        self.filler = TextAnchorFillingAgent()
        self.schema_cache: Dict[str, FormSchema] = {}

    def get_cached_schema(self, form_path: Path) -> Optional[FormSchema]:
        """Checks for a pre-processed schema file."""
        cache_file = form_path.with_suffix('.text_anchor.json')
        if cache_file.exists():
            print(f"Found cached schema: {cache_file.name}")
            try:
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                    labels = [FormLabel(**label_data) for label_data in data.get("labels", [])]
                    return FormSchema(labels=labels)
            except (Exception, json.JSONDecodeError) as e:
                print(f" Warning: Could not load cached schema. Re-processing. Reason: {e}")
        return None

    def save_schema_to_cache(self, form_path: Path, schema: FormSchema):
        """Saves a processed schema to a JSON file."""
        cache_file = form_path.with_suffix('.text_anchor.json')
        try:
            with open(cache_file, 'w') as f:
                json.dump(schema.to_dict(), f, indent=2)
            print(f"Schema saved to cache: {cache_file.name}")
        except Exception as e:
            print(f" Error saving schema to cache: {e}")

    def process_pa(self, patient_name: str, referral_path: Path, pa_form_path: Path, output_dir: Path):
        """
        Executes the full, robust pipeline for processing a single PA request.
        """
        print("\n" + "="*50)
        print(f" Starting Mandolin Pipeline for Patient: {patient_name}")
        print(f"   Referral Doc: {referral_path.name}")
        print(f"   PA Form: {pa_form_path.name}")
        print("="*50 + "\n")

        # --- Phase 1: Schema Creation (or loading from cache) ---
        schema = self.get_cached_schema(pa_form_path)
        if not schema or not any(l.semantic_purpose for l in schema.labels):
            print("No valid cached schema found. Processing from scratch...")
            # 1a. Find all text anchors on the form
            labels = self.text_anchor_agent.find_text_anchors(pa_form_path)
            
            # 1b. Assign semantic purposes to those anchors
            mapped_labels = self.mapper.map_semantics(labels)
            
            schema = FormSchema(labels=mapped_labels)
            self.save_schema_to_cache(pa_form_path, schema)
        
        # --- Phase 2: Data Extraction ---
        # Get a list of purposes that the mapper successfully identified
        required_purposes = [l.semantic_purpose for l in schema.labels if l.semantic_purpose]
        
        if not required_purposes:
            print(" Pipeline halted: No semantic purposes could be mapped from the form.")
            return
            
        extracted_data = self.extractor.extract_data(referral_path, required_purposes)

        if not extracted_data:
            print(" Pipeline halted: Data extraction failed or returned no data.")
            return

        # --- Phase 3: Data Merging ---
        # Link the extracted data back to the original schema labels
        purpose_to_label_map = schema.get_labels_by_purpose()
        for purpose, value in extracted_data.items():
            if purpose in purpose_to_label_map and value is not None and str(value).lower() != 'null':
                purpose_to_label_map[purpose].extracted_value = value

        # --- Phase 4: Form Filling ---
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"{patient_name.replace(' ', '_')}_PA_{timestamp}.pdf"
        output_path = output_dir / output_filename

        self.filler.fill_form(schema, output_path, pa_form_path)

        # --- Phase 5: Reporting ---
        self.generate_report(patient_name, schema, output_dir)

        print("\n" + "="*50)
        print(" Mandolin Pipeline finished successfully.")
        print("="*50 + "\n")

    def generate_report(self, patient_name: str, schema: FormSchema, output_dir: Path):
        """Generates a markdown report of missing information."""
        
        # Find labels that had a purpose but no value was extracted for them
        missing_labels = [
            label for label in schema.labels 
            if label.semantic_purpose and label.extracted_value is None
        ]

        if not missing_labels:
            return

        report_path = output_dir / f"{patient_name.replace(' ', '_')}_processing_report.md"
        with open(report_path, 'w') as f:
            f.write(f"# Processing Report for {patient_name}\n\n")
            f.write("The following information could not be found in the referral documents:\n\n")
            for label in missing_labels:
                f.write(f"- **{label.text}** (Needed for purpose: `{label.semantic_purpose}`)\n")
        print(f" Report generated for missing information at: {report_path.name}")


def find_files(directory: Path, name_contains: str) -> Optional[Path]:
    """Finds the first file in a directory whose name contains a string."""
    for item in directory.iterdir():
        if item.is_file() and name_contains in item.name and item.name.lower().endswith('.pdf'):
            return item
    return None


def main():
    """Main function to run the Mandolin PA processing pipeline."""
    base_dir = Path(__file__).parent
    input_dir = base_dir / "pa_forms" / "patient_documents"
    output_dir = base_dir / "pa_forms" / "completed"
    output_dir.mkdir(parents=True, exist_ok=True)

    referral_doc_path = find_files(input_dir, "Referral")
    pa_form_path = find_files(input_dir, "FORM")

    if not referral_doc_path or not pa_form_path:
        print(f" Error: Could not find required 'Referral' and 'FORM' files in '{input_dir}'.")
        return

    patient_name = "Amy Chen" # In a real system, this would be dynamic

    pipeline = MandolinPipeline()
    pipeline.process_pa(
        patient_name=patient_name,
        referral_path=referral_doc_path,
        pa_form_path=pa_form_path,
        output_dir=output_dir
    )

if __name__ == "__main__":
    main()