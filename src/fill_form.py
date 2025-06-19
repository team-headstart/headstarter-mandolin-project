import fitz  # PyMuPDF
import json
import os

# Load extracted JSON data
with open("data/Akshay.json") as f:
    data = json.load(f)

# Open the PDF
pdf_path = "Input Data/Akshay/PA.pdf"
doc = fitz.open(pdf_path)

# Define field -> value mapping
field_values = {
    "T11": data.get("patient_first", ""),
    "T12": data.get("patient_last", ""),
    "T13": data.get("dob", ""),
    "T21F": data.get("diagnosis", ""),
    "Request by T": data.get("medication", "")
}

# Fill the form
for page in doc:
    for field_name, value in field_values.items():
        for widget in page.widgets():
            if widget.field_name == field_name:
                widget.field_value = value
                widget.update()

# Save output
os.makedirs("output", exist_ok=True)
output_path = "output/Akshay_filled.pdf"
doc.save(output_path)
print(f"✅ Filled form")