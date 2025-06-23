import base64
import os
import json
import pathlib
from typing import List, Optional
from pydantic import BaseModel, Field
from mistralai import Mistral
from dotenv import load_dotenv
from google import genai
from google.genai import types
from prompts import get_ocr_analysis_prompt, get_system_prompt, get_system_data_collection_prompt, get_data_collection_prompt, get_pdf_analysis_prompt
from datetime import datetime
import pymupdf
import time

# Load environment variables from .env file
load_dotenv()

# Timing function
def time_step(step_name: str):
    """Decorator to time a function execution."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            start_time = time.time()
            result = func(*args, **kwargs)
            end_time = time.time()
            duration = end_time - start_time
            print(f"⏱️  {step_name} completed in {duration:.2f} seconds")
            return result
        return wrapper
    return decorator

# Pydantic models for structured data
class ImageData(BaseModel):
    id: str
    top_left_x: int
    top_left_y: int
    bottom_right_x: int
    bottom_right_y: int
    image_base64: str

class PageDimensions(BaseModel):
    dpi: int
    height: int
    width: int

class OCRPage(BaseModel):
    index: int
    markdown: str
    images: List[ImageData]
    dimensions: PageDimensions

class OCRResponse(BaseModel):
    pages: List[OCRPage]

class PAFormField(BaseModel):
    name: str
    page: int
    field_type_string: str
    field_label: str
    context: str = Field(default="")
    
class PAFormAnswer(BaseModel):
    name: str
    page: int
    field_type_string: str
    field_label: str
    context: str
    answer: str = Field(default="Answer to the question based on the provided referral package data.")

class PAFormFields(BaseModel):
    fields: List[PAFormField]
    
class PAFormAnswers(BaseModel):
    answers: List[PAFormAnswer]

def encode_pdf(pdf_path):
    """Encode the pdf to base64."""
    try:
        with open(pdf_path, "rb") as pdf_file:
            return base64.b64encode(pdf_file.read()).decode('utf-8')
    except FileNotFoundError:
        print(f"Error: The file {pdf_path} was not found.")
        return None
    except Exception as e:  # General exception handling
        print(f"Error: {e}")
        return None
    
# Path to your pdf
pa_pdf_path = "./Input Data/Abdulla/PA.pdf"

# Getting the base64 string
base64_pdf = encode_pdf(pa_pdf_path)

# Start overall timing
overall_start_time = time.time()

'''
STEP 1:
PyMuPDF PDF Breakdown

Parses over the PA PDF and returns a breakdown of the PDF with its pages, fields, field options, and more. 
'''

@time_step("Step 1: PyMuPDF Field Extraction")
def extract_pa_pdf_fields(pdf_path: str) -> dict:
    doc = pymupdf.open(pdf_path)
    fields = []
    for page_num, page in enumerate(doc, start=1):
        widgets = page.widgets()
        for w in widgets:
            field = {
                "name": w.field_name,
                "type": w.field_type,
                "value": w.field_value,
                "page": page_num,
                "field_type": w.field_type,
                "field_type_string": w.field_type_string,
                "field_label": w.field_label,
            }
            fields.append(field)
    return fields
pa_pdf_fields = extract_pa_pdf_fields(pa_pdf_path)

# Convert list of fields to object format expected by PAFormFields
pa_pdf_fields_obj = {"fields": pa_pdf_fields}

structured_pa_pdf_fields = PAFormFields.model_validate(pa_pdf_fields_obj)


''' 
STEP 2:
Mistral OCR API Call
- model: mistral-ocr-latest
- document:
    - type: document_url
    - document_url: base64 encoded pdf
- include_image_base64: True
- response_format: markdown

Parses over the Base64 encoded PA PDF and returns a JSON object with markdown text
containing the contents of the PDF.
'''


mistrtal_api_key = os.environ["MISTRAL_API_KEY"]
client = Mistral(api_key=mistrtal_api_key)

@time_step("Step 2: OCR Processing")
def process_pdf_with_ocr(pdf_path: str) -> OCRResponse:
    """Process a PDF file with OCR and return structured response."""
    
    # Encode the PDF to base64
    base64_pdf = encode_pdf(pdf_path)
    if not base64_pdf:
        raise FileNotFoundError(f"PDF file not found at {pdf_path}")
    
    # Initialize Mistral client
    mistral_api_key = os.environ["MISTRAL_API_KEY"]
    client = Mistral(api_key=mistral_api_key)
    
    # Process PDF with OCR
    ocr_response = client.ocr.process(
        model="mistral-ocr-latest",
        document={
            "type": "document_url",
            "document_url": f"data:application/pdf;base64,{base64_pdf}" 
        },
        include_image_base64=True,
    )
    
    # Convert Mistral response to our Pydantic model
    try:
        structured_response = OCRResponse(
            pages=[
                OCRPage(
                    index=page.index,
                    markdown=page.markdown,
                    images=[
                        ImageData(
                            id=image.id,
                            top_left_x=image.top_left_x,
                            top_left_y=image.top_left_y,
                            bottom_right_x=image.bottom_right_x,
                            bottom_right_y=image.bottom_right_y,
                            image_base64=image.base64
                        )
                        for image in page.images
                    ],
                    dimensions=PageDimensions(
                        dpi=page.dimensions.dpi,
                        height=page.dimensions.height,
                        width=page.dimensions.width
                    )
                )
                for i, page in enumerate(ocr_response.pages or [])
            ]
        )
        
        return structured_response
        
    except Exception as e:
        print(f"Error processing OCR response: {e}")
        raise

# Process the PA form
try:
    structured_response = process_pdf_with_ocr(pa_pdf_path)
    print("Successfully processed PA form with OCR")
except Exception as e:
    print(f"Error in OCR processing: {e}")
    exit(1)

'''
STEP 3:
LLM Pre-Processing API Call
- model: gemini-2.5-flash-preview-05-20
- text:
    - type: markdown
    - markdown: markdown text from the OCR response
- response_format: json_object

Parses over the markdown text from the OCR response and returns a JSON object with 
the fillable fields parsed out and their corresponding value types.
'''
@time_step("Step 3: LLM Analysis")
def process_with_llm(system_prompt: str, prompt: str, pdf_path: str, response_format: str = None, model: str = "gemini-2.5-flash-lite-preview-06-17",) -> str:
    """Process OCR text with LLMs to extract structured information."""
    
    gemini_upload_filepath = pathlib.Path(pdf_path)
    
    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    
    response = client.models.generate_content(
        model=model,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            response_schema=response_format
            ),
          contents=[
            types.Part.from_bytes(
                data=gemini_upload_filepath.read_bytes(),
                mime_type='application/pdf',
            ),
            prompt]
    )
    # print(response.text)
    return response.text



try:
    # Process all pages from the OCR response
    llm_analysis = process_with_llm(system_prompt=get_system_prompt(), 
                                    prompt=get_pdf_analysis_prompt(
                                        pa_pdf_fields=structured_pa_pdf_fields, ocr_text=structured_response), 
                                    response_format=PAFormFields, 
                                    pdf_path=pa_pdf_path)
    print("Successfully processed PA form with LLM including OCR + PyMuPDF")
except Exception as e:
    print(f"Error in LLM processing: {e}")


'''
STEP 4:
Saving LLM Processing of PA Form

Saves the processed OCR content with the fields, field options, and descriptions to a JSON folder organized by the patient's name similar to how it is provided in input data.
'''

@time_step("Step 4: Data Saving")
def save_processed_data(patient_name: str, ocr_response: OCRResponse, llm_analysis: dict):
    """Save processed data in a nested folder structure matching input data organization."""
    
    # Create output directory structure
    output_base = "Output Data"
    patient_dir = os.path.join(output_base, patient_name)
    os.makedirs(patient_dir, exist_ok=True)
    
    # Save LLM analysis
    llm_file = os.path.join(patient_dir, "Extracted_Fields.json")
    with open(llm_file, 'w') as f:
        json.dump(llm_analysis, f, indent=2)
    
    print(f"Processed data saved to {patient_dir}")

# Extract patient name from input path and save processed data
patient_name = os.path.basename(os.path.dirname(pa_pdf_path))
save_processed_data(patient_name, structured_response, json.loads(llm_analysis))


# '''
# Step 5:
# AI Gathering of Necessary Field Data for Entry
# - model: gemini-2.5-flash-preview-05-20
# - text:
#     - type: application/json
#         - llm_analysis
#     - type: application/pdf
#         - referral_package.pdf
# - response_format: json_object

# Provided the full referral_package and the OCR derived fields, the AI model will be allowed to collect the information it deems necessary to fill in the fields appropriately. The AI model will be passed the extracted fields and the referral package pdf.
# '''

# @time_step("Step 5: Direct Field Data Collection")
# def gather_field_input_data(llm_field_analysis: dict) -> dict:
#     """Gather and structure field data from PA form and referral package for form entry."""
    
#     client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    
#     # Referral package path
#     referral_package_pdf_path = "./Input Data/Abdulla/referral_package.pdf"
#     filepath = pathlib.Path(referral_package_pdf_path)
    
#     system_prompt = get_system_data_collection_prompt()
#     prompt = get_data_collection_prompt(llm_field_analysis)
    
#     # Get the model's analysis
#     response = client.models.generate_content(
#         model="gemini-2.5-flash-preview-05-20",
#         config=types.GenerateContentConfig(
#             system_instruction=system_prompt,
#             response_mime_type="application/json"),
#         contents=[
#             types.Part.from_bytes(
#                 data=filepath.read_bytes(),
#                 mime_type='application/pdf',
#             ),
#             prompt]
#     )
    
#     # Parse and return the structured field data
#     field_data = json.loads(response.text)
    
#     # Save the field data
#     patient_name = os.path.basename(os.path.dirname(pa_pdf_path))
#     output_dir = os.path.join("Output Data", patient_name)
#     field_data_file = os.path.join(output_dir, "Field_Data_Direct.json")
    
#     with open(field_data_file, 'w') as f:
#         json.dump(field_data, f, indent=2)
    
#     print(f"Field data saved to {field_data_file}")
#     return field_data

# # Process the field data
# try:
#     field_data_direct = gather_field_input_data(json.loads(llm_analysis))
#     print("Successfully processed PA and referral packaged directly with Gemini Document Analysis")
# except Exception as e:
#     print(f"Error in field data gathering: {e}")
    

'''
Step 5:
AI Gathering of Necessary Field Data for Entry
- model: gemini-2.5-flash-preview-05-20
- text:
    - type: application/json
        - llm_analysis
    - type: application/pdf
        - referral_package.pdf
- response_format: json_object

Provided an OCR derived referral package and the OCR derived fields, the AI model will be allowed to collect the information it deems necessary to fill in the fields appropriately. The AI model will be passed the extracted fields and the extracted referral package pdf.
'''

@time_step("Step 6: OCR Field Data Collection")
def gather_field_input_data_ocr(llm_analysis: dict):
    
    
    try:
        referral_package_pdf_path = "./Input Data/Abdulla/referral_package.pdf"
        referral_package_structured_response = process_pdf_with_ocr(referral_package_pdf_path)
        
        output_base = "Output Data"
        patient_dir = os.path.join(output_base, "Abdulla")
        os.makedirs(patient_dir, exist_ok=True)
        
    except Exception as e:
        print(f"Error in OCR processing: {e}")
        exit(1)

    try:
    # Process all pages from the OCR response
        field_data_text = process_with_llm(get_system_data_collection_prompt(), 
                                           prompt=get_data_collection_prompt(llm_analysis, referral_package_ocr=referral_package_structured_response), 
                                           response_format=PAFormAnswers,
                                           pdf_path=referral_package_pdf_path,
                                           model="gemini-2.5-pro")
    except Exception as e:
        print(f"Error in LLM processing: {e}")
        
    field_data = json.loads(field_data_text)
    
    # Save the field data
    patient_name = os.path.basename(os.path.dirname(pa_pdf_path))
    output_dir = os.path.join("Output Data", patient_name)
    field_data_file = os.path.join(output_dir, "Completed_Form_Fields.json")
    
    with open(field_data_file, 'w') as f:
        json.dump(field_data, f, indent=2)
    
    print(f"Field data saved to {field_data_file}")
    return field_data
        
try:
    field_data_ocr = gather_field_input_data_ocr(json.loads(llm_analysis))
    print("Successfully processed PA and referral packaged with AI OCR + Gemini Document Analysis")
except Exception as e:
    print(f"Error in field data gathering: {e}")

# End overall timing
overall_end_time = time.time()
overall_duration = overall_end_time - overall_start_time
print(f"\n🎯 Total processing time: {overall_duration:.2f} seconds ({overall_duration/60:.2f} minutes)")