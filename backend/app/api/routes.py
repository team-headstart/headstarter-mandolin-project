from fastapi import APIRouter, HTTPException, Depends, File, UploadFile, Form
from fastapi.responses import FileResponse, StreamingResponse
import tempfile
import shutil
import os
import logging
from typing import Optional

from ..models.schemas import ProcessingResult
from ..services.processor import PAFormProcessor

router = APIRouter(prefix="/api/v1")

# Set up a logger for this module
logger = logging.getLogger(__name__)

@router.post("/process")
async def process_form(
    referral_document: UploadFile = File(..., description="The referral document (PDF or image)."),
    pa_form: UploadFile = File(..., description="The PA form PDF to be processed."),
    output_dir: str = Form("Output_Data", description="Directory on server to save output files.")
):
    """
    Process a Prior Authorization form by uploading the necessary files.
    
    This endpoint accepts a PA form and a referral document, processes them,
    and returns the processed PDF file directly for download.
    """
    # Create a temporary directory to store uploaded files for processing
    with tempfile.TemporaryDirectory() as temp_dir:
        pa_form_path = os.path.join(temp_dir, pa_form.filename)
        referral_path = os.path.join(temp_dir, referral_document.filename)

        # Save uploaded files to the temporary directory
        try:
            with open(pa_form_path, "wb") as buffer:
                shutil.copyfileobj(pa_form.file, buffer)
            logger.info(f"Temporarily saved PA form to {pa_form_path}")
            
            with open(referral_path, "wb") as buffer:
                shutil.copyfileobj(referral_document.file, buffer)
            logger.info(f"Temporarily saved referral to {referral_path}")

        finally:
            # Ensure the file objects are closed
            pa_form.file.close()
            referral_document.file.close()
            
        try:
            processor = PAFormProcessor()
            result = await processor.process_prior_auth(
                pa_form_path,
                referral_path,
                output_dir
            )
            
            if result.success and result.filled_pdf_path and os.path.exists(result.filled_pdf_path):
                # Return the file directly for download
                return FileResponse(
                    path=result.filled_pdf_path,
                    media_type='application/pdf',
                    filename='processed_pa_form.pdf',
                    headers={
                        'Content-Disposition': 'attachment; filename="processed_pa_form.pdf"'
                    }
                )
            else:
                raise HTTPException(
                    status_code=500,
                    detail=f"Processing failed: {result.error_message or 'Unknown error'}"
                )
                
        except Exception as e:
            logger.error(f"Error during form processing: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error processing form: {str(e)}"
            )

@router.get("/download/{filename}")
async def download_file(filename: str):
    """
    Download a processed file by filename.
    """
    output_dir = "Output_Data"
    file_path = os.path.join(output_dir, filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        path=file_path,
        media_type='application/pdf',
        filename=filename,
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"'
        }
    )

@router.get("/files")
async def list_processed_files():
    """
    List all processed files available for download.
    """
    output_dir = "Output_Data"
    if not os.path.exists(output_dir):
        return {"files": []}
    
    files = []
    for filename in os.listdir(output_dir):
        if filename.endswith('.pdf'):
            file_path = os.path.join(output_dir, filename)
            files.append({
                "filename": filename,
                "size": os.path.getsize(file_path),
                "modified": os.path.getmtime(file_path)
            })
    
    return {"files": files} 