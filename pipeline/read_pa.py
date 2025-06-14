import pdfplumber
import os

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
file_path = os.path.join(base_dir, "Input Data", "Adbulla", "PA.pdf")

with pdfplumber.open(file_path) as pdf:
    first_page = pdf.pages[0]
    print(first_page.chars[0])
    
