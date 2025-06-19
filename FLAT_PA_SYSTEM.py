#!/usr/bin/env python3
"""
MANDOLIN PA AUTOMATION SYSTEM
An agent-based system to handle dynamic, conditional, and complex PA forms.
This system is designed to be universal and handle any PA form for any drug.
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
import io
import math


load_dotenv()
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))

# --- Data Structures ---

@dataclass
class FormField:
    """Represents a single visual, fillable field on the PA form."""
    field_id: str
    page_num: int
    type: Literal["char_boxes", "underline", "checkbox"]
    # Bounding box of the fillable area itself
    coordinates: List[List[float]]
    box_count: Optional[int] = None
    # These will be populated by the mapper
    linked_label: Optional[str] = None
    semantic_purpose: Optional[str] = None

    def to_dict(self):
        return {
            "field_id": self.field_id,
            "page_num": self.page_num,
            "type": self.type,
            "coordinates": self.coordinates,
            "box_count": self.box_count,
            "linked_label": self.linked_label,
            "semantic_purpose": self.semantic_purpose,
        }

@dataclass
class FormLabel:
    """Represents a single text label identified on the PA form using PyMuPDF for precision."""
    text: str
    page_num: int
    # Exact coordinates [x0, y0, x1, y1] from the PDF's text rendering
    coordinates: Tuple[float, float, float, float]
    semantic_purpose: Optional[str] = None

    def to_dict(self):
        return {
            "text": self.text,
            "page_num": self.page_num,
            "coordinates": self.coordinates,
            "semantic_purpose": self.semantic_purpose,
        }

@dataclass
class FormSchema:
    """A structured representation of all text labels and fillable fields."""
    labels: List[FormLabel]
    fields: List[FormField]

    def to_dict(self):
        return {
            "labels": [label.to_dict() for label in self.labels],
            "fields": [field.to_dict() for field in self.fields],
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

class TextAnchorAgent:
    """
    Finds the precise coordinates of text labels on a PDF using PyMuPDF, not AI.
    This provides a deterministic and accurate foundation for form filling.
    """
    def find_text_anchors(self, pa_form_path: Path) -> List[FormLabel]:
        """
        Extracts all text blocks from a PDF and returns them as FormLabel objects.
        """
        print(f"⚓️ Activating Text Anchor Agent for: {pa_form_path.name}")
        labels = []
        doc = fitz.open(pa_form_path)

        for page_num, page in enumerate(doc):
            # Extract words with their coordinates
            words = page.get_text("words")
            for word in words:
                x0, y0, x1, y1, text, _, _, _ = word
                # Clean up text and create a label
                cleaned_text = text.strip()
                if cleaned_text:
                    labels.append(
                        FormLabel(
                            text=cleaned_text,
                            page_num=page_num,
                            coordinates=(x0, y0, x1, y1)
                        )
                    )
        
        doc.close()
        print(f"✅ Found {len(labels)} potential text anchors.")
        return labels

class SemanticMapperAgent:
    """
    Links visual fields to their nearest text labels and section headers,
    then uses an AI model with this context to assign a precise semantic purpose.
    """
    def __init__(self):
        self.model = genai.GenerativeModel('gemini-2.5-pro')

    def map_semantics(self, schema: FormSchema) -> FormSchema:
        print(f"🗺️  Activating Context-Aware Semantic Mapper...")
        if not schema.fields:
            return schema

        # 1. Link fields to their nearest labels and headers
        contextual_fields = self._link_context(schema)
        
        # 2. Build a prompt with this rich context
        prompt = self._build_mapping_prompt(contextual_fields)

        # 3. Call the AI to get semantic purposes
        try:
            response = self.model.generate_content(prompt)
            mappings = dict(re.findall(r"(\S+):\s*(\S+)", response.text))

            # 4. Assign the returned purposes back to the original fields
            for field in schema.fields:
                if field.field_id in mappings:
                    purpose = mappings[field.field_id]
                    field.semantic_purpose = purpose if purpose.lower() != 'null' else None
            
            print("✅ Semantic mapping complete.")
            return schema

        except Exception as e:
            print(f"❌ Semantic mapping AI call failed: {e}")
            return schema

    def _link_context(self, schema: FormSchema) -> List[Dict]:
        """For each field, find the nearest label/header and UPDATE the field object."""
        
        headers = [
            l for l in schema.labels 
            if l.text.isupper() and len(l.text) > 3 and l.text not in ["YES", "NO"]
        ]

        contextual_fields = []
        for field in schema.fields:
            if not field.coordinates or not isinstance(field.coordinates, list) or not field.coordinates[0]:
                continue
            if not isinstance(field.coordinates[0], (list, tuple)):
                continue

            nearest_label = min(
                schema.labels, 
                key=lambda l: self._distance(field.coordinates, l.coordinates)
            )
            
            # Actually assign the found label text to the field object
            field.linked_label = nearest_label.text
            
            nearest_header = min(
                headers,
                key=lambda h: self._distance(field.coordinates, h.coordinates, vertical_weight=0.5)
            ) if headers else None

            contextual_fields.append({
                "field_id": field.field_id,
                "type": field.type,
                "label": field.linked_label, # Use the newly assigned label
                "header": nearest_header.text if nearest_header else "None"
            })
        return contextual_fields

    def _distance(self, p1, p2, vertical_weight=1.0):
        """
        Calculate weighted Euclidean distance between the centers of two boxes.
        Handles both nested and flat coordinate structures robustly.
        """
        # --- Sanitize Coordinates ---
        # This function ensures a coordinate, whether it's [[x,y,x,y]] or (x,y,x,y),
        # is returned as a simple (x,y,x,y) tuple.
        def sanitize(coord):
            if not coord:
                return (0, 0, 0, 0) # Return a default if empty
            if isinstance(coord[0], list) or isinstance(coord[0], tuple):
                return tuple(coord[0])
            return tuple(coord)

        box1 = sanitize(p1)
        box2 = sanitize(p2)

        c1 = ((box1[0] + box1[2]) / 2, (box1[1] + box1[3]) / 2)
        c2 = ((box2[0] + box2[2]) / 2, (box2[1] + box2[3]) / 2)
        return math.sqrt((c1[0] - c2[0])**2 + (vertical_weight * (c1[1] - c2[1]))**2)

    def _build_mapping_prompt(self, contextual_fields: List[Dict]) -> str:
        """Builds the prompt with context for the LLM."""
        context_str = "\n".join(
            [f"- ID: `{f['field_id']}` (Type: {f['type']}), Header: '{f['header']}', Label: '{f['label']}'" for f in contextual_fields]
        )

        return f"""
