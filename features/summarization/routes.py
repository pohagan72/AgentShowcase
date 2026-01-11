# features/summarization/routes.py
import os
import io
import uuid
import logging
from flask import (
    Blueprint, request, current_app, jsonify, Response, 
    stream_with_context, g, url_for, send_file, flash, redirect
)
from werkzeug.utils import secure_filename

# --- Import Agents & Utils ---
from .agents import analyst_agent
from .agents import designer_agent
from . import utils  # Shared utilities for text extraction

bp = Blueprint('summarization', __name__)

def get_input_data():
    """
    Handles the logic for retrieving the file (either uploaded or sample)
    and extracting its text content.
    
    Returns:
        tuple: (text_content, filename_display)
    """
    text = ""
    filename = "Document"

    # 1. Check for Sample usage (IBM Report)
    if request.form.get("use_sample") == "true":
        filename = "IBM_Report.pdf"
        # Path to the static sample file
        path = os.path.join(current_app.root_path, 'static', 'files', "IBM-2024-annual-report.pdf")
        
        if os.path.exists(path):
            try:
                with open(path, 'rb') as f:
                    # Read into memory and extract
                    file_bytes = io.BytesIO(f.read())
                    text = utils.extract_text_from_stream(file_bytes, '.pdf')
            except Exception as e:
                logging.error(f"Error reading sample file: {e}")
        else:
            logging.error(f"Sample file not found at: {path}")

    # 2. Check for User File Upload
    else:
        file = request.files.get("file")
        if file and file.filename:
            # Use the utility to handle FileStorage object
            text, filename = utils.read_text_from_file(file)

    return text, filename

# --- Route 1: Text Analysis (The Analyst Agent) ---
@bp.route("/process/summarization/summarize", methods=["POST"])
def process_summarize():
    """
    Endpoint for the 'Create Text Summary' tab.
    Delegates to the Analyst Agent for mandate-driven analysis.
    """
    # 1. Validate Service Config
    if not current_app.config.get('GEMINI_CONFIGURED'): 
        return jsonify({"error": "Gemini AI service is not configured."}), 503
    
    # 2. Parse Input
    text, filename = get_input_data()

    if not text: 
        return jsonify({"error": "Could not extract text from the file. Please ensure it is a valid PDF, DOCX, or PPTX."}), 400

    model_name = current_app.config.get('GEMINI_MODEL_NAME')

    # 3. Stream Analyst Response
    return Response(
        stream_with_context(
            analyst_agent.stream_analysis(text, model_name, filename)
        ), 
        mimetype='application/x-ndjson'
    )

# --- Route 2: PPT Generation (The Designer Agent) ---
@bp.route("/process/summarization/create_ppt", methods=["POST"])
def process_create_ppt():
    """
    Endpoint for the 'Create Executive PowerPoint' tab.
    Delegates to the Designer Agent for structured slide generation.
    """
    g.request_id = uuid.uuid4().hex
    
    # 1. Validate Service Config
    if not current_app.config.get('GEMINI_CONFIGURED'): 
        return jsonify({"error": "Gemini AI service is not configured."}), 503

    # 2. Parse Input
    text, filename = get_input_data()
    
    if not text:
         return jsonify({"error": "Could not extract text from the file. PDF/DOCX/PPTX supported."}), 400

    # 3. Get Options
    template = request.form.get('template', 'professional')
    model_name = current_app.config.get('GEMINI_MODEL_NAME')
    
    # 4. Stream Designer Response
    return Response(
        stream_with_context(
            designer_agent.stream_ppt_generation(
                text_content=text,
                model_name=model_name,
                template=template,
                req_id=g.request_id,
                filename=filename
            )
        ),
        mimetype='application/x-ndjson'
    )

# --- Route 3: File Download ---
@bp.route("/download/ppt/<file_id>/<filename>", methods=["GET"])
def download_generated_ppt(file_id, filename):
    """
    Serves the generated PPTX file from Cloud Storage.
    """
    gcs_path = f"{file_id}/output/{filename}" 
    
    if not current_app.config.get('GCS_AVAILABLE'):
        flash("Cloud storage is unavailable.", "error")
        return redirect(url_for('main.index', feature_key='summarization'))
    
    try:
        blob = current_app.gcs_bucket.blob(gcs_path)
        if not blob.exists():
            flash("File expired or not found. Please regenerate.", "error")
            return redirect(url_for('main.index', feature_key='summarization'))
        
        buffer = io.BytesIO()
        blob.download_to_file(buffer)
        buffer.seek(0)
        
        return send_file(
            buffer, 
            as_attachment=True, 
            download_name=filename, 
            mimetype='application/vnd.openxmlformats-officedocument.presentationml.presentation'
        )
    except Exception as e:
        logging.error(f"Download Error for {filename}: {e}")
        flash("An error occurred while downloading the file.", "error")
        return redirect(url_for('main.index', feature_key='summarization'))