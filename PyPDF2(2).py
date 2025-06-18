from PyPDF2 import PdfReader, PdfWriter

# This function takes an input PDF, a dictionary of field values, and saves a filled version
def fill_pdf(input_path, output_path, field_values):
    # Load the existing PDF form
    reader = PdfReader(input_path)

    # Create a writer to write a new PDF with filled values
    writer = PdfWriter()

    # Copy each page from the original form into the writer
    for page in reader.pages:
        writer.add_page(page)

    # Apply the field values to the first page of the PDF
    # (Assumes all fields are on page 0 — this works for most forms)
    writer.update_page_form_field_values(writer.pages[0], field_values)

    # Save the filled PDF to a new file
    with open(output_path, "wb") as f:
        writer.write(f)
field_values = {
    "T6": "T6_TEST",
    "T7": "T7_TEST",
    "T20": "T20_TEST",
    "T35": "T35_TEST",
    "T8": "T8_TEST"
}
fill_pdf("PA.pdf", "test_filled.pdf", field_values)
