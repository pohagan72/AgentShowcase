from flask import (
    render_template, request, flash, current_app, url_for, g, redirect, send_file, jsonify, after_this_request
)
import os
import io
import uuid
import re
import logging
import time
import threading
from urllib.parse import urlparse # <--- ADDED THIS IMPORT

from werkzeug.utils import secure_filename
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from google.cloud import storage
from google.cloud.exceptions import NotFound as GCSNotFound

from docx import Document
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
import pandas as pd
import PyPDF2

# --- Imports for PPT Builder Logic ---
try:
    from .ppt_builder_logic import prompts as ppt_prompts
    from .ppt_builder_logic import translate as ppt_translate
    from .ppt_builder_logic.file_processor import (
        allowed_file as ppt_allowed_file_util,
        extract_text_from_blob as ppt_extract_text_from_blob
    )
    from .ppt_builder_logic.url_processor import is_safe_url as ppt_is_safe_url, fetch_and_extract_url_content as ppt_fetch_and_extract_url_content
    from .ppt_builder_logic.presentation_generator import create_presentation as ppt_create_presentation
    from .ppt_builder_logic.core_processor import generate_slides_from_text as ppt_generate_slides_from_text
    PPT_BUILDER_MODULES_LOADED = True
except ImportError as e:
    logging.error(f"Critical Error: Could not import PPT Builder logic modules: {e}. 'Create Executive PowerPoint' will FAIL.", exc_info=True)
    PPT_BUILDER_MODULES_LOADED = False
    # Define dummy functions if modules fail to load
    def dummy_ppt_func(*args, **kwargs): raise NotImplementedError("PPT Builder modules failed to load.")
    ppt_allowed_file_util = lambda x, y: False
    ppt_extract_text_from_blob = dummy_ppt_func
    ppt_is_safe_url = lambda x: False
    ppt_fetch_and_extract_url_content = dummy_ppt_func
    ppt_create_presentation = dummy_ppt_func
    ppt_generate_slides_from_text = dummy_ppt_func
    # Create a dummy ppt_prompts object with MAX_INPUT_CHARS for call_llm_for_ppt_builder fallback
    ppt_prompts = type('DummyPrompts', (), {'MAX_INPUT_CHARS': 3000000})() 
    ppt_translate = type('DummyTranslate', (), {'translate_slide_data': dummy_ppt_func})()

# --- Constants for Text Summarization ---
MAX_CONTENT_LENGTH_TEXT_SUMMARY = 1000000
MAX_CLASSIFICATION_EXCERPT_TEXT_SUMMARY = 15000 # Max chars for classifying text summary input
TEXT_SUMMARY_MAX_FILE_SIZE_MB = 10 # New constant for file size limit
TEXT_SUMMARY_MAX_FILE_SIZE_BYTES = TEXT_SUMMARY_MAX_FILE_SIZE_MB * 1024 * 1024

CLASSIFICATION_CATEGORIES_TEXT_SUMMARY = [
    "Resume/CV", "Patent", "Terms of Service (ToS)", "Service Level Agreement (SLA)",
    "Contract/Agreement", "Privacy Policy", "Informational Guide/Manual",
    "Technical Report/Documentation", "Python Source Code", "News Article/Blog Post",
    "Marketing Plan/Proposal", "Meeting Notes/Summary", "Case Study / Research Report",
    "Financial Report (Annual/10-K/10-Q)", "Web Page Content", "Reddit Thread",
    "Legal Case Brief", "Legislative Bill/Regulation", "Business Plan",
    "SWOT Analysis Document", "Press Release", "System Design Document",
    "User Story / Feature Requirement Document", "Medical Journal Article",
    "Academic Paper/Research", "General Business Document", "Other",
]

# --- DEFAULT Constants for PPT Builder (used if not in app.config) ---
DEFAULT_PPT_MODEL_INPUT_TOKEN_LIMITS = {
    "gemini-1.0-pro": 30720, "gemini-pro": 30720,
    "gemini-1.5-pro-latest": 1048576, "gemini-1.5-flash-latest": 1048576,
    "gemini-1.5-flash-001": 1048576, "gemini-2.0-flash": 1048576,
    "gemini-2.0-flash-001": 1048576,
}
DEFAULT_PPT_DEFAULT_INPUT_TOKEN_LIMIT = 30000
DEFAULT_PPT_MAX_CONCURRENT_REQUESTS = 3

