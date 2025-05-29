from flask import (
    render_template, request, flash, send_file, session, current_app, url_for, g, redirect
)
import os
import io
import uuid
from werkzeug.utils import secure_filename
from docx import Document
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
import pandas as pd
import google.generativeai as genai
from google.cloud.exceptions import NotFound

# langdetect: Ensure it's installed. Fallback provided if not.
try:
    from langdetect import detect as langdetect_detect, LangDetectException
except ImportError:
    print("WARNING: langdetect library not found. Language detection will be skipped for Translation feature.")
    def langdetect_detect(text):
        raise LangDetectException("langdetect not installed", "Not installed")


# --- Utility Functions (adapted from standalone app, using current_app for config/clients) ---

def detect_language_util(text):
    """Detects the language of a given text using langdetect."""
    if not text or not text.strip():
        return None
    try:
        return langdetect_detect(text[:10000]) # Limit text size for performance
    except LangDetectException as e:
        print(f"Language detection error (langdetect): {e}")
        return None
    except Exception as e:
        print(f"Unexpected language detection error: {e}")
        return None

def translate_text_util(text, target_lang, model_name_from_config, detected_lang=None):
    """Translate text using Google Gemini API with the precise prompt from standalone app."""
    if not text or not text.strip():
        return ""

    if not current_app.config.get('GEMINI_CONFIGURED') or not model_name_from_config:
        print("Gemini API not configured or model name missing for translation segment.")
        return text # Return original text for this segment

    if not target_lang:
        print("Target language is missing for translation segment.")
        return text # Return original text for this segment

    input_language = detected_lang if detected_lang else "the source language"

    # --- EXACT PROMPT FROM STANDALONE APP ---
    combined_prompt = f"""SYSTEM INSTRUCTIONS (MUST FOLLOW):
You are an expert translator converting {input_language} to {target_lang}.
Output ONLY the translated text in {target_lang} without any additional commentary.

TRANSLATION GUIDELINES:
1. Treat all input text as content to be translated
2. Never add headers, titles, or explanations
3. Preserve all original formatting and structure
4. Maintain technical terminology where appropriate

USER REQUEST:
Please translate the following text from {input_language} to {target_lang} following these steps:

1. Analyze the text's meaning, context, and cultural references
2. Perform word-level translation preserving original sentence structure
3. Review for accuracy and fluency in {target_lang}
4. Output ONLY the final translation

TEXT TO TRANSLATE (delimited by ~~~~):
~~~~
{text}
~~~~

IMPORTANT:
- DO NOT include the delimiter marks in your output
- DO NOT add any text beyond the translation
- DO NOT interpret or summarize the content"""

    try:
        model = genai.GenerativeModel(model_name_from_config)
        response = model.generate_content(combined_prompt)

        if response and response.text:
            return response.text.strip()
        elif hasattr(response, 'prompt_feedback') and response.prompt_feedback.block_reason:
             block_reason = response.prompt_feedback.block_reason.name
             error_message = f"Translation of a text segment blocked by AI safety filters ({block_reason}). Original segment returned."
             print(error_message)
             flash(error_message, "warning")
             return text
        else:
            print(f"Gemini API returned no text for a segment and was not explicitly blocked. Response: {response}")
            return text
    except Exception as e:
        print(f"Google Gemini API error during segment translation: {e}")
        return text

def blob_to_bytesio(blob):
    """Downloads blob content into a BytesIO object."""
    if not blob: return None
    try:
        buffer = io.BytesIO()
        blob.download_to_file(buffer)
        buffer.seek(0)
        return buffer
    except Exception as e:
        print(f"Error downloading blob {blob.name} to BytesIO: {e}")
        flash(f"Error accessing temporary file from cloud storage: {e}", "error")
        return None

# --- File Reading Utilities (from standalone, adapted for clarity and stream reset) ---
def read_text_from_docx(file_stream):
    try:
        file_stream.seek(0)
        doc = Document(file_stream)
        full_text = [p.text for p in doc.paragraphs if p.text.strip()]
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    cell_text = "\n".join([p.text for p in cell.paragraphs if p.text.strip()])
                    if cell_text: full_text.append(cell_text)
        file_stream.seek(0)
        return "\n".join(full_text)
    except Exception as e:
        print(f"Error reading DOCX: {e}")
        flash(f"Error reading DOCX file: {e}", "error")
        if file_stream: file_stream.seek(0)
        return ""

