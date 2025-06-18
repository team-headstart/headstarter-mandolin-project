### README: Prior Authorization (PA) Form Automation Pipeline

📄 Project Overview

This project is an automation pipeline designed to process Prior Authorization (PA) forms using OCR and text extraction from scanned documents. It aims to extract relevant patient information from scanned referral packages and fill it into a structured PA form PDF.

This is my first major project as a Headstarter Software Engineering Resident. I approached this challenge with a mindset to struggle intentionally and grow through exploration before seeking heavy external support. The current submission represents an MVP (Minimum Viable Product), demonstrating key pipeline logic with room for future extension.

🔹 What I Implemented

### 1. OCR Text Extraction (Azure OCR)

Used Microsoft Azure's Computer Vision API to process scanned PDFs and return machine-readable text.

Successfully parsed a high-resolution PDF (referral_package.pdf) using Azure endpoint and key.
### 2. **Parsing Relevant Patient Info**
- Wrote a custom parser to extract fields like:
  - First name (field: `T6`)
  - Last name (field: `T7`)
  - Diagnosis (field: `T35`)
  - Fax number (field: `T20`)
- Used `.split()`, `.startswith()`, and dictionaries to associate parsed values with field identifiers.

### 3. **Form Field Mapping and Filling**
- Identified PDF form fields using `PyPDF2.get_fields()`
- Mapped internal field names (e.g., `T6`, `T20`) to OCR-extracted data
- Wrote a form-filling function using `PdfReader`, `PdfWriter`, and `update_page_form_field_values`

### 4. **Manual Testing for Mapping**
- Wrote a temporary script to inject dummy values (`T6_TEST`, etc.) into form to identify field placements

### 📈 Submission Summary
- Documented codebase (functions for parsing and filling)
- Working OCR extraction pipeline
- Working form field filler logic for a handful of sample fields
- `README.md` and comments showing my thought process and progress

**Branch:** `automation-pa-filling-quamdeen`

**Submitted by:** Quamdeen Olajide
