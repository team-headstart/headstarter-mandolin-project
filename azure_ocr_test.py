import requests
import time

endpoint = "https://my-first-dom.cognitiveservices.azure.com"
key = "Bllb7gQ6e9YgzSX7orRiMANtod9AZRjGGOfTgMVjRIWBGzt4PxRvJQQJ99BFACYeBjFXJ3w3AAAFACOGKey7"

headers = {
    "Ocp-Apim-Subscription-Key": key,
    "Content-Type": "image/png"
}

# Step 1: Send image to Azure
with open("image.png", "rb") as f:
    data = f.read()

response = requests.post(
    endpoint + "/vision/v3.2/read/analyze",
    headers=headers,
    data=data
)

if response.status_code != 202:
    print("❌ Error:", response.status_code)
    print(response.text)
    exit()

# Step 2: Get the Operation-Location URL
operation_url = response.headers.get("Operation-Location")

# Step 3: Poll for result
print("⏳ Waiting for OCR result...")
time.sleep(3)  # wait before polling

while True:
    result = requests.get(operation_url, headers={"Ocp-Apim-Subscription-Key": key})
    result_json = result.json()
    
    status = result_json["status"]
    if status == "succeeded":
        print("✅ OCR Result:")
        for line in result_json["analyzeResult"]["readResults"][0]["lines"]:
            print(line["text"])
        break
    elif status == "failed":
        print("❌ OCR Failed")
        break
    else:
        print("⌛ Still processing...")
        time.sleep(2)

def extract_patient_info(ocr_text):
    info = {
    }
    
    lines = ocr_text.splitlines()

    for line in lines:
        line = line.strip()
        if line.startswith("Patient Name: "):
            name = line.split(":", 1)[1].strip()
            info["T6"] = name.split()[0]
            info["T7"] = name.split()[1]
        if line.startswith("Diagnosis: "):
            diagnosis = line.split(":", 1)[1].strip()
            info["T35"] = diagnosis
            
    
        