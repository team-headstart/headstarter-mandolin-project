import pdfplumber

with pdfplumber.open("../Input Data/Abdulla/referral_package.pdf") as pdf:
    first_page = pdf.pages[0]
    print(first_page.chars[0])
    
