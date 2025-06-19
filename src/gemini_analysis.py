import os
import pathlib
import json
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-flash")

def extract_key_data(pdf_path, prompt):
    pdf_bytes = pathlib.Path(pdf_path).read_bytes()
    response = model.generate_content([
        {"mime_type": "application/pdf", "data": pdf_bytes},
        prompt
    ])
    return response.text

pdf_path = "Input Data/Akshay/referral_package.pdf"
prompt = (
    "Extract patient first name, last name, DOB, diagnosis, provider name, NPI, insurance ID, and medication. "
    "Return result as JSON with keys: patient_first, patient_last, dob, diagnosis, provider_name, npi, insurance_id, medication."
)

result = extract_key_data(pdf_path, prompt)

# Clean up response
cleaned_result = result.strip()
if cleaned_result.startswith("```json"):
    cleaned_result = cleaned_result.replace("```json", "").strip()
if cleaned_result.endswith("```"):
    cleaned_result = cleaned_result[:-3].strip()

# Now parse
with open("data/Akshay.json", "w") as f:
    json.dump(json.loads(cleaned_result), f, indent=2)

