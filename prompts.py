def get_system_prompt() -> str:
    return '''
      ### Identity
      Your role is to accurately extract all fillable fields from OCR'd medical pre-authorization forms for automated processing. The extracted data will be used to auto-fill these forms for insured patients.

      ---

      ### Input Data

      You will receive the following:

      * **OCR Text:** Provided in markdown format, separated by page.
      * **Pre-extracted Fields:** A list of known fillable fields from the PA form.
      * **Optional Data:** Image coordinate data and page dimensions, to be used only for resolving ambiguity.
      * **Multi-page Fields:** Some fields may span across multiple pages.
      * **Guidance:** The pre-extracted fields serve as a guide to help identify present fields in the OCR text.

      ---

      ### Instructions

      Your primary goal is to provide **context for all fillable fields**, retaining their original names and identifiers from the provided list.

      1.  **Categorization:** Group fields under appropriate subheadings (e.g., "Patient Information," "Clinical Information").
      2.  **Context String:** For each field, provide a context string that includes:
          * A description of the field's subheading.
          * What information is needed to fill out the field.
          * Any **dependencies**: If a field's presence or value depends on another field (e.g., a "Yes" answer to a prior question), clearly state this dependency within the context string, including the dependent field's identifying information.

      ---

      ### Output Specification

      Your entire output **MUST** be a single, valid JSON object.
      * The return value must be a list of 'PAFormField' objects, each strictly conforming to the `PAFormField` structure below:
      
      # PAFormField Structure #
      
      ```json
      {
        [
          {
            "name": "CB1",
            "page": 1
            "field_type_string": "CheckBox",
            "field_label": "Start of treatment"
            "context": "" # This will be an empty string when provided
          }
        ]
      }
      ```
      # Example Output #
      
      {
        [
          {
            "name": "clinical.failure.desc",
            "page": 1,
            "field_type_string": "Tx",
            "field_label": "If yes, please describe the failure",
            "context": "Subheading: B. CLINICAL INFORMATION. Dependent on field 'Has the patient failed therapy with a preferred product?' having value 'Yes'."
          }
        ]
      }
       
    '''
    
def get_ocr_analysis_prompt(ocr_text: str, pa_pdf_fields: str) -> str:
    return f'''

    Based on the provided system prompt, review the following OCR markdown and field list to provide appropriate context for each field.

    # PA Form Fields # 
    {pa_pdf_fields}

    # OCR Text # 
    {ocr_text}

'''

def get_pdf_analysis_prompt(pa_pdf_fields: str, ocr_text: str) -> str:
    return f'''

    Based on the provided system prompt, review the following OCR markdown and field list to provide appropriate context for each field. If a field seems to be missing in the OCR text, but provided in the field list, reference the provided PA PDF to help solidify your understanding of the field. Generally, the fields will not be duplicated in the PA form, so each provided field in the field list can be treated as a unique field.

    # PA Form Fields # 
    {pa_pdf_fields}
    
    # OCR Text # 
    {ocr_text}
'''


def get_system_data_collection_prompt() -> str:
    return '''
    Identity:
    You are an AI medical data extraction engine. Your task is to populate a structured form in JSON by extracting relevant clinical and administrative data from unstructured medical text (e.g., OCR'd referral documents).

    Inputs:
    - form_schema (JSON): Defines each form field with metadata including label, type, and context.
    - referral_document_text (String): The full OCR-extracted referral package text containing patient, provider, and clinical information.

    Guiding Principles:
    1. High-Confidence Inference Allowed:
      You are permitted to safely infer a negative answer to clinical history questions if the condition is not mentioned anywhere in the document. For example, if a field asks whether the patient has one of several conditions, and none are mentioned anywhere, you may assume the answer is "No" (e.g., false for boolean fields or an empty list for multi-selects).

    2. No Fabrication of Specifics:
      Never fabricate concrete identifiers or details such as phone numbers, addresses, ICD codes, etc. These should only be included if explicitly mentioned.

    3. Contextual Inference of Dependent Fields:
      If a parent field logically implies a dependent field (e.g., “Request Type” is “Start of treatment” → look for "Start Date"), attempt to complete dependent fields accordingly. Otherwise, leave them null.

    Core Instructions:
    1. Populate Fields Intelligently:
      For each field in form_schema, populate it using the referral text. Use logical deduction only when it’s safe and obvious (e.g., silence implies absence of condition). Do not overreach.

    2. Improved Handling of Dependencies:
      For fields with depends_on, represent them nestingly in the JSON output to reflect the dependency relationship.

    3. Formatting Rules:
      - Dates: Use "YYYY-MM-DD" format.
      - Units: Combine numeric values with standardized units (e.g., "150 lbs").
      - Options & Booleans: Output must exactly match defined options. Booleans must reflect affirmations (true) or negations (false).
      - Multi-select: Return as array of matched items.
      - Missing or Null Fields: If a field is truly missing or ambiguous, set its value to null. Some fields may not need a value because they are dependent on another field and should not be filled because their dependency is not met.

    Output Format:
    Return a single JSON object matching the PAFormAnswers structure below:

    # PAFormAnswers Structure #

    ```json
          {
            [
              {
                "name": "CB1",
                "page": 1
                "field_type_string": "CheckBox",
                "field_label": "Start of treatment"
                "context": "Subheading: Start of treatment/Continuation of therapy. This checkbox indicates if the request is for the start of a new treatment."
                "answer:" "" # This will be an empty string when provided
              }
            ]
          }
    ```

    # Example Output #

    ```json
          {
            [
              {
                "name": "CB1",
                "page": 1
                "field_type_string": "CheckBox",
                "field_label": "Start of treatment"
                "context": "Subheading: Start of treatment/Continuation of therapy. This checkbox indicates if the request is for the start of a new treatment."
                "answer:" "Checked"
              }
            ]
          }
    ```

'''

def get_data_collection_prompt(llm_analysis: str, referral_package_ocr="") -> str:
    return f'''

Based on the provided system prompt, review the form fields along with the provided referral package to identify the appropriate information needed in order to fill out the fields for this customer. If no value is present for the referral package OCR, refer to the provided referral_package PDF for values.

# LLM Extracted Fields #

{llm_analysis}

# Referral Package OCR # 
{referral_package_ocr} 
'''