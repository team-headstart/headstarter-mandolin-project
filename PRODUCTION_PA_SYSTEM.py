#!/usr/bin/env python3
"""
PRODUCTION PA AUTOMATION SYSTEM
Fully automated PA form processing with comprehensive reporting and conditional field handling
"""

import json
import fitz
import base64
from pathlib import Path
import google.generativeai as genai
from dotenv import load_dotenv
import os
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

load_dotenv()
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))

@dataclass
class FormField:
    """Represents a form field with its metadata"""
    field_id: str
    purpose: str
    is_required: bool
    field_type: str
    context: str
    dependencies: List[str] = None
    mutually_exclusive_with: List[str] = None

@dataclass
class ProcessingResult:
    """Complete processing result for a patient"""
    patient_name: str
    filled_pdf_path: str
    missing_info_report_path: str
    total_fields: int
    filled_fields: int
    required_fields_missing: int
    success_rate: float
    processing_time: str

class ProductionPASystem:
    """Production PA automation system with comprehensive field analysis and reporting"""
    
    def __init__(self):
        self.model = genai.GenerativeModel('gemini-2.0-flash')
    
    def extract_from_referral_documents(self, referral_path: Path) -> Dict[str, str]:
        """Automatically extract data from referral documents using advanced OCR"""
        
        print(f"📊 Extracting from: {referral_path.name}")
        
        doc = fitz.open(str(referral_path))
        all_extracted_data = {}
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            
            # Convert page to high-resolution image for better OCR
            mat = fitz.Matrix(3.0, 3.0)  # Higher resolution for better OCR
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            img_b64 = base64.b64encode(img_data).decode()
            
            # Extract from page
            page_data = self._extract_from_page(img_b64, page_num + 1)
            
            # Merge data (prefer non-empty values)
            for field, value in page_data.items():
                if value and value.strip():
                    all_extracted_data[field] = value
        
        doc.close()
        
        print(f"📈 Extracted {len(all_extracted_data)} data fields")
        return all_extracted_data
    
    def _extract_from_page(self, img_b64: str, page_num: int) -> Dict[str, str]:
        """Extract data from a single page with comprehensive field coverage"""
        
        prompt = f"""
        Extract ALL visible medical information from this referral document page {page_num}.
        
        EXTRACTION RULES:
        1. Extract ONLY information clearly visible in the document
        2. Preserve exact formatting and capitalization as shown
        3. For names: Extract exactly as written, do not modify or "correct"
        4. For dates: Use exact format shown (MM/DD/YYYY preferred)
        5. For phone numbers: Include exact formatting
        6. Do not make assumptions or infer missing information
        7. Look for handwritten text, stamps, and form fields
        
        COMPREHENSIVE FIELDS TO EXTRACT:
        
        PATIENT INFORMATION:
        - patient_first_name: First name exactly as written
        - patient_last_name: Last name exactly as written
        - patient_middle_name: Middle name or initial
        - patient_dob: Date of birth in any format shown
        - patient_age: Age if mentioned
        - patient_address: Complete street address
        - patient_city: City name
        - patient_state: State (abbreviation or full name)
        - patient_zip: ZIP code
        - patient_phone: Primary phone number
        - patient_cell_phone: Cell/mobile phone
        - patient_email: Email address
        - patient_weight: Weight with units
        - patient_height: Height 
        - patient_gender: Male/Female/Other
        - patient_ssn: Social Security Number (if visible)
        
        INSURANCE INFORMATION:
        - member_id: Insurance member/subscriber ID
        - group_number: Insurance group number
        - insurance_plan: Insurance plan name
        - insurance_company: Insurance company name
        - policy_number: Policy number
        - subscriber_name: Name on insurance policy
        - subscriber_dob: Subscriber date of birth
        - insurance_phone: Insurance contact phone
        - copay_amount: Copay amount
        - deductible: Deductible information
        
        PROVIDER INFORMATION:
        - prescriber_first_name: Doctor's first name
        - prescriber_last_name: Doctor's last name
        - prescriber_title: MD, DO, NP, PA, etc.
        - prescriber_npi: 10-digit NPI number
        - prescriber_phone: Provider phone
        - prescriber_fax: Provider fax
        - prescriber_address: Provider address
        - prescriber_city: Provider city
        - prescriber_state: Provider state
        - prescriber_zip: Provider ZIP
        - prescriber_specialty: Medical specialty
        - clinic_name: Clinic or practice name
        - clinic_phone: Clinic phone number
        
        CLINICAL INFORMATION:
        - diagnosis: Primary diagnosis
        - secondary_diagnosis: Additional diagnoses
        - icd_code: ICD-10 diagnosis codes
        - medication_name: Prescribed medication
        - medication_dose: Dosage information
        - medication_frequency: How often taken
        - medication_strength: Strength/concentration
        - allergies: Known allergies
        - current_medications: List of current medications
        - previous_treatments: Previous treatment attempts
        - treatment_failures: Failed treatments and reasons
        - lab_results: Laboratory test results
        - vital_signs: Blood pressure, heart rate, etc.
        - medical_history: Relevant medical history
        
        TREATMENT HISTORY:
        - has_tried_otc: Has tried over-the-counter medications
        - has_tried_generic: Has tried generic alternatives
        - contraindications: Contraindications to treatment
        - treatment_start_date: When treatment should start
        - urgency: Urgency of treatment (stat, urgent, routine)
        
        Return JSON with ALL clearly visible fields:
        {{
            "patient_first_name": "exact name",
            "patient_last_name": "exact name",
            "patient_dob": "MM/DD/YYYY",
            "diagnosis": "exact diagnosis text",
            "medication_name": "exact medication"
        }}
        
        IMPORTANT: Only include fields where information is clearly visible.
        For handwritten text, do your best to interpret if clearly readable.
        """
        
        try:
            response = self.model.generate_content([
                prompt,
                {"mime_type": "image/png", "data": img_b64}
            ])
            
            response_text = response.text.strip()
            if response_text.startswith('```json'):
                response_text = response_text[7:-3].strip()
            elif response_text.startswith('```'):
                response_text = response_text[3:-3].strip()
            
            # Clean up JSON issues
            response_text = self._clean_json_response(response_text)
            
            extracted = json.loads(response_text)
            
            # Clean extracted data
            clean_data = {}
            for field, value in extracted.items():
                if value and str(value).strip():
                    clean_value = str(value).strip()
                    if len(clean_value) > 0 and clean_value.lower() not in ['n/a', 'none', 'not available', 'unknown', 'not provided']:
                        clean_data[field] = clean_value
            
            print(f"  Page {page_num}: {len(clean_data)} fields extracted")
            return clean_data
            
        except Exception as e:
            print(f"  ❌ Page {page_num} extraction failed: {e}")
            return {}
    
    def _clean_json_response(self, response_text: str) -> str:
        """Clean up common JSON formatting issues from AI responses"""
        
        # Remove trailing commas before closing braces/brackets
        import re
        response_text = re.sub(r',(\s*[}\]])', r'\1', response_text)
        
        # Fix unterminated strings by finding and closing them
        lines = response_text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            # If line has unterminated string, try to fix it
            if line.count('"') % 2 == 1 and ':' in line:
                # Add closing quote at end if missing
                if not line.rstrip().endswith('"') and not line.rstrip().endswith('",'):
                    line = line.rstrip() + '"'
            cleaned_lines.append(line)
        
        response_text = '\n'.join(cleaned_lines)
        
        # Ensure proper JSON structure
        if not response_text.strip().startswith('{'):
            response_text = '{' + response_text
        if not response_text.strip().endswith('}'):
            response_text = response_text + '}'
            
        return response_text
    
    def analyze_pa_form_structure(self, pa_path: Path) -> Dict[str, FormField]:
        """Comprehensive PA form analysis with conditional logic detection"""
        
        print(f"🔍 Analyzing PA form: {pa_path.name}")
        
        doc = fitz.open(str(pa_path))
        form_fields = {}
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            
            # Get form widgets with extended context
            widgets = []
            page_text = page.get_text()
            
            for widget in page.widgets():
                if widget.field_name:
                    rect = widget.rect
                    # Get extended context around field
                    context_rect = rect + (-100, -50, 100, 50)
                    context = page.get_text("text", clip=context_rect).strip()
                    
                    widgets.append({
                        'field_name': widget.field_name,
                        'field_type': widget.field_type,
                        'context': context,
                        'rect': [rect.x0, rect.y0, rect.x1, rect.y1]
                    })
            
            if widgets:
                # Convert page to image for AI analysis
                mat = fitz.Matrix(2.0, 2.0)
                pix = page.get_pixmap(matrix=mat)
                img_data = pix.tobytes("png")
                img_b64 = base64.b64encode(img_data).decode()
                
                # Analyze with AI
                page_fields = self._analyze_page_fields_comprehensive(img_b64, widgets, page_text, page_num + 1)
                form_fields.update(page_fields)
        
        doc.close()
        
        print(f"📋 Detected {len(form_fields)} form fields")
        return form_fields
    
    def _analyze_page_fields_comprehensive(self, img_b64: str, widgets: list, page_text: str, page_num: int) -> Dict[str, FormField]:
        """Comprehensive field analysis with conditional logic detection"""
        
        field_list = []
        for w in widgets:
            field_list.append(f"ID: {w['field_name']} | Type: {w['field_type']} | Context: {w['context'][:150]}")
        
        prompt = f"""
        Analyze this PA form page {page_num} to comprehensively understand ALL form fields.
        
        Form fields detected:
        {chr(10).join(field_list)}
        
        Page text context:
        {page_text[:2000]}
        
        ANALYSIS REQUIREMENTS:
        1. Identify field purpose using standard medical form categories
        2. Determine if field is REQUIRED or OPTIONAL (look for asterisks *, "required", etc.)
        3. Identify conditional dependencies (if this field is filled, then...)
        4. Identify mutually exclusive fields (either/or choices)
        5. Look for section headers and groupings
        
        STANDARD FIELD PURPOSES:
        - Patient Demographics: patient_first_name, patient_last_name, patient_dob, patient_address, patient_city, patient_state, patient_zip, patient_phone, patient_gender, patient_weight, patient_height
        - Insurance: member_id, group_number, insurance_plan, subscriber_name, insurance_company, policy_number
        - Provider: prescriber_first_name, prescriber_last_name, prescriber_npi, prescriber_phone, prescriber_fax, prescriber_address, clinic_name
        - Clinical: diagnosis, medication_name, icd_code, dosage, strength, allergies, medical_history
        - Treatment: has_tried_otc, previous_treatments, treatment_failures, contraindications
        - Administrative: date_of_request, urgency, prior_auth_number
        
        Return JSON with comprehensive field analysis:
        {{
            "field_id": {{
                "purpose": "detected_purpose",
                "is_required": true/false,
                "field_type": "text/checkbox/dropdown",
                "context": "surrounding text and labels",
                "dependencies": ["field_id1", "field_id2"] (if conditional),
                "mutually_exclusive_with": ["field_id3"] (if either/or choice)
            }}
        }}
        
        IMPORTANT: 
        - Mark fields as required if you see asterisks (*), "required", "must", etc.
        - Identify checkbox groups that are mutually exclusive
        - Note conditional fields (if X then Y becomes relevant)
        """
        
        try:
            response = self.model.generate_content([
                prompt,
                {"mime_type": "image/png", "data": img_b64}
            ])
            
            response_text = response.text.strip()
            if response_text.startswith('```json'):
                response_text = response_text[7:-3].strip()
            elif response_text.startswith('```'):
                response_text = response_text[3:-3].strip()
            
            # Clean up common JSON issues
            response_text = self._clean_json_response(response_text)
            
            field_analysis = json.loads(response_text)
            
            # Convert to FormField objects
            form_fields = {}
            for field_id, analysis in field_analysis.items():
                form_field = FormField(
                    field_id=field_id,
                    purpose=analysis.get('purpose', 'unknown'),
                    is_required=analysis.get('is_required', False),
                    field_type=analysis.get('field_type', 'text'),
                    context=analysis.get('context', ''),
                    dependencies=analysis.get('dependencies', []),
                    mutually_exclusive_with=analysis.get('mutually_exclusive_with', [])
                )
                form_fields[field_id] = form_field
            
            print(f"  Page {page_num}: {len(form_fields)} fields analyzed comprehensively")
            return form_fields
            
        except Exception as e:
            print(f"  ❌ Page {page_num} comprehensive analysis failed: {e}")
            # Fallback to basic field detection
            return self._fallback_field_analysis(widgets, page_num)
    
    def _fallback_field_analysis(self, widgets: list, page_num: int) -> Dict[str, FormField]:
        """Basic fallback field analysis when AI analysis fails"""
        
        form_fields = {}
        
        for widget in widgets:
            field_id = widget['field_name']
            context = widget['context']
            field_type = widget['field_type']
            
            # Basic purpose detection from context
            purpose = 'unknown'
            is_required = False
            
            context_lower = context.lower()
            
            # Detect common field purposes
            if any(term in context_lower for term in ['first name', 'fname']):
                purpose = 'patient_first_name'
            elif any(term in context_lower for term in ['last name', 'lname', 'surname']):
                purpose = 'patient_last_name'
            elif any(term in context_lower for term in ['address', 'street']):
                purpose = 'patient_address'
            elif any(term in context_lower for term in ['city']):
                purpose = 'patient_city'
            elif any(term in context_lower for term in ['state']):
                purpose = 'patient_state'
            elif any(term in context_lower for term in ['zip', 'postal']):
                purpose = 'patient_zip'
            elif any(term in context_lower for term in ['phone', 'telephone']):
                purpose = 'patient_phone'
            elif any(term in context_lower for term in ['member id', 'subscriber id']):
                purpose = 'member_id'
            elif any(term in context_lower for term in ['group number', 'group id']):
                purpose = 'group_number'
            elif any(term in context_lower for term in ['insurance', 'plan']):
                purpose = 'insurance_plan'
            elif any(term in context_lower for term in ['npi', 'provider id']):
                purpose = 'prescriber_npi'
            elif any(term in context_lower for term in ['diagnosis', 'condition']):
                purpose = 'diagnosis'
            elif any(term in context_lower for term in ['medication', 'drug']):
                purpose = 'medication_name'
            
            # Detect required fields (look for asterisk or "required")
            if '*' in context or 'required' in context_lower:
                is_required = True
            
            form_field = FormField(
                field_id=field_id,
                purpose=purpose,
                is_required=is_required,
                field_type=field_type,
                context=context,
                dependencies=[],
                mutually_exclusive_with=[]
            )
            
            form_fields[field_id] = form_field
        
        print(f"  Page {page_num}: {len(form_fields)} fields analyzed (fallback mode)")
        return form_fields
    
    def create_smart_mapping_with_logic(self, form_fields: Dict[str, FormField], extracted_data: Dict[str, str]) -> Tuple[Dict[str, str], List[str]]:
        """Create intelligent mapping with conditional logic and track missing required fields"""
        
        print(f"🧠 Creating smart mappings with conditional logic")
        print(f"  Form fields detected: {len(form_fields)}")
        print(f"  Data extracted: {len(extracted_data)}")
        
        mappings = {}
        missing_required_fields = []
        filled_field_purposes = set()
        
        # First pass: Fill direct mappings
        for field_id, form_field in form_fields.items():
            purpose = form_field.purpose
            context = form_field.context.lower()
            
            # Smart mapping based on context analysis
            mapped_value = self._smart_context_mapping(field_id, form_field, extracted_data)
            
            if mapped_value:
                mappings[field_id] = mapped_value
                filled_field_purposes.add(purpose)
                print(f"  ✅ {field_id} ← {purpose} = '{mapped_value}'")
            elif form_field.is_required:
                missing_required_fields.append(field_id)
                print(f"  ❌ {field_id} ({purpose}) - REQUIRED field missing")
            else:
                print(f"  ⚠️ {field_id} ({purpose}) - optional field not found")
        
        # Second pass: Apply conditional logic
        mappings = self._apply_conditional_logic(form_fields, mappings, filled_field_purposes)
        
        print(f"📈 Created {len(mappings)} mappings, {len(missing_required_fields)} required fields missing")
        return mappings, missing_required_fields
    
    def _apply_conditional_logic(self, form_fields: Dict[str, FormField], mappings: Dict[str, str], filled_purposes: set) -> Dict[str, str]:
        """Apply conditional logic and handle mutually exclusive fields"""
        
        print("🔄 Applying conditional logic...")
        
        # Handle mutually exclusive fields
        mutually_exclusive_groups = {}
        for field_id, form_field in form_fields.items():
            if form_field.mutually_exclusive_with:
                for exclusive_field in form_field.mutually_exclusive_with:
                    group_key = tuple(sorted([field_id, exclusive_field]))
                    if group_key not in mutually_exclusive_groups:
                        mutually_exclusive_groups[group_key] = []
                    mutually_exclusive_groups[group_key].append(field_id)
        
        # For each mutually exclusive group, keep only the first filled field
        for group_fields in mutually_exclusive_groups.values():
            filled_in_group = [f for f in group_fields if f in mappings]
            if len(filled_in_group) > 1:
                # Keep first one, remove others
                for field_to_remove in filled_in_group[1:]:
                    del mappings[field_to_remove]
                    print(f"  🚫 Removed {field_to_remove} due to mutual exclusivity")
        
        # Handle conditional dependencies
        # If a field has dependencies, only include it if dependencies are satisfied
        fields_to_remove = []
        for field_id, form_field in form_fields.items():
            if field_id in mappings and form_field.dependencies:
                dependency_satisfied = False
                for dep_field_id in form_field.dependencies:
                    if dep_field_id in mappings:
                        dependency_satisfied = True
                        break
                
                if not dependency_satisfied:
                    fields_to_remove.append(field_id)
                    print(f"  🚫 Removing {field_id} - conditional dependency not satisfied")
        
        for field_id in fields_to_remove:
            del mappings[field_id]
        
        return mappings
    
    def _smart_context_mapping(self, field_id: str, form_field: FormField, extracted_data: Dict[str, str]) -> Optional[str]:
        """Smart mapping using context analysis and field relationships"""
        
        context = form_field.context.lower()
        purpose = form_field.purpose.lower()
        
        # Define context-based mapping rules
        mapping_rules = [
            # Patient Demographics
            (['first name', 'patient first', 'fname'], 'patient_first_name'),
            (['last name', 'patient last', 'lname', 'surname'], 'patient_last_name'),
            (['middle name', 'middle initial', 'mname'], 'patient_middle_name'),
            (['date of birth', 'dob', 'birth date'], 'patient_dob'),
            (['address', 'street address', 'patient address'], 'patient_address'),
            (['city', 'patient city'], 'patient_city'),
            (['state', 'patient state'], 'patient_state'),
            (['zip', 'postal', 'zip code'], 'patient_zip'),
            (['home phone', 'phone', 'telephone'], 'patient_phone'),
            (['cell phone', 'mobile', 'cellular'], 'patient_cell_phone'),
            (['gender', 'sex'], 'patient_gender'),
            (['weight'], 'patient_weight'),
            (['height'], 'patient_height'),
            (['age'], 'patient_age'),
            
            # Insurance Information
            (['member id', 'member number', 'subscriber id'], 'member_id'),
            (['group number', 'group id'], 'group_number'),
            (['insurance plan', 'plan name'], 'insurance_plan'),
            (['insurance company', 'insurer'], 'insurance_company'),
            (['policy number', 'policy id'], 'policy_number'),
            (['subscriber name', 'insured name'], 'subscriber_name'),
            
            # Provider Information
            (['prescriber first', 'doctor first', 'physician first'], 'prescriber_first_name'),
            (['prescriber last', 'doctor last', 'physician last'], 'prescriber_last_name'),
            (['npi', 'provider id'], 'prescriber_npi'),
            (['prescriber phone', 'doctor phone', 'provider phone'], 'prescriber_phone'),
            (['prescriber fax', 'doctor fax', 'provider fax'], 'prescriber_fax'),
            (['prescriber address', 'doctor address', 'provider address'], 'prescriber_address'),
            (['clinic name', 'practice name'], 'clinic_name'),
            
            # Clinical Information
            (['diagnosis', 'condition'], 'diagnosis'),
            (['medication name', 'drug name', 'product name'], 'medication_name'),
            (['dose', 'dosage'], 'medication_dose'),
            (['strength'], 'medication_strength'),
            (['icd', 'diagnosis code'], 'icd_code'),
            (['allergies', 'allergy'], 'allergies'),
            (['current medications', 'current meds'], 'current_medications'),
        ]
        
        # Check each mapping rule
        for context_keywords, data_field in mapping_rules:
            for keyword in context_keywords:
                if keyword in context:
                    if data_field in extracted_data:
                        return extracted_data[data_field]
        
        # Additional specific mappings based on purpose
        purpose_mappings = {
            'patient_first_name': 'patient_first_name',
            'patient_last_name': 'patient_last_name', 
            'patient_middle_name': 'patient_middle_name',
            'patient_dob': 'patient_dob',
            'patient_address': 'prescriber_address',  # Sometimes patient address not available, use prescriber
            'patient_city': 'prescriber_city',
            'patient_state': 'prescriber_state', 
            'patient_zip': 'prescriber_zip',
            'patient_phone': 'prescriber_phone',
            'patient_weight': 'patient_weight',
            'patient_height': 'patient_height',
            'patient_gender': 'patient_gender',
            'member_id': 'policy_number',  # Member ID often stored as policy number
            'group_number': 'group_number',
            'insurance_plan': 'insurance_plan',
            'insurance_company': 'insurance_company',
            'prescriber_first_name': 'prescriber_first_name',
            'prescriber_last_name': 'prescriber_last_name',
            'prescriber_npi': 'prescriber_npi',
            'prescriber_phone': 'prescriber_phone',
            'prescriber_fax': 'prescriber_fax',
            'prescriber_address': 'prescriber_address',
            'prescriber_city': 'prescriber_city',
            'prescriber_state': 'prescriber_state',
            'prescriber_zip': 'prescriber_zip',
            'diagnosis': 'diagnosis',
            'medication_name': 'medication_name',
            'medication_dose': 'medication_dose',
            'medication_frequency': 'medication_frequency',
            'icd_code': 'icd_code',
            'allergies': 'allergies',
            'current_medications': 'current_medications'
        }
        
        if purpose.lower() in purpose_mappings:
            data_field = purpose_mappings[purpose.lower()]
            if data_field in extracted_data:
                return extracted_data[data_field]
        
        # Fallback to original alternative mapping
        return self._find_alternative_mapping(purpose, extracted_data)
    
    def _find_alternative_mapping(self, purpose: str, extracted_data: Dict[str, str]) -> Optional[str]:
        """Find alternative mappings with expanded coverage"""
        
        # Comprehensive alternative mapping strategies
        alternatives = {
            'patient_name': ['patient_first_name', 'patient_last_name'],
            'patient_first_name': ['patient_first_name'],
            'patient_last_name': ['patient_last_name'],
            'patient_middle_name': ['patient_middle_name'],
            'patient_dob': ['patient_dob'],
            'patient_age': ['patient_age'],
            'patient_phone': ['patient_phone', 'patient_cell_phone'],
            'patient_cell_phone': ['patient_cell_phone', 'patient_phone'],
            'patient_address': ['patient_address'],
            'patient_city': ['patient_city'],
            'patient_state': ['patient_state'],
            'patient_zip': ['patient_zip'],
            'patient_gender': ['patient_gender'],
            'patient_weight': ['patient_weight'],
            'patient_height': ['patient_height'],
            'member_id': ['member_id', 'policy_number'],
            'group_number': ['group_number'],
            'insurance_plan': ['insurance_plan', 'insurance_company'],
            'insurance_company': ['insurance_company', 'insurance_plan'],
            'subscriber_name': ['subscriber_name', 'patient_first_name', 'patient_last_name'],
            'prescriber_first_name': ['prescriber_first_name'],
            'prescriber_last_name': ['prescriber_last_name'],
            'prescriber_npi': ['prescriber_npi'],
            'prescriber_phone': ['prescriber_phone', 'clinic_phone'],
            'prescriber_fax': ['prescriber_fax'],
            'prescriber_address': ['prescriber_address'],
            'clinic_name': ['clinic_name'],
            'diagnosis': ['diagnosis', 'secondary_diagnosis'],
            'medication_name': ['medication_name'],
            'medication_dose': ['medication_dose'],
            'medication_strength': ['medication_strength'],
            'icd_code': ['icd_code'],
            'allergies': ['allergies'],
            'medical_history': ['medical_history'],
            'previous_treatments': ['previous_treatments'],
            'has_tried_otc': ['has_tried_otc']
        }
        
        for alt_key in alternatives.get(purpose, []):
            if alt_key in extracted_data:
                return extracted_data[alt_key]
        
        # Special case: construct full name
        if purpose == 'patient_name':
            first = extracted_data.get('patient_first_name', '')
            middle = extracted_data.get('patient_middle_name', '')
            last = extracted_data.get('patient_last_name', '')
            if first and last:
                full_name = f"{first} {middle} {last}" if middle else f"{first} {last}"
                return full_name.strip()
        
        # Special case: construct prescriber name
        if purpose in ['prescriber_name', 'prescriber_full_name']:
            first = extracted_data.get('prescriber_first_name', '')
            last = extracted_data.get('prescriber_last_name', '')
            title = extracted_data.get('prescriber_title', '')
            if first and last:
                full_name = f"{first} {last}"
                if title:
                    full_name += f", {title}"
                return full_name
        
        return None
    
    def fill_pa_form_with_reporting(self, pa_path: Path, mappings: Dict[str, str], output_path: Path) -> Dict:
        """Fill PA form and generate comprehensive results"""
        
        print(f"📝 Filling PA form with {len(mappings)} mappings")
        
        doc = fitz.open(str(pa_path))
        results = {
            'filled_fields': {},
            'failed_fields': [],
            'total_attempted': len(mappings),
            'field_details': {}
        }
        
        for field_id, value in mappings.items():
            success = False
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                for widget in page.widgets():
                    if widget.field_name == field_id:
                        try:
                            if widget.field_type == 2:  # Checkbox
                                # Handle boolean values for checkboxes
                                checkbox_value = value.lower() in ['yes', 'true', '1', 'male', 'female', 'new', 'existing']
                                widget.field_value = checkbox_value
                                display_value = "☑" if checkbox_value else "☐"
                            else:  # Text field
                                widget.field_value = str(value)
                                display_value = str(value)
                            
                            widget.update()
                            results['filled_fields'][field_id] = value
                            results['field_details'][field_id] = {
                                'value': value,
                                'display_value': display_value,
                                'field_type': widget.field_type
                            }
                            success = True
                            print(f"  ✅ {field_id} = '{display_value}'")
                            break
                        except Exception as e:
                            print(f"  ❌ Failed to fill {field_id}: {e}")
                
                if success:
                    break
            
            if not success:
                results['failed_fields'].append(field_id)
                print(f"  ❌ Could not fill {field_id}")
        
        doc.save(str(output_path))
        doc.close()
        
        results['success_rate'] = len(results['filled_fields']) / results['total_attempted'] if results['total_attempted'] > 0 else 0
        return results
    
    def generate_missing_info_report(self, patient_name: str, form_fields: Dict[str, FormField], 
                                   missing_required_fields: List[str], filled_fields: Dict[str, str],
                                   extracted_data: Dict[str, str], output_dir: Path) -> str:
        """Generate comprehensive missing information report"""
        
        report_path = output_dir / f"{patient_name}_missing_info_report.md"
        
        # Categorize missing fields
        required_missing = []
        optional_missing = []
        all_required_fields = []
        
        for field_id, form_field in form_fields.items():
            if form_field.is_required:
                all_required_fields.append((field_id, form_field))
                if field_id not in filled_fields:
                    required_missing.append((field_id, form_field))
            elif field_id not in filled_fields:
                optional_missing.append((field_id, form_field))
        
        # Generate report content
        report_content = f"""# Missing Information Report - {patient_name}

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Summary
- **Total Form Fields:** {len(form_fields)}
- **Fields Successfully Filled:** {len(filled_fields)}
- **Required Fields:** {len(all_required_fields)}
- **Required Fields Missing:** {len(required_missing)}
- **Optional Fields Missing:** {len(optional_missing)}
- **Success Rate:** {(len(filled_fields) / len(form_fields) * 100) if len(form_fields) > 0 else 0:.1f}%
- **Required Fields Completion:** {((len(all_required_fields) - len(required_missing)) / len(all_required_fields) * 100) if len(all_required_fields) > 0 else 0:.1f}%

## ❌ Required Fields Missing ({len(required_missing)})

**These fields are required for PA submission but could not be filled from the referral package:**

"""
        
        for field_id, form_field in required_missing:
            report_content += f"""### {field_id}
- **Purpose:** {form_field.purpose}
- **Field Type:** {form_field.field_type}
- **Context:** {form_field.context[:200]}...
- **Why Missing:** Information not found in referral package

"""
        
        report_content += f"""## ⚠️ Optional Fields Missing ({len(optional_missing)})

**These optional fields could not be filled:**

"""
        
        for field_id, form_field in optional_missing[:10]:  # Limit to first 10 for readability
            report_content += f"- **{field_id}** ({form_field.purpose}): {form_field.context[:100]}...\n"
        
        if len(optional_missing) > 10:
            report_content += f"- ... and {len(optional_missing) - 10} more optional fields\n"
        
        report_content += f"""
## ✅ Successfully Filled Fields ({len(filled_fields)})

"""
        
        for field_id, value in list(filled_fields.items())[:15]:  # Show first 15
            form_field = form_fields.get(field_id)
            status = "Required" if form_field and form_field.is_required else "Optional"
            report_content += f"- **{field_id}** ({status}): `{value}`\n"
        
        if len(filled_fields) > 15:
            report_content += f"- ... and {len(filled_fields) - 15} more filled fields\n"
        
        report_content += f"""
## 📊 Data Extraction Summary

**Total data points extracted from referral package:** {len(extracted_data)}

**Key extracted information:**
"""
        
        key_fields = ['patient_first_name', 'patient_last_name', 'patient_dob', 'diagnosis', 'medication_name', 'prescriber_first_name', 'prescriber_last_name', 'member_id']
        for key_field in key_fields:
            if key_field in extracted_data:
                report_content += f"- **{key_field}:** {extracted_data[key_field]}\n"
        
        report_content += f"""
## 🔧 Recommendations

To improve completion rate for future submissions:

1. **For Required Fields Missing:** Ensure referral packages include:
"""
        
        missing_purposes = set(form_field.purpose for _, form_field in required_missing)
        for purpose in list(missing_purposes)[:10]:
            report_content += f"   - {purpose.replace('_', ' ').title()}\n"
        
        report_content += """
2. **For Better OCR:** Ensure documents are:
   - High resolution scans
   - Clearly legible text
   - Proper orientation
   - Minimal handwriting (use typed forms when possible)

3. **For Complex Cases:** Consider manual review of:
   - Conditional field requirements
   - Mutually exclusive selections
   - Clinical decision requirements

---
*This report was generated automatically by the PA Automation System*
"""
        
        # Write report to file
        with open(report_path, 'w') as f:
            f.write(report_content)
        
        print(f"📄 Missing info report generated: {report_path}")
        return str(report_path)
    
    def process_patient_comprehensive(self, patient_name: str, output_dir: Path = None) -> ProcessingResult:
        """Process patient with comprehensive analysis and reporting"""
        
        start_time = datetime.now()
        
        print(f"🚀 COMPREHENSIVE PA PROCESSING: {patient_name}")
        print("=" * 60)
        
        if output_dir is None:
            output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)
        
        # Find documents
        patient_mapping = {"Abdullah": "Adbulla", "Akshay": "Akshay", "Amy": "Amy"}
        pdf_patient = patient_mapping.get(patient_name, patient_name)
        
        patient_dir = Path(f"Input Data/{pdf_patient}")
        pa_files = list(patient_dir.glob("*PA*.pdf")) + list(patient_dir.glob("*pa*.pdf"))
        referral_files = list(patient_dir.glob("*referral*.pdf")) + list(patient_dir.glob("*package*.pdf"))
        
        if not pa_files or not referral_files:
            return ProcessingResult(
                patient_name=patient_name,
                filled_pdf_path="",
                missing_info_report_path="",
                total_fields=0,
                filled_fields=0,
                required_fields_missing=0,
                success_rate=0.0,
                processing_time="0s"
            )
        
        # Step 1: Comprehensive PA form analysis
        print(f"\n🔍 STEP 1: COMPREHENSIVE PA FORM ANALYSIS")
        form_fields = self.analyze_pa_form_structure(pa_files[0])
        
        # Step 2: Advanced data extraction
        print(f"\n📊 STEP 2: ADVANCED DATA EXTRACTION")
        extracted_data = self.extract_from_referral_documents(referral_files[0])
        
        # Step 3: Smart mapping with conditional logic
        print(f"\n🧠 STEP 3: SMART MAPPING WITH CONDITIONAL LOGIC")
        mappings, missing_required_fields = self.create_smart_mapping_with_logic(form_fields, extracted_data)
        
        # Step 4: Fill form with comprehensive tracking
        print(f"\n📝 STEP 4: FORM FILLING WITH TRACKING")
        filled_pdf_path = output_dir / f"{patient_name}_PA_filled.pdf"
        filling_results = self.fill_pa_form_with_reporting(pa_files[0], mappings, filled_pdf_path)
        
        # Step 5: Generate missing information report
        print(f"\n📄 STEP 5: GENERATING MISSING INFORMATION REPORT")
        missing_info_report_path = self.generate_missing_info_report(
            patient_name, form_fields, missing_required_fields, 
            filling_results['filled_fields'], extracted_data, output_dir
        )
        
        # Calculate processing time
        end_time = datetime.now()
        processing_time = str(end_time - start_time).split('.')[0]
        
        # Generate final results
        result = ProcessingResult(
            patient_name=patient_name,
            filled_pdf_path=str(filled_pdf_path),
            missing_info_report_path=missing_info_report_path,
            total_fields=len(form_fields),
            filled_fields=len(filling_results['filled_fields']),
            required_fields_missing=len(missing_required_fields),
            success_rate=filling_results['success_rate'],
            processing_time=processing_time
        )
        
        print(f"\n📊 COMPREHENSIVE PROCESSING RESULTS:")
        print(f"  Form Fields Detected: {result.total_fields}")
        print(f"  Data Extracted: {len(extracted_data)}")
        print(f"  Fields Successfully Filled: {result.filled_fields}")
        print(f"  Required Fields Missing: {result.required_fields_missing}")
        print(f"  Overall Success Rate: {result.success_rate:.1%}")
        print(f"  Processing Time: {result.processing_time}")
        print(f"  Filled PDF: {result.filled_pdf_path}")
        print(f"  Missing Info Report: {result.missing_info_report_path}")
        
        return result

