# Mandolin AI: Automated Prior Authorization Filling System

This repository contains an advanced AI pipeline designed to automate the filling of Prior Authorization (PA) forms for specialty drugs, aiming to reduce the manual administrative burden on healthcare providers and accelerate patient access to critical treatments.

## 1. The Problem: The Prior Authorization Bottleneck

Getting approval for life-saving specialty drugs is a complex, manual process that can delay patient care by up to 30 days. Healthcare staff must manually:
1.  Analyze a patient's **Referral Package** (a 30-50 page document with medical history, lab results, etc.).
2.  Find the correct drug- and insurance-specific **PA Form**.
3.  Painstakingly extract key data points from the referral.
4.  Manually transcribe that data onto the PA form.

This workflow is slow and prone to human error, creating a significant bottleneck. This project's goal is to automate this entire process with a high degree of accuracy and reliability.

## 2. The Solution: A Multi-Agent AI Assembly Line

This system solves the problem by breaking it down into a sequence of specialized tasks, each handled by a dedicated AI agent. This "AI Assembly Line" approach ensures each step is simple, reliable, and auditable, leading to a more robust and accurate system than a single monolithic model.

### Architectural Diagram

```mermaid
graph TD;
    A[Start: PA Form & Referral] --> B{FormUnderstandingAgent};
    B -- Raw Schema --> C{SchemaRefinementAgent};
    C -- Refined Schema --> D{DataExtractionAgent};
    A --> D;
    C -- Clinical Questions --> E{ClinicalQAAgent};
    A --> E;
    D -- Extracted Data --> F{FormFillingAgent - Pass 1};
    E -- Clinical Answers --> F;
    A -- Blank PA Form --> F;
    F -- Filled PDF v1 --> G{ValidationAgent};
    D -- Extracted Data --> G;
    C -- Refined Schema --> G;
    G -- Corrections List --> H{FormFillingAgent - Pass 2};
    F -- Filled PDF v1 --> H;
    H -- Final Filled PDF --> I[End: Final PDF & Report];
    G -- Missing Info --> J{ReportGenerator};
    J -- Report --> I;
```

### The Agents

-   **`FormUnderstandingAgent` (The Blueprint Maker):** Uses `gemini-2.0-flash` to visually analyze the blank PA form, identifying every field and its human-readable text label.
-   **`SchemaRefinementAgent` (The Translator):** Uses a powerful LLM (`gemini-1.5-pro-latest`) to translate human labels (e.g., "Patient First Name") into standardized, machine-readable keys (e.g., `patient_first_name`). This is a critical step for generalization.
-   **`DataExtractionAgent` (The Detective):** Uses `gemini-2.5-pro` to read the entire referral package, using the refined schema as a "shopping list" to find the required data.
-   **`ClinicalQAAgent` (The Specialist):** A specialized `gemini-2.5-pro` agent that focuses only on answering the complex "Yes/No" clinical questions on the form.
-   **`FormFillingAgent` (The Scribe):** A non-AI agent that mechanically fills the PDF form fields using `PyMuPDF`.
-   **`ValidationAgent` (The Auditor):** The system's core "fill and verify" loop. This `gemini-2.5-pro` agent visually inspects the first-pass filled form, compares it to the source data, and generates a list of corrections to fix hallucinations or formatting errors.

## 3. Installation

To set up the project locally, follow these steps.

**Prerequisites:**
- Python 3.9+
- An API key for Google's Gemini models.

**Setup:**

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/alhridoy/automate_pa.git
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

## 4. How to Run the Pipeline

Execute the main script from the project's root directory:

```bash
python3 MANDOLIN_PA_SYSTEM.py
```

The script will automatically find the patient data in the `Input Data/` directory, process each patient one by one, and place the results in the `Output Data/` directory.

The output for each patient will include:
-   `{PatientName}_PA_filled.pdf`: The final, filled PDF.
-   `{PatientName}_processing_report.md`: A report detailing any information that could not be found.
-   Intermediate log files (schemas, extracted data) for debugging.

## 5. Assumptions & Limitations

-   **Widget-Based PDFs:** The system is currently designed to work only with interactive, widget-based PDF forms. It cannot fill "flat" PDFs that do not have fillable AcroForm fields. This was a primary requirement, with flat PDF support noted as a potential bonus feature.
-   **API Access & Cost:** The system relies on powerful, and therefore not free, LLMs. Execution will incur costs based on token usage. The system also assumes that the specified models (`gemini-2.0-flash`, `gemini-1.5-pro-latest`, `gemini-2.5-pro`) are available to the provided API key.
-   **Fax Quality:** The accuracy of the OCR-dependent steps (`DataExtractionAgent`, `ClinicalQAAgent`) is highly dependent on the image quality of the scanned documents in the referral package. Extremely poor handwriting or low-quality scans may reduce accuracy.
-   **No Hallucination Guarantee:** While the `ValidationAgent` significantly mitigates the risk of AI hallucinations, it is not a perfect guarantee. It represents a robust best-effort attempt to catch and correct errors. 
## 6. The "Text-Anchor" Pipeline for Flat PDFs

To handle non-interactive, "flat" PDFs, a separate, more deterministic pipeline was developed. The core challenge with flat PDFs is the absence of pre-defined fields, which makes data placement difficult and prone to error. The Text-Anchor system solves this by abandoning AI for coordinate guessing and instead using a highly reliable, code-centric approach.

This pipeline is orchestrated by `FLAT_PA_SYSTEM.py`.

### Architectural Diagram

```mermaid
graph TD;
    subgraph "Phase 1: Schema Creation (Once per Form Type)"
        A[Blank PA Form] --> B(TextAnchorAgent);
        B -- List of all text on form --> C(SemanticMapperAgent);
        C -- Text labels + assigned purposes --> D[Cached Schema (.json)];
    end

    subgraph "Phase 2: Form Filling (Once per Patient)"
        E[Patient Referral] --> F(DataExtractionAgent);
        D -- "Shopping list" of purposes --> F;
        F -- Extracted JSON data --> G{Data Merger};
        D -- Schema with purposes --> G;
        G -- Schema with values to fill --> H(TextAnchorFillingAgent);
        A --> H;
        H -- Perfectly aligned text --> I[Final Filled PDF];
    end
```

### The "Text-Anchor" Agents

-   **`TextAnchorAgent` (The Surveyor):** This is a 100% deterministic agent that uses `PyMuPDF` to extract every single piece of text from the PDF along with its *exact* pixel coordinates. This forms the unchangeable "ground truth" for the entire system.
-   **`SemanticMapperAgent` (The Interpreter):** Uses a powerful language model (`gemini-2.5-pro`) to perform a single, crucial task: it takes the list of text labels from the Surveyor and assigns a standardized purpose to each one (e.g., it maps the text "Last name:" to the purpose `patient_last_name`). This is a pure language task, leveraging the AI's core strength. The results are cached for efficiency.
-   **`DataExtractionAgent` (The Detective):** Given a referral document and the list of required purposes from the mapper, this agent (`gemini-2.0-flash`) extracts the necessary patient data.
-   **`TextAnchorFillingAgent` (The Scribe):** This agent is the core of the system's reliability. It is a non-AI agent that operates with simple logic:
    1.  It receives the list of text anchors, now populated with the data to be filled.
    2.  For each piece of data, it finds the corresponding text label's exact coordinates.
    3.  It programmatically calculates an insertion point a few pixels to the right of the label.
    4.  It writes the text directly onto the PDF at that precise location.

This architecture ensures perfect alignment and high accuracy by using each tool for its strength: `PyMuPDF` for geometric precision and the AI for language understanding. 