## Automated Prior Authorization Filling System

This repository contains an advanced AI pipeline designed to automate the filling of both interactive (widget-based) and flat (non-interactive) Prior Authorization (PA) forms. The system uses a sophisticated multi-agent architecture to analyze, extract, and populate forms, significantly reducing the manual administrative burden on healthcare providers.

## 1. My Thought Process & Architectural Decisions

The primary challenge of this project was the need to handle two fundamentally different types of PDFs. A single system cannot reliably process both widget-based and flat forms. My solution was to develop two distinct, specialized pipelines, each orchestrated by its own script.

### Multi-Agent Architecture 1: The Interactive Pipeline (`MANDOLIN_PA_SYSTEM.py`)

This system is designed for modern, widget-based PDFs that have pre-defined, interactive fields (text boxes, checkboxes, etc.).

-   **Form Understanding:** The pipeline begins by using a vision-capable AI (`gemini-2.0-flash`) to analyze the form's visual layout and structure, creating an initial schema of all available fields.
-   **Semantic Refinement:** A more powerful AI (`gemini-2.5-pro`) then refines this schema, assigning a precise, machine-readable `semantic_purpose` to each field (e.g., mapping the visual label "Patient First Name" to the key `patient_first_name`). This standardization is key to making the system adaptable to new forms.
-   **Parallel Extraction:** The system then uses two agents in parallel:
    -   A `DataExtractionAgent` reads the patient's referral documents to find demographic and other standard information.
    -   A specialized `ClinicalQAAgent` focuses solely on answering the complex "Yes/No" clinical questions on the form.
-   **Validation & Correction:** In a critical "fill-and-verify" loop, the system performs a first-pass fill of the form and then hands it off to a `ValidationAgent`. This powerful AI (`gemini-2.5-pro`) visually inspects the filled document, compares it against the source data, and generates a list of corrections for any hallucinations, formatting errors, or misplaced data. This self-correction loop dramatically increases the final accuracy.
-   **Finalization:** The corrections are applied, and a final, flattened PDF is generated alongside a report detailing any information that could not be found.

###  Multi-AgentArchitecture 2: The "Text-Anchor" Pipeline for Flat PDFs (`FLAT_PA_SYSTEM.py`)

Flat PDFs are much more challenging as they have no structured fields. Attempting to use AI to visually "guess" the coordinates of where to write text is notoriously unreliable and prone to alignment errors.

To solve this, I developed the **Text-Anchor** system, a more deterministic and robust approach:

-   **The "Surveyor" (`TextAnchorAgent`):** This is a code-based agent that uses the `PyMuPDF` library to get the *exact* pixel coordinates of every text label on the form. This creates a perfect, unchangeable "ground truth" map of the document, completely avoiding AI guesswork for layout.
-   **The "Interpreter" (`SemanticMapperAgent`):**  (`gemini-2.5-pro`) is used for what it does best: language understanding. It takes the list of text labels and assigns a `semantic_purpose` to each one. This result is cached to avoid re-processing the same form type.
-   **The "Scribe" (`TextAnchorFillingAgent`):** This non-AI agent is the core of the system's reliability. It operates on simple, predictable logic:
    1.  It finds the coordinates of a label (e.g., the label "Last Name:").
    2.  It programmatically calculates an insertion point a few pixels to the right of that label.
    3.  It writes the corresponding extracted data directly onto the form.

This architecture ensures perfect alignment and accuracy by using each tool for its strength: `PyMuPDF` for geometric precision and the AI for language understanding.

## 2. Installation

Follow these steps to set up and run the project locally.

**Prerequisites:**
- Python 3.9+
- An API key for Google's Gemini models.

**Setup:**

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/[your-username]/headstarter-mandolin-project.git
    cd headstarter-mandolin-project
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configure your environment:**
    -   Create a file named `.env` in the project root.
    -   Add your Google Gemini API key to this file:
        ```
        GEMINI_API_KEY="YOUR_API_KEY_HERE"
        ```

## 3. How to Run the Pipelines

The project contains two primary pipeline scripts. All output, including filled PDFs and processing reports, will be placed in the `output_examples/` directory.

