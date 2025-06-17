#!/usr/bin/env python3
"""
Verify that the PA form has been filled with actual data
"""

import fitz
from pathlib import Path

def verify_filled_pdf():
    # Open filled PDF
    filled_path = Path('output_examples/Akshay_PA_filled.pdf')
    
    if not filled_path.exists():
        print("❌ Filled PDF not found!")
        return
    
    filled_doc = fitz.open(str(filled_path))
    
    print('📝 AKSHAY PA FORM - VERIFICATION RESULTS:')
    print('=' * 60)
    
    # Count form fields
    total_fields = 0
    populated_fields = {}
    
    for page_num in range(len(filled_doc)):
        page = filled_doc[page_num]
        for widget in page.widgets():
            if widget.field_name:
                total_fields += 1
                field_value = widget.field_value
                
                # Check if field has meaningful content
                if field_value and str(field_value).strip() and str(field_value) != 'Off':
                    populated_fields[widget.field_name] = field_value
    
    print(f'📊 SUMMARY:')
    print(f'  Total form fields detected: {total_fields}')
    print(f'  Fields with data: {len(populated_fields)}')
    print(f'  Success rate: {len(populated_fields)/total_fields*100:.1f}%')
    print()
    
    print(f'✅ POPULATED FIELDS ({len(populated_fields)}):')
    print('-' * 60)
    
    for field, value in populated_fields.items():
        # Format boolean values nicely
        if isinstance(value, bool):
            display_value = "☑ (checked)" if value else "☐ (unchecked)"
        else:
            display_value = str(value)
        
        print(f'  {field}: {display_value}')
    
    filled_doc.close()
    
    # Verify specific key fields that should be filled
    print()
    print('🔍 KEY FIELD VERIFICATION:')
    print('-' * 60)
    
    key_checks = [
        ('Insurance Info T.1', 'Member ID'),
        ('Presc Info T.1', 'Prescriber First Name'), 
        ('Presc Info T.7', 'Prescriber Last Name'),
        ('Product T.1', 'Medication Name'),
        ('Diagnosis T.1', 'Diagnosis'),
    ]
    
    for field_id, description in key_checks:
        if field_id in populated_fields:
            print(f'  ✅ {description}: {populated_fields[field_id]}')
        else:
            print(f'  ❌ {description}: NOT FILLED')

if __name__ == "__main__":
    verify_filled_pdf()