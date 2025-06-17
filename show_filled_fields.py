#!/usr/bin/env python3
"""
Show detailed view of filled PA form fields
"""

import fitz
from pathlib import Path

def show_filled_fields():
    # Compare original vs filled
    original_path = Path('Input Data/Akshay/pa.pdf')
    filled_path = Path('output_examples/Akshay_PA_filled.pdf')
    
    print('🔍 PA FORM FIELD COMPARISON')
    print('=' * 60)
    
    # Open both documents
    orig_doc = fitz.open(str(original_path))
    filled_doc = fitz.open(str(filled_path))
    
    # Get original field values
    orig_fields = {}
    for page_num in range(len(orig_doc)):
        page = orig_doc[page_num]
        for widget in page.widgets():
            if widget.field_name:
                orig_fields[widget.field_name] = widget.field_value or ""
    
    # Get filled field values  
    filled_fields = {}
    for page_num in range(len(filled_doc)):
        page = filled_doc[page_num]
        for widget in page.widgets():
            if widget.field_name:
                filled_fields[widget.field_name] = widget.field_value or ""
    
    # Find fields that changed (were filled)
    changed_fields = {}
    for field_name in filled_fields:
        orig_val = str(orig_fields.get(field_name, ""))
        filled_val = str(filled_fields[field_name])
        
        if orig_val != filled_val and filled_val.strip():
            changed_fields[field_name] = {
                'original': orig_val,
                'filled': filled_val
            }
    
    print(f'📊 SUMMARY:')
    print(f'  Original form fields: {len(orig_fields)}')
    print(f'  Filled form fields: {len(filled_fields)}')
    print(f'  Fields that were populated: {len(changed_fields)}')
    print()
    
    if changed_fields:
        print(f'✅ FIELDS SUCCESSFULLY FILLED ({len(changed_fields)}):')
        print('-' * 60)
        for field_name, values in changed_fields.items():
            print(f'🟢 {field_name}:')
            print(f'   Before: "{values["original"]}"')
            print(f'   After:  "{values["filled"]}"')
            print()
    else:
        print('❌ No fields were successfully filled.')
    
    # Show extracted data that should have been used
    print('📋 DATA THAT WAS EXTRACTED BUT NOT MAPPED:')
    print('-' * 60)
    
    # Import our system to show extracted data
    try:
        from PRODUCTION_PA_SYSTEM import ProductionPASystem
        system = ProductionPASystem()
        referral_path = Path('Input Data/Akshay/referral_package.pdf')
        extracted = system.extract_from_referral_documents(referral_path)
        
        key_data = [
            'patient_first_name', 'patient_last_name', 'patient_dob',
            'prescriber_first_name', 'prescriber_last_name', 'prescriber_npi',
            'member_id', 'group_number', 'insurance_plan',
            'diagnosis', 'medication_name'
        ]
        
        for key in key_data:
            if key in extracted:
                print(f'  📝 {key}: {extracted[key]}')
        
        print(f'\nTotal extracted fields: {len(extracted)}')
    except Exception as e:
        print(f'Could not load extraction data: {e}')
    
    orig_doc.close()
    filled_doc.close()

if __name__ == "__main__":
    show_filled_fields()