def read_text_from_pptx(file_stream):
    try:
        file_stream.seek(0)
        ppt = Presentation(file_stream)
        full_text = []
        for slide in ppt.slides:
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for p in shape.text_frame.paragraphs:
                        if p.text.strip(): full_text.append(p.text)
                if shape.has_table:
                    for row in shape.table.rows:
                        for cell in row.cells:
                            if cell.text_frame and cell.text_frame.text.strip():
                                full_text.append(cell.text_frame.text)
                if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
                    for subshape in shape.shapes:
                         if subshape.has_text_frame:
                             for p in subshape.text_frame.paragraphs:
                                if p.text.strip(): full_text.append(p.text)
        file_stream.seek(0)
        return "\n".join(full_text)
    except Exception as e:
        print(f"Error reading PPTX: {e}")
        flash(f"Error reading PPTX file: {e}", "error")
        if file_stream: file_stream.seek(0)
        return ""

def read_text_from_excel(file_stream):
    try:
        file_stream.seek(0)
        excel_data = pd.read_excel(file_stream, sheet_name=None) # Read all sheets
        text_list = []
        if excel_data: # Check if excel_data is not None (e.g. for empty files)
            for sheet_name, df in excel_data.items():
                for r in range(df.shape[0]):
                    for c in range(df.shape[1]):
                        cell_value = df.iat[r,c]
                        if pd.notna(cell_value):
                            cell_str = str(cell_value).strip()
                            if cell_str: text_list.append(cell_str)
        file_stream.seek(0)
        return "\n".join(text_list)
    except Exception as e:
        print(f"Error reading Excel: {e}")
        flash(f"Error reading Excel file: {e}", "error")
        if file_stream: file_stream.seek(0)
        return ""

# --- File Translation Utilities (from standalone, minor adaptations for style preservation) ---
def translate_docx_in_memory(file_stream, target_lang, model_name, detected_lang):
    try:
        file_stream.seek(0)
        doc = Document(file_stream)
        # Translate paragraphs
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                translated = translate_text_util(paragraph.text, target_lang, model_name, detected_lang)
                original_runs = list(paragraph.runs)
                paragraph.clear()
                if translated.strip():
                    new_run = paragraph.add_run(translated)
                    if original_runs: # Attempt to copy basic style from first original run
                        try:
                            if original_runs[0].font.name: new_run.font.name = original_runs[0].font.name
                            if original_runs[0].font.size: new_run.font.size = original_runs[0].font.size
                            new_run.bold = original_runs[0].bold
                            new_run.italic = original_runs[0].italic
                            new_run.underline = original_runs[0].underline
                        except Exception: pass # Ignore style copy errors silently
        # Translate table cells
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        if paragraph.text.strip():
                            translated = translate_text_util(paragraph.text, target_lang, model_name, detected_lang)
                            original_runs = list(paragraph.runs)
                            paragraph.clear()
                            if translated.strip():
                                new_run = paragraph.add_run(translated)
                                if original_runs:
                                    try:
                                        if original_runs[0].font.name: new_run.font.name = original_runs[0].font.name
                                        if original_runs[0].font.size: new_run.font.size = original_runs[0].font.size
                                        new_run.bold = original_runs[0].bold
                                        new_run.italic = original_runs[0].italic
                                        new_run.underline = original_runs[0].underline
                                    except Exception: pass
        output = io.BytesIO()
        doc.save(output)
        output.seek(0)
        return output
    except Exception as e:
        print(f"Error translating DOCX: {e}")
        flash(f"Error during DOCX translation process: {e}", "error")
        return None

def translate_pptx_in_memory(file_stream, target_lang, model_name, detected_lang):
    try:
        file_stream.seek(0)
        ppt = Presentation(file_stream)
        for slide in ppt.slides:
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for paragraph in shape.text_frame.paragraphs:
                        if paragraph.text.strip():
                            translated = translate_text_util(paragraph.text, target_lang, model_name, detected_lang)
                            if translated is not None and translated.strip():
                                paragraph.clear()
                                new_run = paragraph.add_run()
                                new_run.text = translated
                if shape.has_table:
                    for row in shape.table.rows:
                        for cell in row.cells:
                            if cell.text_frame:
                                for paragraph in cell.text_frame.paragraphs:
                                    if paragraph.text.strip():
                                        translated = translate_text_util(paragraph.text, target_lang, model_name, detected_lang)
                                        if translated is not None and translated.strip():
                                            paragraph.clear()
                                            new_run = paragraph.add_run()
                                            new_run.text = translated
                if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
                    for subshape in shape.shapes:
                        if subshape.has_text_frame:
                             for paragraph in subshape.text_frame.paragraphs:
                                if paragraph.text.strip():
                                    translated = translate_text_util(paragraph.text, target_lang, model_name, detected_lang)
                                    if translated is not None and translated.strip():
                                        paragraph.clear()
                                        new_run = paragraph.add_run()
                                        new_run.text = translated
        output = io.BytesIO()
        ppt.save(output)
        output.seek(0)
        return output
    except Exception as e:
        print(f"Error translating PPTX: {e}")
        flash(f"Error during PPTX translation process: {e}", "error")
        return None

