### Task: Automate the Prior Authorization (PA) Form Filling Workflow


My Video talking through the process: https://youtu.be/Cs-54xvcnuQ

Jupyter Notebook file: `main.ipynb` is labelled with different sections

Extracting Information from Referral Packages:

1st Method: Used OCRmyPDF to scan and textualise, PDFPlunmber to extract as much text data as possible
2nd Method: Used Pytesseract to directly use OCR scanning

Extracting Information from PA Form:

- Used Fitz from PyMuPDF to get all the form-fillable sections & create a dictionary
- Use Gemini to get context of each fillable section and what to look for from the referral package to answer
- Pass all available data to allow the LLM to generate the most-likely answer
- Use Fitz to populate each field with an answer if available, else leave empty
- Output the file to `/Output Data/PA_filled.pdf`