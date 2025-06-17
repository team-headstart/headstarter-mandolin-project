#!/usr/bin/env python3
"""Verify the improved filled PDF"""

import fitz
from pathlib import Path

# Open the filled PDF
filled_path = Path('output_improved/Akshay_PA_filled.pdf')
if not filled_path.exists():
    print('❌ Filled PDF not found!')
    exit()

doc = fitz.open(str(filled_path))

print('📝 AKSHAY PA FORM - FILLED FIELDS:')
print('=' * 60)

# Count filled fields
filled_fields = {}
total_fields = 0

for page_num in range(len(doc)):
    page = doc[page_num]
    for widget in page.widgets():
        if widget.field_name:
            total_fields += 1
            field_value = widget.field_value
            if field_value and str(field_value).strip() and str(field_value) != 'Off':
                filled_fields[widget.field_name] = field_value

print(f'Total form fields: {total_fields}')
print(f'Successfully filled: {len(filled_fields)}')
print(f'Success rate: {len(filled_fields)/total_fields*100:.1f}%')
print()

print('✅ FILLED FIELDS:')
print('-' * 60)

# Group by category
insurance_fields = {}
prescriber_fields = {}
product_fields = {}
other_fields = {}

for field_id, value in filled_fields.items():
    field_lower = field_id.lower()
    if 'insurance' in field_lower:
        insurance_fields[field_id] = value
    elif 'presc' in field_lower:
        prescriber_fields[field_id] = value
    elif 'product' in field_lower:
        product_fields[field_id] = value
    else:
        other_fields[field_id] = value

if insurance_fields:
    print('\n🏥 INSURANCE INFORMATION:')
    for field, value in insurance_fields.items():
        print(f'  {field}: {value}')

if prescriber_fields:
    print('\n👨‍⚕️ PRESCRIBER INFORMATION:')
    for field, value in prescriber_fields.items():
        print(f'  {field}: {value}')

if product_fields:
    print('\n💊 MEDICATION INFORMATION:')
    for field, value in product_fields.items():
        print(f'  {field}: {value}')

if other_fields:
    print('\n📋 OTHER FIELDS:')
    for field, value in other_fields.items():
        print(f'  {field}: {value}')

doc.close()

print('\n✅ The filled PDF is ready at: output_improved/Akshay_PA_filled.pdf')