## Automated Prior Authorization Filling System

This repository contains an advanced AI pipeline designed to automate the filling of both interactive (widget-based) and flat (non-interactive) Prior Authorization (PA) forms. The system uses a sophisticated multi-agent architecture to analyze, extract, and populate forms, significantly reducing the manual administrative burden on healthcare providers.

## 1. My Thought Process & Architectural Decisions

The primary challenge of this project was the need to handle two fundamentally different types of PDFs. A single system cannot reliably process both widget-based and flat forms. My solution was to develop two distinct, specialized pipelines, each orchestrated by its own script.

### Multi-Agent  Architecture 1: The Interactive Pipeline (`MANDOLIN_PA_SYSTEM.py`)

This system is designed for modern, widget-based PDFs that have pre-defined, interactive fields (text boxes, checkboxes, etc.).

-   **Form Understanding:** The pipeline begins by using a vision-capable AI (`gemini-2.0-flash`) to analyze the form's visual layout and structure, creating an initial schema of all available fields.
-   **Semantic Refinement:** A more powerful AI (`gemini-2.5-pro`) then refines this schema, assigning a precise, machine-readable `semantic_purpose` to each field (e.g., mapping the visual label "Patient First Name" to the key `patient_first_name`). This standardization is key to making the system adaptable to new forms.
-   **Parallel Extraction:** The system then uses two agents in parallel:
    -   A `DataExtractionAgent` reads the patient's referral documents to find demographic and other standard information.
    -   A specialized `ClinicalQAAgent` focuses solely on answering the complex "Yes/No" clinical questions on the form.
-   **Validation & Correction:** In a critical "fill-and-verify" loop, the system performs a first-pass fill of the form and then hands it off to a `ValidationAgent`. This powerful AI (`gemini-2.5-pro`) visually inspects the filled document, compares it against the source data, and generates a list of corrections for any hallucinations, formatting errors, or misplaced data. This self-correction loop dramatically increases the final accuracy.
-   **Finalization:** The corrections are applied, and a final, flattened PDF is generated alongside a report detailing any information that could not be found.

###  Multi-Agent Architecture 2: The "Text-Anchor" Pipeline for Flat PDFs (`FLAT_PA_SYSTEM.py`)

Flat PDFs are much more challenging as they have no structured fields. Attempting to use AI to visually "guess" the coordinates of where to write text is notoriously unreliable and prone to alignment errors.

To solve this, I developed the **Text-Anchor** system, a more deterministic and robust approach:

-   ** (`TextAnchorAgent`):** This is a code-based agent that uses the `PyMuPDF` library to get the *exact* pixel coordinates of every text label on the form. This creates a perfect, unchangeable "ground truth" map of the document, completely avoiding AI guesswork for layout.
-   ** (`SemanticMapperAgent`):**  (`gemini-2.5-pro`) is used for what it does best: language understanding. It takes the list of text labels and assigns a `semantic_purpose` to each one. This result is cached to avoid re-processing the same form type.
-   ** (`TextAnchorFillingAgent`):** This non-AI agent is the core of the system's reliability. It operates on simple, predictable logic:
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


### Missing report report for Akshey ->  https://github.com/alhridoy/headstarter-mandolin-project/blob/automation-pa-filling-alhridoy/Output%20Data/Akshay_processing_report.md
[📄 View Akshay_PA_filled_v1.pdf](https://github.com/alhridoy/headstarter-mandolin-project/blob/automation-pa-filling-alhridoy/Output%20Data/Akshay_PA_filled_v1.pdf)


### Missing report report for Abdullah -> https://github.com/alhridoy/headstarter-mandolin-project/blob/automation-pa-filling-alhridoy/Output%20Data/Adbulla_processing_report.md
[📄 View Adbulla_PA_filled_v1.pdf](https://github.com/alhridoy/headstarter-mandolin-project/blob/automation-pa-filling-alhridoy/output_examples/Adbulla_PA_20250618_220041.pdf)

### Missing report report for Amy -> https://github.com/alhridoy/headstarter-mandolin-project/blob/automation-pa-filling-alhridoy/output_examples/Amy_Chen_processing_report.md
[📄 View Amy_Chen_PA_20250618_154533.pdf](https://github.com/alhridoy/headstarter-mandolin-project/blob/automation-pa-filling-alhridoy/pa_forms/completed/Amy_Chen_PA_20250618_154533.pdf)