You are an expert in medical form data mapping. Your task is to assign a precise `semantic_purpose` to a list of form fields based on their context.

**Context Provided for Each Field:**
- `ID`: The unique identifier for the field.
- `Type`: The visual type of the field (`char_boxes`, `underline`, `checkbox`).
- `Header`: The nearest major section header (e.g., "Member Information", "Drug Information").
- `Label`: The closest text label to the field.

**Instructions:**
1.  Use the combination of `Header` and `Label` to determine the exact purpose.
2.  For a `checkbox`, the purpose should reflect the `Label` next to it (e.g., if the label is "Yes", the purpose is `..._yes`).
3.  If the purpose is ambiguous or the field is not for data entry, assign `null`.

**Crucial: Header and Label Examples**
- Header: 'Member Information', Label: 'Last name:' -> `patient_last_name`
- Header: 'Prescriber information', Label: 'Last name:' -> `prescriber_last_name`
- Header: 'Drug information', Label: 'Drug name:' -> `drug_name`
- Header: '...', Label: 'Yes' (for the age question) -> `clinical_question_is_patient_over_18_yes`

**Output Format:**
Return ONLY the mappings as `field_id: semantic_purpose` pairs, one per line.

**Fields to Process:**
{context_str}
"""

class DataExtractionAgent:
    """Uses an LLM to extract structured data from referral documents based on a schema."""
    def __init__(self):
        # Using the faster, more efficient model for data extraction as requested.
        self.model = genai.GenerativeModel('gemini-2.0-flash')

    def extract_data(self, referral_path: Path, required_data: Dict[str, str]) -> ExtractedData:
        """Performs targeted data extraction based on a dictionary of required purposes."""
        print(f"🔎 Activating Data Extraction Agent for: {referral_path.name}")

        if not required_data:
            print("⚠️ Warning: No required data points provided. Skipping extraction.")
            return ExtractedData()

        # 1. Convert referral document to images for the LLM
        doc = fitz.open(referral_path)
        page_images_b64 = []
        for page in doc:
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_data = pix.tobytes("png")
            page_images_b64.append(base64.b64encode(img_data).decode())
        doc.close()

        # 2. Build and execute the prompt
        prompt = self._build_extraction_prompt(required_data)
        model_input = [prompt]
        for img_b64 in page_images_b64:
            model_input.append({"mime_type": "image/png", "data": img_b64})

        print(f"🤖 Asking AI to extract {len(required_data)} data points...")

        try:
            response = self.model.generate_content(model_input,
                generation_config=genai.types.GenerationConfig(
                    response_mime_type="application/json"
                )
            )
            return self._parse_extraction_response(response.text)
        except Exception as e:
            print(f"❌ Data extraction failed: {e}")
            return ExtractedData()

    def _parse_extraction_response(self, response_text: str) -> ExtractedData:
        """
        Safely parses the JSON response from the LLM, handling cases where the AI
        might not perfectly follow the nested structure.
        """
        try:
            data = json.loads(response_text)
            print("✅ Data extraction successful.")
            
            # The AI doesn't always follow the "extracted_data" nesting instruction.
            # This makes our parsing more robust.
            if "extracted_data" in data and isinstance(data["extracted_data"], dict):
                # Ideal case: the AI followed instructions perfectly.
                return ExtractedData(data=data["extracted_data"])
            elif isinstance(data, dict) and any(data.values()):
                # Common case: the AI returned a flat JSON object with the data.
                print("   ⚠️ AI did not use the 'extracted_data' key. Processing flat JSON response.")
                return ExtractedData(data=data)
            else:
                # The JSON is valid but empty or in an unexpected format.
                print("   ⚠️ AI returned a valid but empty or unrecognized JSON structure.")
                return ExtractedData()

        except json.JSONDecodeError as e:
            print(f"❌ Error decoding JSON from extraction response: {e}")
            print(f"   Raw response: {response_text}")
            return ExtractedData()

    def _build_extraction_prompt(self, required_data: Dict[str, str]) -> str:
        """Builds a targeted prompt for data extraction from a dictionary."""
        
        data_points_str = "\n".join([f'- `{key}` (related to "{label}")' for key, label in required_data.items()])

        return f"""