### To Run the Flat PDF Pipeline:


```bash
python3 FLAT_PA_SYSTEM.py
```

### To Run the Interactive PDF Pipeline:

This pipeline is configured to look for interactive forms in the `Input Data/` directory. As there are no interactive forms in the base repository, running this script will demonstrate its ability to gracefully skip patients for whom it cannot find a valid form.

```bash
python3 MANDOLIN_PA_SYSTEM.py
```

## 4. Output Examples

This submission includes comprehensive examples of filled PA forms and processing reports demonstrating both pipeline architectures:

### Interactive PDF Pipeline Results (`Output Data/`)
- **Adbulla**:
  - `Adbulla_PA_filled.pdf` & `Adbulla_PA_filled_v1.pdf` - Filled forms with validation corrections
  - `Adbulla_processing_report.md` - Missing information report (18.0% fill rate)
  - `Adbulla_extracted_data.json` - Raw extracted data (249 fields)
  - `Adbulla_corrections.json` - Validation corrections applied

- **Akshay**:
  - `Akshay_PA_filled.pdf` & `Akshay_PA_filled_v1.pdf` - Filled forms with validation corrections
  - `Akshay_processing_report.md` - Missing information report (40.7% fill rate)
  - `Akshay_extracted_data.json` - Raw extracted data (120 fields)
  - `Akshay_corrections.json` - Validation corrections applied

### Flat PDF Pipeline Results (`output_examples/`)
- **Amy Chen**:
  - `Amy_Chen_PA_20250618_183606.pdf` - Text-anchor filled form
  - `Amy_Chen_processing_report.md` - Missing information report

- **Additional Test Results**:
  - Multiple timestamped versions showing iterative improvements
  - `Adbulla_PA_*.pdf` - Various test runs with different configurations
  - `Amy_PA_*.pdf` - Flat PDF system test results

### Performance Summary
- **Interactive Pipeline**: Handles complex widget-based forms with validation loop
- **Flat PDF Pipeline**: Deterministic text-anchor positioning for non-interactive forms
- **Fill Rates**: 18.0% - 40.7% depending on form complexity and data availability
- **Self-Correction**: Validation agent identifies and fixes AI hallucinations
- **Universal Design**: Works with any unseen PA form through schema-first approach

### Processing report for Akshey -> 

The following information could not be found in the referral documents:

/ (Needed for field with purpose: request_date_separator_1)
/ (Needed for field with purpose: request_date_separator_2)
/ (Needed for field with purpose: unidentified_separator)
Indicate (Needed for field with purpose: request_type_option_2)
/ (Needed for field with purpose: secondary_date_separator_1)
/ (Needed for field with purpose: secondary_date_separator_2)
/ (Needed for field with purpose: secondary_date_separator_3)
or (Needed for field with purpose: patient_height_unit_separator)
cms (Needed for field with purpose: patient_height_unit_cms)
Yes (Needed for field with purpose: clinical_question_has_other_coverage_yes)
No (Needed for field with purpose: clinical_question_has_other_coverage_no)
Does patient have other coverage? (Needed for field with purpose: question_has_other_coverage)
Carrier Name: (Needed for field with purpose: secondary_insurance_carrier_name)
If yes, provide ID#: (Needed for field with purpose: secondary_insurance_member_id)
Yes (Needed for field with purpose: clinical_question_has_medicaid_yes)
No (Needed for field with purpose: clinical_question_has_medicaid_no)
Medicaid: (Needed for field with purpose: question_has_medicaid)
Yes (Needed for field with purpose: insurance_info_unspecified_question_yes)
No (Needed for field with purpose: insurance_info_unspecified_question_no)
Office Contact Name: (Needed for field with purpose: prescriber_office_contact_name)
D.O. (Needed for field with purpose: prescriber_credential_do_checkbox)
N.P. (Needed for field with purpose: prescriber_credential_np_checkbox)
P.A. (Needed for field with purpose: prescriber_credential_pa_checkbox)
DEA #: (Needed for field with purpose: prescriber_dea_number)
UPIN: (Needed for field with purpose: prescriber_upin)
Other (Needed for field with purpose: prescriber_credential_other)
Self-administered (Needed for field with purpose: drug_administration_location_self_administered)
Physician's Office (Needed for field with purpose: drug_administration_location_physicians_office)
Dispensing Pharmacy Name: (Needed for field with purpose: dispensing_pharmacy_name)
All Records (Needed for field with purpose: release_of_information_all_records)
Labs (Needed for field with purpose: release_of_information_labs)
Office Visits (Needed for field with purpose: release_of_information_office_visits)
Physician Office (Needed for field with purpose: place_of_service_physician_office_label)
Servicing Facility Name: (Needed for field with purpose: servicing_facility_name)
Home Infusion (Needed for field with purpose: place_of_service_home_infusion)
Home Infusion Agency Name: (Needed for field with purpose: home_infusion_agency_name)
Home Infusion Agency Address: (Needed for field with purpose: home_infusion_agency_address)
Administration CPT Codes (Needed for field with purpose: administration_cpt_codes_checkbox)
Servicing Facility Address: (Needed for field with purpose: servicing_facility_address)
Servicing Facility Phone Number: (Needed for field with purpose: servicing_facility_phone_number)
Retail (Needed for field with purpose: pharmacy_type_retail)
Other (Needed for field with purpose: pharmacy_type_other)
Specialty (Needed for field with purpose: pharmacy_type_specialty)
Other (Needed for field with purpose: place_of_service_other)
Pharmacy Name: (Needed for field with purpose: pharmacy_name)
Pharmacy Address: (Needed for field with purpose: pharmacy_address)
Pharmacy Fax Number: (Needed for field with purpose: pharmacy_fax_number)
Pharmacy TIN: (Needed for field with purpose: pharmacy_tin)
Pharmacy PIN: (Needed for field with purpose: pharmacy_pin)
Secondary Diagnosis ICD Code: (Needed for field with purpose: secondary_diagnosis_icd_code)
Tertiary Diagnosis ICD Code: (Needed for field with purpose: tertiary_diagnosis_icd_code)
No (Needed for field with purpose: clinical_question_1_no)
Yes (Needed for field with purpose: clinical_question_1_yes)
No (Needed for field with purpose: clinical_question_2_no)
Yes (Needed for field with purpose: clinical_question_2_yes)
No (Needed for field with purpose: clinical_question_3_no)
Yes (Needed for field with purpose: clinical_question_3_yes)
No (Needed for field with purpose: clinical_question_tb_tested_no)
weeks (Needed for field with purpose: duration_unit_weeks_1)
weeks (Needed for field with purpose: duration_unit_weeks_2)
weeks (Needed for field with purpose: duration_unit_weeks_3)
Latent and treated (Needed for field with purpose: clinical_question_tb_status_latent_and_treated)
Latent and untreated (Needed for field with purpose: clinical_question_tb_status_latent_and_untreated)
Latent and treated (Needed for field with purpose: clinical_question_tb_status_latent_and_treated_duplicate)
Active (Needed for field with purpose: clinical_question_tb_status_active)
Yes (Needed for field with purpose: clinical_question_4_yes)
No (Needed for field with purpose: clinical_question_4_no)
Yes (Needed for field with purpose: clinical_question_5_yes)
No (Needed for field with purpose: clinical_question_5_no)
Yes (Needed for field with purpose: clinical_question_6_yes)
No (Needed for field with purpose: clinical_question_6_no)
Yes (Needed for field with purpose: clinical_question_7_yes)
No (Needed for field with purpose: clinical_question_7_no)
weeks (Needed for field with purpose: duration_unit_weeks_4)
weeks (Needed for field with purpose: duration_unit_weeks_5)
weeks (Needed for field with purpose: duration_unit_weeks_6)
Yes (Needed for field with purpose: clinical_question_8_yes)
No (Needed for field with purpose: clinical_question_8_no)
Summary
Total Form Fields: 118
Successfully Extracted: 48 fields
Missing Information: 70 fields
Fill Rate: 40.7%
Note: Many missing fields are form separators, conditional checkboxes, or clinical questions that may not apply to this specific case.
