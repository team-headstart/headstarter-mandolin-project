from flask import Flask, request, render_template, send_file, flash, redirect, url_for, jsonify
import os
from werkzeug.utils import secure_filename
from pdf_to_doc import convert_pdf_to_doc
from pdf_form_extractor import PDFFormExtractor, debug_extraction_and_fields
import tempfile
import logging
from datetime import datetime
from dotenv import load_dotenv
import json

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Required for flash messages

# Configure folders
UPLOAD_FOLDER = 'uploads'
CONVERTED_FOLDER = 'converted'
FILLED_FORMS_FOLDER = 'filled_forms'
LOGS_FOLDER = 'logs'
for folder in [UPLOAD_FOLDER, CONVERTED_FOLDER, FILLED_FORMS_FOLDER, LOGS_FOLDER]:
    if not os.path.exists(folder):
        os.makedirs(folder)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['CONVERTED_FOLDER'] = CONVERTED_FOLDER
app.config['FILLED_FORMS_FOLDER'] = FILLED_FORMS_FOLDER
app.config['LOGS_FOLDER'] = LOGS_FOLDER

# Allowed file extensions
ALLOWED_EXTENSIONS = {'pdf'}

def allowed_file(filename):
    """Check if the file has an allowed extension"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_extraction_log(timestamp, extracted_data, source_file, template_file):
    """Save extraction log to a JSON file"""
    log_data = {
        'timestamp': timestamp,
        'source_file': source_file,
        'template_file': template_file,
        'extracted_data': extracted_data
    }
    log_file = os.path.join(app.config['LOGS_FOLDER'], f'extraction_{timestamp}.json')
    with open(log_file, 'w') as f:
        json.dump(log_data, f, indent=2)
    return log_file

@app.route('/', methods=['GET'])
def index():
    """Render the upload form"""
    # Get list of converted files and filled forms
    converted_files = []
    filled_forms = []
    extraction_logs = []
    
    if os.path.exists(app.config['CONVERTED_FOLDER']):
        converted_files = [f for f in os.listdir(app.config['CONVERTED_FOLDER']) 
                         if f.endswith('.docx')]
    
    if os.path.exists(app.config['FILLED_FORMS_FOLDER']):
        filled_forms = [f for f in os.listdir(app.config['FILLED_FORMS_FOLDER']) 
                       if f.endswith('.pdf')]
    
    if os.path.exists(app.config['LOGS_FOLDER']):
        extraction_logs = [f for f in os.listdir(app.config['LOGS_FOLDER']) 
                         if f.endswith('.json')]
        extraction_logs.sort(reverse=True)  # Most recent first
    
    return render_template('index.html', 
                         converted_files=converted_files,
                         filled_forms=filled_forms,
                         extraction_logs=extraction_logs)

@app.route('/download/<filename>')
def download_file(filename):
    """Download a converted file"""
    try:
        # Check if file is in converted, filled forms, or logs folder
        if filename.endswith('.docx'):
            folder = app.config['CONVERTED_FOLDER']
        elif filename.endswith('.json'):
            folder = app.config['LOGS_FOLDER']
        else:
            folder = app.config['FILLED_FORMS_FOLDER']
            
        return send_file(
            os.path.join(folder, filename),
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        flash(f'Error downloading file: {str(e)}')
        return redirect(url_for('index'))

@app.route('/view_log/<filename>')
def view_log(filename):
    """View extraction log"""
    try:
        log_path = os.path.join(app.config['LOGS_FOLDER'], filename)
        with open(log_path, 'r') as f:
            log_data = json.load(f)
        return render_template('log_view.html', log_data=log_data)
    except Exception as e:
        flash(f'Error viewing log: {str(e)}')
        return redirect(url_for('index'))

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload and conversion"""
    try:
        # Check if files were uploaded
        if 'source_pdf' not in request.files or 'template_pdf' not in request.files:
            flash('Please upload both source and template PDF files')
            return redirect(request.url)
        
        source_file = request.files['source_pdf']
        template_file = request.files['template_pdf']
        
        # Check if files are empty
        if source_file.filename == '' or template_file.filename == '':
            flash('No file selected')
            return redirect(request.url)
        
        # Check if files are allowed
        if not allowed_file(source_file.filename) or not allowed_file(template_file.filename):
            flash('Only PDF files are allowed')
            return redirect(request.url)
        
        # Save uploaded files
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        source_filename = secure_filename(f"{timestamp}_source_{source_file.filename}")
        template_filename = secure_filename(f"{timestamp}_template_{template_file.filename}")
        
        source_path = os.path.join(app.config['UPLOAD_FOLDER'], source_filename)
        template_path = os.path.join(app.config['UPLOAD_FOLDER'], template_filename)
        
        source_file.save(source_path)
        template_file.save(template_path)
        
        try:
            # First convert source PDF to Word for better text extraction
            word_filename = f"{timestamp}_{os.path.splitext(source_file.filename)[0]}.docx"
            word_path = os.path.join(app.config['CONVERTED_FOLDER'], word_filename)
            logger.info(f"Converting source PDF to Word: {source_path}")
            convert_pdf_to_doc(source_path, word_path)
            
            # Extract data and fill template
            logger.info("Starting data extraction from source PDF")
            extractor = PDFFormExtractor()
            extracted_data = extractor.extract_data_from_pdf(source_path)
            logger.info(f"Extracted data: {json.dumps(extracted_data, indent=2)}")
            
            # Save extraction log
            log_file = save_extraction_log(timestamp, extracted_data, source_filename, template_filename)
            logger.info(f"Saved extraction log to: {log_file}")
            
            # Generate output filename for filled form
            output_filename = f"{timestamp}_filled_{os.path.splitext(template_file.filename)[0]}.pdf"
            output_path = os.path.join(app.config['FILLED_FORMS_FOLDER'], output_filename)
            
            # Fill the template with extracted data
            logger.info("Filling template PDF with extracted data")
            extractor.fill_pdf_form(template_path, output_path, extracted_data)
            logger.info(f"Filled form saved to: {output_path}")
            
            flash('Files processed successfully! You can download the converted Word document and filled form below.')
            
        except Exception as e:
            logger.error(f"Error during processing: {str(e)}")
            flash(f'Error processing files: {str(e)}')
            return redirect(url_for('index'))
        
        finally:
            # Clean up uploaded files
            try:
                os.remove(source_path)
                os.remove(template_path)
            except Exception as e:
                logger.error(f"Error cleaning up temporary files: {str(e)}")
        
        return redirect(url_for('index'))
        
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        flash(f'Error processing request: {str(e)}')
        return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True) 