You are a specialized data extraction bot for medical documents. Your task is to analyze the provided images of a patient's referral document and extract specific pieces of information.

**1. Goal:**
Find and extract the values for the following data points. The text in parentheses is the label from the form where this data will be placed, use it as a hint to find the correct value.

**Data to Extract:**
{data_points_str}

**2. Rules:**
- Read the entire document carefully to find the most accurate information.
- Provide the data in the requested JSON format.
- If you cannot find a value for a specific field, return `null` for that key. Do not make up information.
- For dates, use the format `MM/DD/YYYY`.
- For clinical questions (those starting with `clinical_question_`), answer based on the document content with "Yes", "No", or a specific value if requested.

**3. Output Format:**
You MUST return your findings as a single JSON object.

**Example JSON Output:**
```json
{{
  "extracted_data": {{
    "patient_last_name": "Chen",
    "patient_first_name": "Amy",
    "patient_dob": "05/23/1983",
    "prescriber_npi": "1234567890",
    "clinical_question_is_patient_over_18": "Yes"
  }}
}}
```

Now, analyze the document and return the extracted data.
"""

class FlatFormFillingAgent:
    """
    Fills a flat PDF form deterministically using a text-anchor schema and extracted data.
    This agent uses precise coordinates of labels, not AI-guessed fields.
    """
    def fill_form(self,
                  schema: FormSchema,
                  extracted_data: ExtractedData,
                  output_path: Path,
                  base_form_path: Path):
        
        print(f"🖋️ Activating Field-Aware Form Filling Agent.")
        if not extracted_data.data:
            print("⚠️ No data extracted. Aborting form filling.")
            return

        doc = fitz.open(base_form_path)
        
        purpose_to_field_map: Dict[str, FormField] = {
            field.semantic_purpose: field
            for field in schema.fields if field.semantic_purpose
        }
        
        fields_filled = 0
        for purpose, value in extracted_data.data.items():
            if value is None or str(value).lower() == 'null':
                continue

            if purpose in purpose_to_field_map:
                field = purpose_to_field_map[purpose]
                page = doc[field.page_num]
                insert_text = str(value)

                if field.type == "char_boxes":
                    self._fill_char_boxes(page, field, insert_text)
                    fields_filled += 1
                elif field.type == "underline":
                    self._fill_underline(page, field, insert_text)
                    fields_filled += 1
                elif field.type == "checkbox" and str(value).lower() in ["yes", "true", "x"]:
                    self._fill_checkbox(page, field)
                    fields_filled += 1
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(output_path), garbage=4, deflate=True, clean=True)
        doc.close()
        print(f"✅ Form filling complete. {fields_filled} fields filled. Saved to: {output_path}")

    def _get_absolute_coords(self, page: fitz.Page, normalized_coords: List[float]) -> fitz.Rect:
        page_width = page.rect.width
        page_height = page.rect.height
        # This handles both [[x,y,x,y]] and [x,y,x,y] formats
        coords = normalized_coords[0] if isinstance(normalized_coords[0], list) else normalized_coords
        return fitz.Rect(coords[0] * page_width, coords[1] * page_height, coords[2] * page_width, coords[3] * page_height)

    def _fill_char_boxes(self, page: fitz.Page, field: FormField, text: str):
        text_to_place = re.sub(r'[^a-zA-Z0-9]', '', text).upper()
        if not field.coordinates or not field.box_count: return

        first_box_rect = self._get_absolute_coords(page, field.coordinates[0])
        box_width = first_box_rect.width
        box_spacing = box_width * 0.15

        for i in range(min(len(text_to_place), field.box_count)):
            char = text_to_place[i]
            x_offset = i * (box_width + box_spacing)
            char_rect = fitz.Rect(first_box_rect.x0 + x_offset, first_box_rect.y0, first_box_rect.x0 + x_offset + box_width, first_box_rect.y1)
            
            font_size = char_rect.height * 0.75
            text_width = fitz.get_text_length(char, fontname="helv", fontsize=font_size)
            x_centered = char_rect.x0 + (char_rect.width - text_width) / 2
            page.insert_text((x_centered, char_rect.y1 - (char_rect.height * 0.15)), char, fontsize=font_size, fontname="helv")

    def _fill_underline(self, page: fitz.Page, field: FormField, text: str):
        if not field.coordinates: return
        rect = self._get_absolute_coords(page, field.coordinates)
        font_size = max(rect.height * 0.8, 8)
        page.insert_text((rect.x0, rect.y1), text, fontsize=font_size, fontname="helv")

    def _fill_checkbox(self, page: fitz.Page, field: FormField):
        if not field.coordinates: return
        rect = self._get_absolute_coords(page, field.coordinates)
        shape = page.new_shape()
        shape.draw_line(rect.tl, rect.br)
        shape.draw_line(rect.bl, rect.tr)
        shape.finish(color=(0, 0, 0), width=0.7)
        shape.commit()

class SchemaHarvesterAgent:
    """
    Finds BOTH precise text coordinates (using PyMuPDF) and visual field
    coordinates (using a visual AI model).
    """
    def __init__(self):
        self.model = genai.GenerativeModel('gemini-2.5-pro')
        self.text_anchor_agent = TextAnchorAgent() # Use the deterministic agent

    def harvest_schema(self, pa_form_path: Path) -> FormSchema:
        print(f"🌾 Activating Hybrid Schema Harvester for: {pa_form_path.name}")

        # 1. Find all text anchors deterministically
        labels = self.text_anchor_agent.find_text_anchors(pa_form_path)

        # 2. Find all visual fields using the AI model
        fields = self._harvest_visual_fields(pa_form_path)
        
        schema = FormSchema(labels=labels, fields=fields)
        print(f"✅ Hybrid schema harvested with {len(labels)} labels and {len(fields)} fields.")
        return schema

    def _harvest_visual_fields(self, pa_form_path: Path) -> List[FormField]:
        """
        Uses progressive, type-specific AI calls to identify all visual
        fillable fields on the form.
        """
        print("🤖 Harvesting visual fields (underlines, char_boxes, checkboxes)...")
        
        doc = fitz.open(pa_form_path)
        page_images_b64 = []
        for page in doc:
            mat = fitz.Matrix(300/72, 300/72) # High DPI for better analysis
            pix = page.get_pixmap(matrix=mat, alpha=False)
            page_images_b64.append(base64.b64encode(pix.tobytes("png")).decode())
        doc.close()

        all_fields = []
        field_types_to_harvest: List[Literal["char_boxes", "underline", "checkbox"]] = ["char_boxes", "underline", "checkbox"]

        for field_type in field_types_to_harvest:
            print(f"  -> Harvesting type: {field_type}")
            prompt = self._build_visual_harvesting_prompt(field_type)
            
            model_input = [prompt]
            for img_b64 in page_images_b64:
                model_input.append({"mime_type": "image/png", "data": img_b64})
            
            try:
                response = self.model.generate_content(model_input,
                    generation_config=genai.types.GenerationConfig(
                        response_mime_type="application/json"
                    )
                )
                response_json = json.loads(response.text)
                fields_data = response_json.get("fields", [])
                
                for field_data in fields_data:
                    # Basic validation
                    if field_data.get('type') == field_type:
                        # Ensure all required fields are present before creating the object
                        if all(k in field_data for k in ['field_id', 'page_num', 'type', 'coordinates']):
                           all_fields.append(FormField(**field_data))
                
                print(f"     ✅ Found {len(fields_data)} fields.")

            except Exception as e:
                print(f"     ❌ ERROR: AI call failed for '{field_type}'. Reason: {e}")
                continue
        
        return all_fields

    def _build_visual_harvesting_prompt(self, field_type: Literal["char_boxes", "underline", "checkbox"]) -> str:
        """Builds a detailed, FOCUSED prompt for harvesting a single type of visual field."""
        prompt = f"""