ppt_processing_semaphore = threading.Semaphore(DEFAULT_PPT_MAX_CONCURRENT_REQUESTS)
logging.info(f"Summarization Feature: Initialized PPT processing semaphore with static limit: {DEFAULT_PPT_MAX_CONCURRENT_REQUESTS}")

# --- Generic File Reading Utilities ---
def read_text_from_docx(file_stream):
    try:
        file_stream.seek(0)
        doc = Document(file_stream)
        full_text = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
        for table in doc.tables: # Also extract from tables
            for row in table.rows:
                for cell in row.cells:
                    cell_text = "\n".join([p.text for p in cell.paragraphs if p.text and p.text.strip()])
                    if cell_text: full_text.append(cell_text)
        return "\n".join(full_text) if full_text else ""
    except Exception as e: logging.error(f"Error reading DOCX: {e}", exc_info=True); raise

def read_text_from_pptx(file_stream):
    try:
        file_stream.seek(0)
        ppt = Presentation(file_stream)
        text_runs = []
        for slide in ppt.slides:
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for paragraph in shape.text_frame.paragraphs:
                        for run in paragraph.runs:
                            if run.text and run.text.strip(): 
                                text_runs.append(run.text.strip())
        return "\n".join(text_runs) if text_runs else ""
    except Exception as e: logging.error(f"Error reading PPTX: {e}", exc_info=True); raise

def read_text_from_excel(file_stream):
    try:
        file_stream.seek(0)
        excel_data = pd.read_excel(file_stream, sheet_name=None)
        text_list = []
        if excel_data:
            for sheet_name, df in excel_data.items():
                for r_idx in range(len(df)):
                    for c_idx in range(len(df.columns)):
                        cell_value = df.iat[r_idx, c_idx]
                        if pd.notna(cell_value) and str(cell_value).strip():
                            text_list.append(str(cell_value).strip())
        return "\n".join(filter(None, text_list))
    except Exception as e: logging.error(f"Error reading Excel: {e}", exc_info=True); raise

def read_text_from_pdf(file_stream):
    try:
        file_stream.seek(0)
        reader = PyPDF2.PdfReader(file_stream)
        text_list = []
        if reader.pages:
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted and extracted.strip(): 
                    text_list.append(extracted.strip())
        return "\n".join(text_list) if text_list else ""
    except Exception as e: logging.error(f"Error reading PDF: {e}", exc_info=True); raise

# --- HELPER FUNCTIONS FOR "CREATE TEXT SUMMARY" TAB ---
def get_classification_prompt_for_text_summary(text_excerpt):
    categories_str = "\n - ".join(CLASSIFICATION_CATEGORIES_TEXT_SUMMARY)
    prompt = f"""Analyze the following text excerpt to determine its primary document type. Respond with ONLY the most fitting category name from the list provided.
Available Categories:
 - {categories_str}
Document Excerpt:
\"\"\"
{text_excerpt}
\"\"\"
Document Classification Category:"""
    return prompt

def parse_classification_response_for_text_summary(llm_response_text):
    potential_category = llm_response_text.strip()
    cleaned_category_llm = re.sub(r'[^\w\s/\(\)\-]', '', potential_category).strip()
    for cat in CLASSIFICATION_CATEGORIES_TEXT_SUMMARY:
        if cat.lower() == cleaned_category_llm.lower(): return cat
    for cat in CLASSIFICATION_CATEGORIES_TEXT_SUMMARY:
        if cat.lower() in cleaned_category_llm.lower():
            logging.warning(f"Text Summary Classification: Fuzzy match for '{potential_category}' -> '{cat}'")
            return cat
    return "Other"

def build_expert_text_summary_prompt(text_to_summarize, classification):
    expert_focus = "Focus on its main topic, key arguments, and conclusions." # Default
    if classification == "Resume/CV": expert_focus = "Focus on the candidate's key skills, experiences, and quantifiable achievements relevant to a potential employer."
    elif classification == "Patent": expert_focus = "Focus on the core invention, its novelty, the problem it solves, and the essence of its main claims."
    elif classification == "Financial Report (Annual/10-K/10-Q)": expert_focus = "Focus on key financial highlights (like revenue, net income), major trends, and any stated outlook."
    # (You would add more elif blocks here for other document types from CLASSIFICATION_CATEGORIES_TEXT_SUMMARY)
    else: expert_focus = f"Given this is a '{classification}', focus on extracting its primary purpose and most critical information."

    prompt = f"""SYSTEM: You are an expert summarization AI. The document has been identified as a '{classification}'.
INSTRUCTIONS:
1. Based on it being a '{classification}', {expert_focus}
2. Generate a concise text summary, approximately 3-6 sentences long, that captures the essence of the document.
3. Ensure the summary is coherent, accurate, and directly reflects the content provided.
4. Output ONLY the summary. Do not include any preambles like "Here is the summary:", conversational phrases, or quotation marks around the summary.

TEXT TO SUMMARIZE:
---
{text_to_summarize}
---
"""
    return prompt