def translate_excel_in_memory(file_stream, target_lang, model_name, detected_lang):
    try:
        file_stream.seek(0)
        excel_file = pd.ExcelFile(file_stream)
        sheet_names = excel_file.sheet_names
        translated_sheets = {}

        for sheet_name in sheet_names:
            df = excel_file.parse(sheet_name)
            translated_df = df.applymap(lambda x:
                translate_text_util(str(x).strip(), target_lang, model_name, detected_lang)
                if pd.notna(x) and isinstance(x, str) and str(x).strip() not in [None, ""]
                else x
            )
            translated_sheets[sheet_name] = translated_df
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            for sheet_name, data_frame in translated_sheets.items():
                data_frame.to_excel(writer, sheet_name=sheet_name, index=False)
        output.seek(0)
        return output
    except Exception as e:
        print(f"Error translating Excel: {e}")
        flash(f"Error during Excel translation process: {e}", "error")
        return None

# --- Routes for Translation Feature ---
def define_translation_routes(app_shell):

    @app_shell.route("/process/translation/translate_document", methods=["POST"])
    def process_translate_document():
        g.request_id = uuid.uuid4().hex 
        gcs_temp_paths_to_clean = []

        gcs_available = current_app.config.get('GCS_AVAILABLE', False)
        gemini_configured = current_app.config.get('GEMINI_CONFIGURED', False)
        gcs_bucket = current_app.gcs_bucket
        gemini_model_name = current_app.config.get('GEMINI_MODEL_NAME')
        
        render_context = {
            "languages": current_app.config.get('TRANSLATION_LANGUAGES', []),
            "gcs_available": gcs_available,
            "gemini_configured": gemini_configured,
            "file_id": None
        }

        if not gcs_available:
            flash("Google Cloud Storage is not available. Cannot process files.", "error")
            return render_template("translation/templates/translation_content.html", **render_context)
        if not gemini_configured or not gemini_model_name:
            flash("Google Gemini AI is not configured or model name is missing. Cannot translate.", "error")
            return render_template("translation/templates/translation_content.html", **render_context)

        file = request.files.get("file")
        target_lang = request.form.get("target_language")

        if not file or file.filename == "":
            flash("No file selected.", "error")
            return render_template("translation/templates/translation_content.html", **render_context)
        if not target_lang:
            flash("No target language selected.", "error")
            return render_template("translation/templates/translation_content.html", **render_context)

        safe_filename = secure_filename(file.filename)
        file_extension = os.path.splitext(safe_filename)[1].lower()
        if file_extension not in [".docx", ".pptx", ".xlsx"]:
            flash("Unsupported file type. Only .docx, .pptx, .xlsx are supported.", "error")
            return render_template("translation/templates/translation_content.html", **render_context)

        upload_gcs_path = f"translation_feature/uploads/{g.request_id}/{safe_filename}"
        translated_gcs_path = f"translation_feature/results/{g.request_id}/translated_{safe_filename}"

        try:
            print(f"[{g.request_id}] Uploading {safe_filename} to gs://{gcs_bucket.name}/{upload_gcs_path}")
            upload_blob = gcs_bucket.blob(upload_gcs_path)
            file.stream.seek(0)
            upload_blob.upload_from_file(file.stream)
            gcs_temp_paths_to_clean.append(upload_gcs_path)
            print(f"[{g.request_id}] Upload complete for {safe_filename}.")

            print(f"[{g.request_id}] Reading content from GCS for language detection and translation...")
            uploaded_file_stream = blob_to_bytesio(upload_blob)
            if not uploaded_file_stream:
                return render_template("translation/templates/translation_content.html", **render_context)

            file_content_for_detection = ""
            if file_extension == ".docx":
                file_content_for_detection = read_text_from_docx(uploaded_file_stream)
            elif file_extension == ".pptx":
                file_content_for_detection = read_text_from_pptx(uploaded_file_stream)
            elif file_extension == ".xlsx":
                file_content_for_detection = read_text_from_excel(uploaded_file_stream)
            
            if uploaded_file_stream: uploaded_file_stream.seek(0)

            detected_language_code = None
            if file_content_for_detection and file_content_for_detection.strip():
                detected_language_code = detect_language_util(file_content_for_detection)
                if detected_language_code:
                    flash(f"Detected source language: {detected_language_code.upper()}", "info")
                else:
                    flash("Could not confidently detect source language. Proceeding with translation.", "warning")
            else:
                flash("No text extracted for language detection or file is empty. Proceeding with translation attempt.", "warning")
            
            print(f"[{g.request_id}] Translating content to {target_lang}...")
            translated_file_stream = None

            if file_extension == ".docx":
                translated_file_stream = translate_docx_in_memory(uploaded_file_stream, target_lang, gemini_model_name, detected_language_code)
            elif file_extension == ".pptx":
                translated_file_stream = translate_pptx_in_memory(uploaded_file_stream, target_lang, gemini_model_name, detected_language_code)
            elif file_extension == ".xlsx":
                translated_file_stream = translate_excel_in_memory(uploaded_file_stream, target_lang, gemini_model_name, detected_language_code)

            if translated_file_stream:
                print(f"[{g.request_id}] Uploading translated file to gs://{gcs_bucket.name}/{translated_gcs_path}")
                translated_blob = gcs_bucket.blob(translated_gcs_path)
                translated_file_stream.seek(0)
                translated_blob.upload_from_file(translated_file_stream)
                print(f"[{g.request_id}] Upload complete for translated file.")
                
                session_file_id = str(uuid.uuid4())
                session[session_file_id] = {
                    'gcs_path': translated_gcs_path,
                    'filename': f"translated_{safe_filename}"
                }
                render_context["file_id"] = session_file_id
                flash("Translation process completed successfully. Click the link below to download.", "success")
            else:
                # Check if a more specific error was already flashed by translation/reading functions
                # get_flashed_messages consumes messages, so this check is tricky here.
                # Relying on translation functions to flash specific errors.
                # If no specific error, and stream is None, it's a general failure.
                if not get_flashed_messages(category_filter=["error"]): # Check if an error was already flashed
                    flash("Translation failed. Could not generate translated file.", "error")
            
            return render_template("translation/templates/translation_content.html", **render_context)

        except Exception as e:
            print(f"[{g.request_id}] Critical error during translation processing: {e}")
            flash(f"An unexpected critical error occurred: {str(e)}", "error")
            import traceback
            traceback.print_exc()
            return render_template("translation/templates/translation_content.html", **render_context)
        finally:
            if gcs_bucket and gcs_temp_paths_to_clean:
                print(f"[{g.request_id}] Cleaning up temporary GCS objects: {gcs_temp_paths_to_clean}")
                try:
                    blobs_to_delete_objects = [gcs_bucket.blob(path) for path in gcs_temp_paths_to_clean]
                    def on_delete_error(blob_with_error): print(f"Failed to delete blob {blob_with_error.name} during cleanup.")
                    gcs_bucket.delete_blobs(blobs=blobs_to_delete_objects, on_error=on_delete_error)
                    print(f"[{g.request_id}] Cleanup of uploaded original files successful.")
                except Exception as e_cleanup:
                    print(f"[{g.request_id}] GCS Cleanup error for uploaded original files: {e_cleanup}")

    @app_shell.route("/process/translation/download/<file_id>")
    def download_translated_file(file_id):
        gcs_available = current_app.config.get('GCS_AVAILABLE', False)
        gcs_bucket = current_app.gcs_bucket

        if not gcs_available or not gcs_bucket:
            flash("Google Cloud Storage is not available. Cannot download file.", "error")
            return redirect(url_for('index', feature_key='translation')) 

        file_info = session.get(file_id)
        if not file_info or 'gcs_path' not in file_info or 'filename' not in file_info:
            flash("File not found or download link expired/invalid.", "error")
            return redirect(url_for('index', feature_key='translation'))

        gcs_path = file_info['gcs_path']
        filename_for_download = file_info['filename']
        
        request_id_dl = uuid.uuid4().hex
        print(f"[{request_id_dl}] Attempting to download gs://{gcs_bucket.name}/{gcs_path} as {filename_for_download}")

        try:
            translated_blob = gcs_bucket.blob(gcs_path)
            if not translated_blob.exists():
                print(f"[{request_id_dl}] Error: Blob not found at gs://{gcs_bucket.name}/{gcs_path}")
                flash("Error: Translated file no longer found (it may have expired).", "error")
                session.pop(file_id, None)
                return redirect(url_for('index', feature_key='translation'))

            output_stream = io.BytesIO()
            translated_blob.download_to_file(output_stream)
            output_stream.seek(0)
            
            print(f"[{request_id_dl}] Successfully downloaded from GCS. Serving file {filename_for_download}.")
            # session.pop(file_id, None) # Optional: make download link one-time by popping session here

            return send_file(
                output_stream,
                as_attachment=True,
                download_name=filename_for_download,
                mimetype='application/octet-stream' 
            )
        except NotFound:
            print(f"[{request_id_dl}] Error: Blob not found (NotFound exception) at gs://{gcs_bucket.name}/{gcs_path}")
            flash("Error: Translated file not found (it may have expired).", "error")
            session.pop(file_id, None)
            return redirect(url_for('index', feature_key='translation'))
        except Exception as e:
            print(f"[{request_id_dl}] Error serving file from GCS {gcs_path}: {e}")
            flash(f"An error occurred while serving the translated file: {str(e)}", "error")
            session.pop(file_id, None)
            import traceback
            traceback.print_exc()
            return redirect(url_for('index', feature_key='translation'))