You are a document analysis AI specialized in identifying the structure of forms. Your sole task is to find all visual elements of a specific type: `{field_type}`. Do not identify any other types.

**Key Task:**
Analyze the provided form images and return a JSON object containing the coordinates and details for ONLY the `{field_type}` elements.

**Extraction Requirements for Each Field:**
- `field_id`: Create a unique, descriptive ID in snake_case (e.g., `patient_last_name_boxes`, `drug_name_underline`).
- `page_num`: The 0-indexed page number where the field appears.
- `type`: This MUST be `{field_type}` for this specific task.
- `coordinates`: The normalized [x1, y1, x2, y2] bounding box for the field.
- `box_count` (REQUIRED and ONLY for `char_boxes`): The total number of individual character boxes in the sequence.

**Coordinate & Field-Specific Rules (CRITICAL):**
- For `char_boxes`: The `coordinates` must be for the **FIRST box** in the sequence only. `box_count` must be the total number of boxes.
- For `underline`: The `coordinates` must be for the entire continuous line.
- For `checkbox`: The `coordinates` must be for the checkable square itself.

**Output Format:**
- You MUST return a single, valid JSON object.
- The object must contain a single key, "fields", which is a list.
- If no fields of the specified type are found, return an empty list: `{{"fields": []}}`.