def main():
    """Run comprehensive PA automation system"""
    
    print("🏭 COMPREHENSIVE PA AUTOMATION SYSTEM")
    print("Advanced Extraction, Conditional Logic, and Comprehensive Reporting")
    print("=" * 80)
    
    system = ProductionPASystem()
    output_dir = Path("output_examples")
    output_dir.mkdir(exist_ok=True)
    
    # Process all patients
    patients = ["Akshay", "Abdullah", "Amy"]
    all_results = []
    
    for patient in patients:
        print(f"\n{'='*80}")
        result = system.process_patient_comprehensive(patient, output_dir)
        
        if result.filled_pdf_path:
            all_results.append(result)
            print(f"\n✅ COMPLETED: {patient}")
            print(f"   Fields Filled: {result.filled_fields}/{result.total_fields}")
            print(f"   Required Missing: {result.required_fields_missing}")
            print(f"   Success Rate: {result.success_rate:.1%}")
            print(f"   Processing Time: {result.processing_time}")
        else:
            print(f"❌ FAILED: Documents not found for {patient}")
    
    # Generate overall summary
    if all_results:
        print(f"\n{'='*80}")
        print("📊 OVERALL PROCESSING SUMMARY")
        
        total_fields = sum(r.total_fields for r in all_results)
        total_filled = sum(r.filled_fields for r in all_results)
        total_required_missing = sum(r.required_fields_missing for r in all_results)
        avg_success = sum(r.success_rate for r in all_results) / len(all_results)
        
        print(f"Patients Processed: {len(all_results)}")
        print(f"Total Form Fields: {total_fields}")
        print(f"Total Fields Filled: {total_filled}")
        print(f"Total Required Fields Missing: {total_required_missing}")
        print(f"Average Success Rate: {avg_success:.1%}")
        print(f"Output Directory: {output_dir}")
        
        # List generated files
        print(f"\nGenerated Files:")
        for result in all_results:
            print(f"  📄 {result.filled_pdf_path}")
            print(f"  📋 {result.missing_info_report_path}")

if __name__ == "__main__":
    main()