def classify_and_summarize_with_gemini(text_content, model_name_from_config, filename=""):
    """
    Classifies text and generates a TEXT summary using Gemini.
    Returns tuple: (classification_detected, summary_text, error_occurred_bool)
    """
    if not text_content or not text_content.strip():
        return "N/A", "No text provided for summarization.", True # error_occurred = True
    
    classification = "Other" # Default classification
    final_summary = ""
    error_occurred = False
    req_id_tag = g.request_id if hasattr(g, 'request_id') else 'TEXT_SUM_TASK'

    try:
        model = genai.GenerativeModel(model_name_from_config)

        # Step 1: Classification for Text Summary
        classification_excerpt = text_content[:MAX_CLASSIFICATION_EXCERPT_TEXT_SUMMARY]
        classification_prompt = get_classification_prompt_for_text_summary(classification_excerpt)
        
        logging.info(f"[{req_id_tag}] TextSummary: Sending classification prompt (excerpt len: {len(classification_excerpt)})...")
        classification_response = model.generate_content(classification_prompt)
        
        if classification_response and classification_response.text:
            classification = parse_classification_response_for_text_summary(classification_response.text)
            flash(f"Text Summary - Detected document type: {classification}", "info")
            logging.info(f"[{req_id_tag}] Text Summary Classification result: {classification}")
        elif hasattr(classification_response, 'prompt_feedback') and classification_response.prompt_feedback.block_reason:
            reason = classification_response.prompt_feedback.block_reason.name
            msg = f"Text summary classification blocked by AI safety filters ({reason}). Using 'Other'."
            logging.warning(f"[{req_id_tag}] {msg}")
            flash(msg, "warning")
            classification = "Other"
        else:
            msg = "Text summary classification failed: AI returned no text. Using 'Other'."
            logging.warning(f"[{req_id_tag}] {msg}")
            flash(msg, "warning")
            classification = "Other"

        # Step 2: Text Summarization using the classification
        summary_prompt = build_expert_text_summary_prompt(text_content, classification)
        logging.info(f"[{req_id_tag}] TextSummary: Sending expert summarization prompt (class: {classification})...")
        summary_response = model.generate_content(summary_prompt)

        if summary_response and summary_response.text:
            final_summary = summary_response.text.strip()
            logging.info(f"[{req_id_tag}] Text summary generated successfully.")
        elif hasattr(summary_response, 'prompt_feedback') and summary_response.prompt_feedback.block_reason:
            reason = summary_response.prompt_feedback.block_reason.name
            final_summary = f"(Text summarization was blocked by safety filters: {reason})"
            flash(final_summary, "warning")
            error_occurred = True
        else:
            final_summary = "(Text summarization failed: The AI model did not return any text.)"
            flash(final_summary, "error")
            error_occurred = True
            
    except Exception as e:
        error_msg = f"(Error occurred during text summarization AI process: {str(e)})"
        logging.error(f"[{req_id_tag}] Error in classify_and_summarize_with_gemini: {e}", exc_info=True)
        flash(error_msg, "error")
        final_summary = error_msg # Ensure error is passed back
        error_occurred = True

    return classification, final_summary, error_occurred