**Example for a `char_boxes` task:**
```json
{{
  "fields": [
    {{
      "field_id": "member_id_boxes",
      "page_num": 0,
      "type": "char_boxes",
      "coordinates": [[0.12, 0.33, 0.14, 0.35]],
      "box_count": 11
    }}
  ]
}}
```

Now, analyze the form images with extreme precision. Find and return the JSON for `{field_type}` fields ONLY.
"""
        return prompt

class MandolinPipeline:
    """
    Orchestrates the entire PA form processing workflow using the new
    text-anchor, decoupled agent architecture.
    """
    def __init__(self):
        # Main system components based on the new architecture
        self.harvester = SchemaHarvesterAgent()
        self.text_anchor_agent = TextAnchorAgent()
        self.mapper = SemanticMapperAgent()
        self.extractor = DataExtractionAgent()
        self.filler = FlatFormFillingAgent()
        self.schema_cache: Dict[str, FormSchema] = {}

    def get_cached_schema(self, form_path: Path) -> Optional[FormSchema]:
        """Checks for a pre-harvested schema JSON file."""
        cache_file = form_path.with_suffix('.schema.json')
        if cache_file.exists():
            print(f"Found cached schema: {cache_file}")
            try:
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                    # Updated to parse both labels and fields for the hybrid schema
                    labels = [FormLabel(**label_data) for label_data in data.get("labels", [])]
                    fields = [FormField(**field_data) for field_data in data.get("fields", [])]
                    return FormSchema(labels=labels, fields=fields)
            except Exception as e:
                print(f"Warning: Could not load cached schema. Re-harvesting. Reason: {e}")
        return None

    def save_schema_to_cache(self, form_path: Path, schema: FormSchema):
        """Saves a harvested schema to a JSON file."""
        cache_file = form_path.with_suffix('.schema.json')
        try:
            with open(cache_file, 'w') as f:
                json.dump(schema.to_dict(), f, indent=2)
            print(f"Schema saved to cache: {cache_file}")
        except Exception as e:
            print(f"Error saving schema to cache: {e}")


    def process_pa(self, patient_name: str, referral_path: Path, pa_form_path: Path, output_dir: Path):
        """
        Executes the full, robust pipeline for processing a single PA request.
        """
        print("\n" + "="*50)
        print(f"🚀 Starting Mandolin Pipeline for Patient: {patient_name}")
        print(f"   Referral Doc: {referral_path.name}")
        print(f"   PA Form: {pa_form_path.name}")
        print("="*50 + "\n")

        schema = self.get_cached_schema(pa_form_path)
        if not schema:
            print("Harvesting new schema...")
            # Phase 1: Hybrid Harvesting
            schema = self.harvester.harvest_schema(pa_form_path)

            # Phase 2: Contextual Linking and Mapping
            schema = self.mapper.map_semantics(schema)
            self.save_schema_to_cache(pa_form_path, schema)

        # The DataExtractionAgent now takes the dictionary directly
        required_purposes = {
            f.semantic_purpose: f.linked_label 
            for f in schema.fields if f.semantic_purpose and f.linked_label
        }
        
        if not required_purposes:
            print("❌ Pipeline halted: No semantic purposes could be mapped.")
            return
            
        extracted_data = self.extractor.extract_data(referral_path, required_purposes)

        if not extracted_data.data:
            print("❌ Pipeline halted: Data extraction failed.")
            return

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"{patient_name.replace(' ', '_')}_PA_{timestamp}.pdf"
        output_path = output_dir / output_filename

        self.filler.fill_form(schema, extracted_data, output_path, pa_form_path)

        print("\n" + "="*50)
        print("✅ Mandolin Pipeline finished successfully.")
        print("="*50 + "\n")


def find_files(directory: Path, name_contains: str) -> Optional[Path]:
    """Finds the first file in a directory whose name contains a string."""
    for item in directory.iterdir():
        if item.is_file() and name_contains in item.name and item.name.lower().endswith('.pdf'):
            return item
    return None


def main():
    """Main function to run the Mandolin PA processing pipeline."""
    # Define directories
    base_dir = Path(__file__).parent
    input_dir = base_dir / "pa_forms" / "patient_documents"
    output_dir = base_dir / "pa_forms" / "completed"

    # Find the necessary files
    # In a real system, this would come from a queue or database
    referral_doc_path = find_files(input_dir, "Referral")
    pa_form_path = find_files(input_dir, "FORM")

    if not referral_doc_path or not pa_form_path:
        print("❌ Error: Could not find required 'Referral' and 'FORM' files in the input directory.")
        return

    # Patient name could be extracted or passed as an argument
    patient_name = "Amy Chen" 

    # Initialize and run the pipeline
    pipeline = MandolinPipeline()
    pipeline.process_pa(
        patient_name=patient_name,
        referral_path=referral_doc_path,
        pa_form_path=pa_form_path,
        output_dir=output_dir
    )

if __name__ == "__main__":
    main() 