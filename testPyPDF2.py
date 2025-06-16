from PyPDF2 import PdfReader

# Load the form
reader = PdfReader("PA.pdf")

# Extract the form fields
fields = reader.get_fields()

# Print the field names
if fields:
    print("Here are the field identifiers in your PA form:")
    for field_name in fields.keys():
        print(f"- {field_name}")
else:
    print("No fillable form fields were found.")