# --- Helper: call_llm function for PPT Builder ---
def call_llm_for_ppt_builder(prompt_text, max_output_tokens=8192, req_id="PPT_LLM_Call"):
    gemini_model_name = current_app.config.get('GEMINI_MODEL_NAME')
    if not current_app.config.get('GEMINI_CONFIGURED') or not gemini_model_name:
        logging.error(f"[{req_id}] LLM call failed for PPT: Gemini not configured.", extra={'event': 'ppt_llm_error_shell_config'})
        raise ValueError("AI service (Gemini) is not configured for PPT generation.")
    try:
        model_instance = genai.GenerativeModel(gemini_model_name)
        ppt_model_limits_config = current_app.config.get('PPT_MODEL_TOKEN_LIMITS', DEFAULT_PPT_MODEL_INPUT_TOKEN_LIMITS)
        ppt_default_token_limit_config = current_app.config.get('PPT_DEFAULT_TOKEN_LIMIT', DEFAULT_PPT_DEFAULT_INPUT_TOKEN_LIMIT)

        token_count_response = model_instance.count_tokens(prompt_text)
        input_token_count = token_count_response.total_tokens
        current_model_limit = ppt_model_limits_config.get(gemini_model_name, ppt_default_token_limit_config)
        if input_token_count > current_model_limit:
            raise ValueError(f"Input prompt ({input_token_count} tokens) for PPT exceeds model '{gemini_model_name}' limit ({current_model_limit}).")

        generation_config = genai.types.GenerationConfig(max_output_tokens=max_output_tokens, temperature=0.5, top_p=0.95)
        # Ensure all HarmCategory members are used for safety settings
        safety_settings = [{"category": c, "threshold": "BLOCK_MEDIUM_AND_ABOVE"} 
                           for c in genai.types.HarmCategory 
                           if c != genai.types.HarmCategory.HARM_CATEGORY_UNSPECIFIED]
        
        logging.info(f"[{req_id}] Calling Gemini for PPT (Model: {gemini_model_name}, Input Tokens: {input_token_count})")
        response = model_instance.generate_content(prompt_text, generation_config=generation_config, safety_settings=safety_settings)
        
        if response.prompt_feedback and response.prompt_feedback.block_reason:
            raise ValueError(f"PPT content blocked by safety filters ({response.prompt_feedback.block_reason.name}).")
        if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
            return "".join(part.text for part in response.candidates[0].content.parts if hasattr(part, 'text')).strip()
        # Check for safety ratings if no content but also no explicit block reason
        if response.candidates and response.candidates[0].finish_reason.name == "SAFETY":
            safety_ratings_str = ", ".join([f"{r.category.name}: {r.probability.name}" for r in response.candidates[0].safety_ratings if hasattr(r, 'category') and hasattr(r, 'probability')])
            raise ValueError(f"PPT content generation likely blocked by safety filters. Ratings: [{safety_ratings_str}]")
        raise ValueError("AI model returned no valid content for PPT generation.")
    except Exception as e:
        logging.error(f"[{req_id}] Error in call_llm_for_ppt_builder: {e}", exc_info=True)
        raise # Re-raise to be handled by process_create_ppt

def define_summarization_routes(app_shell):

    @app_shell.route("/process/summarization/summarize", methods=["POST"])
    def process_summarize():
        g.request_id = uuid.uuid4().hex 
        logging.info(f"Received text summarization request {g.request_id}")
        context = {"summary": "", "hx_target_is_text_summary_result": True}

        if not current_app.config.get('GEMINI_CONFIGURED'):
            flash("Gemini API not configured. Summarization service unavailable.", "error")
            return render_template("summarization/templates/summarization_content.html", **context)

        text_content_from_file = ""
        filename_for_context = ""
        file_input = request.files.get("file") 

        if file_input and file_input.filename:
            filename_for_context = secure_filename(file_input.filename)
            
            # --- Check file size ---
            file_input.seek(0, os.SEEK_END)
            file_size = file_input.tell()
            file_input.seek(0) # Reset stream position

            if file_size > TEXT_SUMMARY_MAX_FILE_SIZE_BYTES:
                flash(f"File '{filename_for_context}' ({file_size/1024/1024:.2f}MB) is too large. Maximum allowed size is {TEXT_SUMMARY_MAX_FILE_SIZE_MB}MB.", "error")
                return render_template("summarization/templates/summarization_content.html", **context)
            # --- End file size check ---

            file_ext = os.path.splitext(filename_for_context)[1].lower()
            logging.info(f"[{g.request_id}] Text Summary: Processing file '{filename_for_context}' (Size: {file_size} bytes)")
            try:
                file_stream = io.BytesIO(file_input.read()) # Read after size check
                if file_ext == ".docx": text_content_from_file = read_text_from_docx(file_stream)
                elif file_ext == ".pptx": text_content_from_file = read_text_from_pptx(file_stream)
                elif file_ext == ".xlsx": text_content_from_file = read_text_from_excel(file_stream)
                elif file_ext == ".pdf": text_content_from_file = read_text_from_pdf(file_stream)
                else:
                    flash(f"Unsupported file type '{file_ext}' for text summary.", "error")
                    return render_template("summarization/templates/summarization_content.html", **context)
                
                if not isinstance(text_content_from_file, str): text_content_from_file = "" 
                if not text_content_from_file.strip():
                     flash(f"No text extracted from file '{filename_for_context}' for text summary. The file might be empty, image-based, or password-protected.", "warning")
            except Exception as e:
                flash(f"Error reading file '{filename_for_context}': {str(e)}", "error")
                logging.error(f"[{g.request_id}] Error reading file for text summary: {e}", exc_info=True)
                return render_template("summarization/templates/summarization_content.html", **context)
        
        content_to_process = text_content_from_file if text_content_from_file and text_content_from_file.strip() else request.form.get("text_to_summarize", "").strip()
        
        if not content_to_process:
            # This message might now be less common if a file is required and successfully read.
            # It could still trigger if file upload failed silently client-side or if an empty file was uploaded and no text extracted.
            flash("Please upload a file to summarize, or ensure the uploaded file contains extractable text and is not empty.", "warning")
            return render_template("summarization/templates/summarization_content.html", **context)
        
        if len(content_to_process) > MAX_CONTENT_LENGTH_TEXT_SUMMARY: # This is a check on TEXT content length, not file size.
             flash(f"Extracted text for summary (length: {len(content_to_process):,}) exceeds internal processing limit of {MAX_CONTENT_LENGTH_TEXT_SUMMARY:,} characters.", "error")
             return render_template("summarization/templates/summarization_content.html", **context)

        model_name = current_app.config.get('GEMINI_MODEL_NAME')
        _classification, summary_text, _error = classify_and_summarize_with_gemini(
            content_to_process, model_name, filename_for_context
        )
        context["summary"] = summary_text
        return render_template("summarization/templates/summarization_content.html", **context)

    # NEW ROUTE FOR DOWNLOADING GENERATED PPTX
    @app_shell.route("/download/ppt/<file_id>/<filename>", methods=["GET"])
    def download_generated_ppt(file_id, filename):
        """
        Serves a generated PowerPoint file from GCS to the user.
        This endpoint is hit by the browser's direct GET request, not HTMX.
        """
        log_extra_ppt = {'extra_data': {'request_id': file_id, 'feature': 'ppt_download'}}
        # Construct the GCS path for the output file
        gcs_path = f"{file_id}/output/{filename}" 

        if not current_app.config.get('GCS_AVAILABLE'):
            logging.error(f"[{file_id}] GCS not available for download.", extra=log_extra_ppt)
            flash("Download service currently unavailable (Cloud Storage not configured).", "error")
            return redirect(url_for('home')) # Redirect to a safe page if GCS is down

        try:
            blob = current_app.gcs_bucket.blob(gcs_path)
            if not blob.exists():
                logging.warning(f"[{file_id}] Attempted to download non-existent PPTX: {gcs_path}", extra=log_extra_ppt)
                flash("The presentation file was not found or has expired. Please try generating it again.", "error")
                return redirect(url_for('display_feature', feature_name='summarization')) # Redirect to the summarization feature

            # Read blob content into a BytesIO buffer
            buffer = io.BytesIO()
            blob.download_to_file(buffer)
            buffer.seek(0) # Rewind the buffer to the beginning before sending

            logging.info(f"[{file_id}] Successfully serving PPTX: {gcs_path}", extra=log_extra_ppt)
            
            # Use send_file to stream the content to the browser, triggering download
            return send_file(
                buffer,
                as_attachment=True,
                download_name=filename,
                mimetype='application/vnd.openxmlformats-officedocument.presentationml.presentation'
            )
        except GCSNotFound:
            logging.error(f"[{file_id}] GCSNotFound when downloading {gcs_path}", exc_info=True, extra=log_extra_ppt)
            flash("The presentation file was not found or has expired. Please try generating it again.", "error")
            return redirect(url_for('display_feature', feature_name='summarization'))
        except Exception as e:
            logging.error(f"[{file_id}] Error serving generated PPTX from GCS ({gcs_path}): {e}", exc_info=True, extra=log_extra_ppt)
            flash("An unexpected error occurred while preparing your download.", "error")
            return redirect(url_for('display_feature', feature_name='summarization'))

    @app_shell.route("/process/summarization/create_ppt", methods=["POST"])
    def process_create_ppt():
        g.request_id = uuid.uuid4().hex
        g.start_time = time.time()
        log_extra_ppt = {'extra_data': {'request_id': g.request_id, 'feature': 'ppt_builder_shell'}}
        
        # This function will run *after* the request is completed,
        # ensuring semaphore release and cleanup of *input* files.
        # Output files will be cleaned by GCS lifecycle policies.
        @after_this_request
        def release_semaphore_and_cleanup_uploads(response):
            req_id_clean = getattr(g, 'request_id', 'PPT_CLEAN_FALLBACK')
            start_time_clean = getattr(g, 'start_time', time.time())
            
            # Only clean up the 'uploads/' folder for this request_id
            if current_app.gcs_bucket: # Ensure bucket is available
                upload_prefix_to_clean = f"{req_id_clean}/uploads/"
                try:
                    blobs_to_delete = list(current_app.storage_client.list_blobs(current_app.gcs_bucket, prefix=upload_prefix_to_clean))
                    if blobs_to_delete:
                        current_app.gcs_bucket.delete_blobs(blobs=blobs_to_delete)
                        logging.info(f"[{req_id_clean}] PPT GCS Input Uploads Cleanup for '{upload_prefix_to_clean}' done ({len(blobs_to_delete)} blobs).")
                except Exception as e_clean_final:
                    logging.error(f"[{req_id_clean}] PPT GCS Input Uploads Cleanup error for '{upload_prefix_to_clean}': {e_clean_final}", exc_info=True)
            
            ppt_processing_semaphore.release() # Release semaphore
            logging.info(f"[{req_id_clean}] PPT Request: Slot released. Total duration: {int((time.time() - start_time_clean) * 1000)}ms")
            return response

        if not PPT_BUILDER_MODULES_LOADED:
            logging.critical(f"[{g.request_id}] PPT Builder modules not loaded. Cannot process PPT request.", extra=log_extra_ppt)
            context = {"ppt_error_message": "Server error: PowerPoint generation components are missing.", "hx_target_is_ppt_status_result": True}
            return render_template("summarization/templates/summarization_content.html", **context), 500

        if not current_app.config.get('GEMINI_CONFIGURED') or not current_app.config.get('GCS_AVAILABLE'):
            err_msg = "AI service or Cloud Storage is unavailable for PowerPoint generation. Please check configuration."
            logging.error(f"[{g.request_id}] {err_msg}", extra=log_extra_ppt)
            context = {"ppt_error_message": err_msg, "hx_target_is_ppt_status_result": True}
            return render_template("summarization/templates/summarization_content.html", **context), 503

        max_concurrent = current_app.config.get('PPT_MAX_CONCURRENT_REQUESTS', DEFAULT_PPT_MAX_CONCURRENT_REQUESTS)
        current_sem = ppt_processing_semaphore 
        
        logging.info(f"[{g.request_id}] PPT Request: Attempting to acquire slot (max: {max_concurrent}, current_val: {current_sem._value if hasattr(current_sem, '_value') else 'N/A'})...", extra=log_extra_ppt)
        if not current_sem.acquire(blocking=True, timeout=10): # Added timeout for acquire
            logging.warning(f"[{g.request_id}] PPT Request: Failed to acquire slot (server busy/timeout).", extra=log_extra_ppt)
            context = {"ppt_error_message": "Server is very busy, please try again in a moment.", "hx_target_is_ppt_status_result": True}
            return render_template("summarization/templates/summarization_content.html", **context), 503
        logging.info(f"[{g.request_id}] PPT Request: Slot acquired.", extra=log_extra_ppt)

        try:
            input_type = request.form.get('inputType')
            template_style = request.form.get('template', current_app.config.get('PPT_DEFAULT_TEMPLATE_NAME', 'professional')).lower()
            audience = request.form.get('audience', '').strip()
            tone = request.form.get('tone', '').strip()
            language = request.form.get('language', '').strip()

            all_slides_data = {}
            any_source_truncated = False
            
            if input_type == 'url':
                source_url = request.form.get('sourceUrl', '').strip()
                if not source_url or not ppt_is_safe_url(source_url):
                    context = {"ppt_error_message": "Invalid or unsafe URL.", "hx_target_is_ppt_status_result": True}
                    return render_template("summarization/templates/summarization_content.html", **context), 400
                try:
                    text, trunc = ppt_fetch_and_extract_url_content(source_url)
                    if trunc: any_source_truncated = True
                    slide_result_list = ppt_generate_slides_from_text(
                        text=text, source_identifier=source_url,
                        call_llm_func=call_llm_for_ppt_builder, 
                        translate_func=ppt_translate.translate_slide_data,
                        language=language, audience=audience, tone=tone, template_name=template_style,
                        truncated=trunc, is_multi_doc=False, total_docs=1
                    )
                    all_slides_data[source_url] = slide_result_list
                except Exception as e_url_proc:
                    logging.error(f"[{g.request_id}] URL processing error for PPT: {e_url_proc}", exc_info=True, extra=log_extra_ppt)
                    context = {"ppt_error_message": f"Failed to process URL: {str(e_url_proc)}", "hx_target_is_ppt_status_result": True}
                    return render_template("summarization/templates/summarization_content.html", **context), 500
            
            elif input_type == 'file':
                uploaded_files = request.files.getlist('file')
                
                max_files_config = current_app.config.get('PPT_MAX_FILES', 5)
                # Use the app config for PPT max file size, which defaults to 10MB if not set.
                max_file_size_config_ppt = current_app.config.get('PPT_MAX_FILE_SIZE_MB', 10) * 1024 * 1024 
                allowed_ext_str_config = current_app.config.get('PPT_ALLOWED_EXTENSIONS_STR', '.docx,.pdf,.py')
                allowed_ext_set_config = set(ext.strip().lower() for ext in allowed_ext_str_config.replace('.', '').split(','))

                if not uploaded_files or all(f.filename == '' for f in uploaded_files):
                    context = {"ppt_error_message": "No files selected for presentation generation.", "hx_target_is_ppt_status_result": True}
                    return render_template("summarization/templates/summarization_content.html", **context), 400
                if len(uploaded_files) > max_files_config:
                    context = {"ppt_error_message": f"Too many files. Maximum allowed: {max_files_config}.", "hx_target_is_ppt_status_result": True}
                    return render_template("summarization/templates/summarization_content.html", **context), 400

                valid_files_for_processing = []
                for f_obj in uploaded_files:
                    filename_check = secure_filename(f_obj.filename)
                    f_obj.seek(0, os.SEEK_END); file_size = f_obj.tell(); f_obj.seek(0)
                    if ppt_allowed_file_util(filename_check, allowed_ext_set_config) and file_size <= max_file_size_config_ppt: # Check against PPT specific limit
                        valid_files_for_processing.append(f_obj)
                    else:
                        logging.warning(f"[{g.request_id}] Ignored file for PPT: {filename_check} (size: {file_size}, type_valid: {ppt_allowed_file_util(filename_check, allowed_ext_set_config)}, size_valid: {file_size <= max_file_size_config_ppt})", extra=log_extra_ppt)
                
                if not valid_files_for_processing:
                    context = {"ppt_error_message": f"No valid files provided (check type/size). Allowed: {allowed_ext_str_config}, Max Size: {current_app.config.get('PPT_MAX_FILE_SIZE_MB', 10)}MB", "hx_target_is_ppt_status_result": True}
                    return render_template("summarization/templates/summarization_content.html", **context), 400
                
                total_to_process = len(valid_files_for_processing)
                for idx, file_to_process in enumerate(valid_files_for_processing):
                    original_fname = secure_filename(file_to_process.filename)
                    # Upload input file to GCS for processing by extract_text_from_blob
                    gcs_input_upload_path = f"{g.request_id}/uploads/{original_fname}" # Path for input files
                    try:
                        blob = current_app.gcs_bucket.blob(gcs_input_upload_path)
                        file_to_process.seek(0)
                        blob.upload_from_file(file_to_process, content_type=file_to_process.content_type)
                        logging.info(f"[{g.request_id}] Input file uploaded to GCS: gs://{current_app.gcs_bucket.name}/{gcs_input_upload_path}", extra=log_extra_ppt)
                        
                        text, trunc = ppt_extract_text_from_blob(blob, original_fname) # Use the GCS blob directly
                        if trunc: any_source_truncated = True
                        slide_result_list = ppt_generate_slides_from_text(
                            text=text, source_identifier=original_fname,
                            call_llm_func=call_llm_for_ppt_builder,
                            translate_func=ppt_translate.translate_slide_data,
                            language=language, audience=audience, tone=tone, template_name=template_style,
                            truncated=trunc, is_multi_doc=(total_to_process > 1), total_docs=total_to_process
                        )
                        all_slides_data[original_fname] = slide_result_list
                    except Exception as e_file_proc:
                        logging.error(f"[{g.request_id}] File processing error for PPT ('{original_fname}'): {e_file_proc}", exc_info=True, extra=log_extra_ppt)
                        context = {"ppt_error_message": f"Failed to process file '{original_fname}': {str(e_file_proc)}", "hx_target_is_ppt_status_result": True}
                        return render_template("summarization/templates/summarization_content.html", **context), 500
            else:
                context = {"ppt_error_message": "Invalid input type selected.", "hx_target_is_ppt_status_result": True}
                return render_template("summarization/templates/summarization_content.html", **context), 400

            successful_sources = {k: v for k, v in all_slides_data.items() if isinstance(v, list) and v}
            if not successful_sources:
                 first_err = next((v for v in all_slides_data.values() if isinstance(v, str) and v.startswith("ERROR:")), "Processing failed for all input sources.")
                 context = {"ppt_error_message": f"PPT Generation Failed: {first_err.replace('ERROR: ', '')}", "hx_target_is_ppt_status_result": True}
                 return render_template("summarization/templates/summarization_content.html", **context), 500
            
            pptx_buffer = ppt_create_presentation(
                all_slides_data=all_slides_data, template_name=template_style,
                any_truncated=any_source_truncated, num_processed=len(all_slides_data)
            )
            
            first_src_key = list(all_slides_data.keys())[0]
            base_name = "presentation"
            if input_type == 'url':
                try: parsed_url = urlparse(first_src_key); base_name = parsed_url.netloc.replace('www.','').replace('.','_') or "webpage"
                except: base_name = "webpage"
            elif input_type == 'file':
                base_name = os.path.splitext(first_src_key)[0] if len(all_slides_data) == 1 else f"{len(all_slides_data)}_docs"
            safe_name = re.sub(r'[^\w\-]+', '_', base_name).strip('_')[:50] or "presentation"
            lang_sfx = f"_{language.lower().replace(' (simplified)', '_simplified')}" if language and language.lower() != 'english' else ""
            download_filename = f"{safe_name}_presentation{lang_sfx}_{time.strftime('%Y%m%d_%H%M')}.pptx"

            # --- NEW: Upload the generated PPTX to GCS for later download ---
            output_gcs_path = f"{g.request_id}/output/{download_filename}"
            try:
                blob_output = current_app.gcs_bucket.blob(output_gcs_path)
                pptx_buffer.seek(0) # Ensure buffer is at the beginning
                blob_output.upload_from_file(pptx_buffer, content_type='application/vnd.openxmlformats-officedocument.presentationml.presentation')
                logging.info(f"[{g.request_id}] Generated PPTX uploaded to GCS: gs://{current_app.gcs_bucket.name}/{output_gcs_path}", extra=log_extra_ppt)
            except Exception as e_gcs_upload:
                logging.error(f"[{g.request_id}] Error uploading generated PPTX to GCS: {e_gcs_upload}", exc_info=True, extra=log_extra_ppt)
                context = {"ppt_error_message": "Failed to store generated presentation (Cloud Storage error).", "hx_target_is_ppt_status_result": True}
                return render_template("summarization/templates/summarization_content.html", **context), 500

            # Construct the download URL pointing to our new Flask route
            download_url_for_frontend = url_for('download_generated_ppt', file_id=g.request_id, filename=download_filename)

            # --- RENDER TEMPLATE FOR HTMX SWAP INSTEAD OF send_file ---
            context = {
                "ppt_success_message": "Presentation generated successfully! Click the button below to download.",
                "ppt_download_url": download_url_for_frontend,
                "hx_target_is_ppt_status_result": True # This is key for the frontend template to show the download link
            }
            return render_template("summarization/templates/summarization_content.html", **context)

        except Exception as e_critical_ppt:
            error_message = "An unexpected internal error occurred during PowerPoint generation."
            logging.exception(f"[{g.request_id}] Critical error in PPT generation: {e_critical_ppt}", extra=log_extra_ppt)
            context = {
                "ppt_error_message": error_message,
                "hx_target_is_ppt_status_result": True
            }
            return render_template("summarization/templates/summarization_content.html", **context), 500