# features/pii_redaction/routes.py
from flask import (
    Blueprint, render_template, request, flash, current_app, url_for, g, redirect, send_file, session
)
import os
import io
import uuid
from werkzeug.utils import secure_filename
from docx import Document
from docx.shared import RGBColor
from docx.enum.text import WD_COLOR_INDEX
from pptx import Presentation
from pptx.dml.color import RGBColor as PptxRGBColor
from pptx.util import Pt
from pptx.enum.dml import MSO_COLOR_TYPE
import logging

# Define the Blueprint
bp = Blueprint('pii_redaction', __name__)

def allowed_file_pii(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config.get('PII_ALLOWED_EXTENSIONS', {'docx', 'pptx'})

def redact_word_document_pii(file_stream, analyzer):
    try:
        document = Document(file_stream)
        redacted_runs_count = 0
        logging.info(f"[{g.request_id if hasattr(g, 'request_id') else 'PII_REDACT'}] Starting Word document redaction.")

        for para_idx, para in enumerate(document.paragraphs):
            if not para.text.strip(): continue
            try:
                analyzer_results = analyzer.analyze(text=para.text, language='en')
            except Exception as e:
                logging.error(f"[{g.request_id if hasattr(g, 'request_id') else 'PII_REDACT'}] Error analyzing paragraph text (Para {para_idx}): {para.text[:50]}... Error: {e}")
                continue

            current_offset = 0
            run_idx_doc = 0 
            runs = para.runs
            redaction_ranges = sorted([(res.start, res.end) for res in analyzer_results])
            range_idx_doc = 0 

            while run_idx_doc < len(runs) and range_idx_doc < len(redaction_ranges):
                run = runs[run_idx_doc]
                run_len = len(run.text)
                run_start = current_offset
                run_end = current_offset + run_len
                if run_len == 0: 
                    run_idx_doc += 1
                    continue

                redact_start, redact_end = redaction_ranges[range_idx_doc]
                overlap_start = max(run_start, redact_start)
                overlap_end = min(run_end, redact_end)

                if overlap_start < overlap_end:
                    run.font.highlight_color = WD_COLOR_INDEX.BLACK
                    run.font.color.rgb = RGBColor(0, 0, 0)
                    redacted_runs_count += 1
                    if redact_end <= run_end:
                        range_idx_doc += 1
                
                current_offset += run_len 
                run_idx_doc += 1 

        for table_idx, table in enumerate(document.tables):
            for row_idx, row in enumerate(table.rows):
                for cell_idx, cell in enumerate(row.cells):
                    for para_idx_cell, para in enumerate(cell.paragraphs):
                        if not para.text.strip(): continue
                        try:
                            analyzer_results = analyzer.analyze(text=para.text, language='en')
                        except Exception as e:
                            logging.error(f"[{g.request_id if hasattr(g, 'request_id') else 'PII_REDACT'}] Error analyzing table cell (T{table_idx}R{row_idx}C{cell_idx}P{para_idx_cell}): {para.text[:50]}... Error: {e}")
                            continue
                        
                        current_offset = 0
                        run_idx_cell = 0 
                        runs = para.runs
                        redaction_ranges = sorted([(res.start, res.end) for res in analyzer_results])
                        range_idx_cell = 0

                        while run_idx_cell < len(runs) and range_idx_cell < len(redaction_ranges):
                            run = runs[run_idx_cell]
                            run_len = len(run.text)
                            run_start = current_offset
                            run_end = current_offset + run_len
                            if run_len == 0:
                                run_idx_cell += 1
                                continue

                            redact_start, redact_end = redaction_ranges[range_idx_cell]
                            overlap_start = max(run_start, redact_start)
                            overlap_end = min(run_end, redact_end)

                            if overlap_start < overlap_end:
                                run.font.highlight_color = WD_COLOR_INDEX.BLACK
                                run.font.color.rgb = RGBColor(0, 0, 0)
                                redacted_runs_count += 1
                                if redact_end <= run_end:
                                    range_idx_cell += 1
                            
                            current_offset += run_len
                            run_idx_cell += 1
        
        logging.info(f"[{g.request_id if hasattr(g, 'request_id') else 'PII_REDACT'}] Attempted to redact {redacted_runs_count} runs in Word document.")
        output_stream = io.BytesIO()
        document.save(output_stream)
        output_stream.seek(0)
        return output_stream
    except Exception as e:
        logging.error(f"[{g.request_id if hasattr(g, 'request_id') else 'PII_REDACT'}] Error processing Word document for PII: {e}", exc_info=True)
        return None


def redact_powerpoint_document_pii(file_stream, analyzer):
    try:
        presentation = Presentation(file_stream)
        redacted_runs_count = 0
        req_id_tag = g.request_id if hasattr(g, 'request_id') else 'PII_REDACT_PPTX'
        logging.info(f"[{req_id_tag}] Starting PowerPoint document redaction.")

        for i, slide in enumerate(presentation.slides):
            for shape_idx, shape in enumerate(slide.shapes):
                if not shape.has_text_frame:
                    continue
                text_frame = shape.text_frame
                for para_idx, para in enumerate(text_frame.paragraphs):
                    if not para.text.strip(): continue
                    try:
                        analyzer_results = analyzer.analyze(text=para.text, language='en')
                    except Exception as e:
                        logging.error(f"[{req_id_tag}] Error analyzing PPTX paragraph (S{i} Sh{shape_idx} P{para_idx}): {para.text[:50]}... Error: {e}")
                        continue

                    current_offset = 0
                    run_idx_ppt = 0 
                    runs = para.runs
                    redaction_ranges = sorted([(res.start, res.end) for res in analyzer_results])
                    range_idx_ppt = 0 
                    
                    while run_idx_ppt < len(runs) and range_idx_ppt < len(redaction_ranges):
                        run = runs[run_idx_ppt]
                        if not hasattr(run, 'text') or run.text is None:
                            run_idx_ppt += 1
                            continue
                        
                        run_len = len(run.text)
                        run_start = current_offset
                        run_end = current_offset + run_len
                        if run_len == 0:
                            run_idx_ppt += 1
                            continue

                        redact_start, redact_end = redaction_ranges[range_idx_ppt]
                        overlap_start = max(run_start, redact_start)
                        overlap_end = min(run_end, redact_end)

                        if overlap_start < overlap_end:
                            original_text_run = run.text
                            redaction_char = '█'
                            
                            font_color_obj = run.font.color
                            if font_color_obj.type == MSO_COLOR_TYPE.RGB:
                                pass 
                            
                            original_font_size = run.font.size
                            
                            run.text = redaction_char * len(original_text_run)
                            
                            run.font.color.rgb = PptxRGBColor(0,0,0)
                            if original_font_size:
                                run.font.size = original_font_size
                            elif para.font.size:
                                run.font.size = para.font.size
                            else:
                                run.font.size = Pt(11)

                            logging.debug(f"  - Redacted PPTX run (S{i} Sh{shape_idx} P{para_idx} R{run_idx_ppt}): '{original_text_run[:20]}...'")
                            redacted_runs_count += 1
                            if redact_end <= run_end:
                                range_idx_ppt += 1
                        
                        current_offset += run_len
                        run_idx_ppt += 1
        
        logging.info(f"[{req_id_tag}] Attempted to redact {redacted_runs_count} runs in PowerPoint document.")
        output_stream = io.BytesIO()
        presentation.save(output_stream)
        output_stream.seek(0)
        return output_stream
    except Exception as e:
        logging.error(f"[{req_id_tag}] Error processing PowerPoint document for PII: {e}", exc_info=True)
        return None

@bp.route("/process/pii_redaction/redact", methods=["POST"])
def process_redact():
    g.request_id = uuid.uuid4().hex
    logging.info(f"Processing PII redaction request {g.request_id}...")

    context = {
        "redacted_file_url": None,
        "original_filename": None,
        "presidio_available": current_app.config.get('PRESIDIO_ANALYZER_AVAILABLE', False),
        "gcs_available": current_app.config.get('GCS_AVAILABLE', False),
        "hx_target_is_result": True
    }

    if not context["presidio_available"]:
        flash("PII Redaction service (Presidio Analyzer) is not available.", "error")
        logging.error(f"[{g.request_id}] Presidio Analyzer not available.")
        return render_template("pii_redaction/templates/pii_redaction_content.html", **context)

    if not context["gcs_available"]:
        flash("Cloud Storage is not available. Cannot store redacted file.", "error")
        logging.error(f"[{g.request_id}] GCS not available for PII redaction output.")
        return render_template("pii_redaction/templates/pii_redaction_content.html", **context)

    if 'file_to_redact' not in request.files:
        flash('No file part selected for redaction.', 'error')
        return render_template("pii_redaction/templates/pii_redaction_content.html", **context)

    file = request.files['file_to_redact']
    if file.filename == '':
        flash('No file selected for redaction.', 'error')
        return render_template("pii_redaction/templates/pii_redaction_content.html", **context)

    if file and allowed_file_pii(file.filename):
        original_filename = secure_filename(file.filename)
        context["original_filename"] = original_filename
        file_ext = original_filename.rsplit('.', 1)[1].lower()
        
        logging.info(f"[{g.request_id}] File received: {original_filename} (Type: {file_ext})")

        file_stream = io.BytesIO(file.read())
        output_stream = None
        
        analyzer = current_app.presidio_analyzer
        gcs_bucket = current_app.gcs_bucket

        try:
            if file_ext == 'docx':
                output_stream = redact_word_document_pii(file_stream, analyzer)
            elif file_ext == 'pptx':
                output_stream = redact_powerpoint_document_pii(file_stream, analyzer)
            
            if output_stream:
                redacted_gcs_path = f"pii_redaction_results/{g.request_id}/redacted_{original_filename}"
                redacted_blob = gcs_bucket.blob(redacted_gcs_path)
                
                output_stream.seek(0)
                redacted_blob.upload_from_file(output_stream)
                logging.info(f"[{g.request_id}] Redacted file '{original_filename}' uploaded to GCS: gs://{gcs_bucket.name}/{redacted_gcs_path}")

                session_file_id = f"redacted_gcs_{g.request_id}"
                session[session_file_id] = {
                    'gcs_path': redacted_gcs_path,
                    'filename': f"redacted_{original_filename}",
                    'mimetype': f'application/vnd.openxmlformats-officedocument.{"wordprocessingml.document" if file_ext == "docx" else "presentationml.presentation"}'
                }
                context["redacted_file_url"] = url_for('pii_redaction.download_redacted_file_pii', file_id=session_file_id)
                flash(f"Document '{original_filename}' processed for PII redaction. Click link to download.", "success")
            else:
                flash(f"PII redaction process failed for '{original_filename}'. Output stream was empty. Check logs.", "error")
                logging.error(f"[{g.request_id}] Redaction output_stream was None for {original_filename}.")

        except Exception as e:
            flash(f'An error occurred during PII redaction of "{original_filename}": {str(e)}', "error")
            logging.error(f"[{g.request_id}] Error during PII redaction route for '{original_filename}': {e}", exc_info=True)
        finally:
            file_stream.close()
            if output_stream:
                output_stream.close()
    else:
        flash('Invalid file type for PII redaction. Please upload .docx or .pptx files.', 'error')
        logging.warning(f"[{g.request_id}] Invalid file type: {file.filename if file else 'No file'}")

    return render_template("pii_redaction/templates/pii_redaction_content.html", **context)

@bp.route("/process/pii_redaction/download/<file_id>")
def download_redacted_file_pii(file_id):
    gcs_bucket = current_app.gcs_bucket
    if not current_app.config.get('GCS_AVAILABLE') or not gcs_bucket:
        flash("Cloud Storage is not available for download.", "error")
        return redirect(url_for('main.index', feature_key='pii_redaction'))

    file_info = session.get(file_id)
    
    if not file_info or 'gcs_path' not in file_info:
        flash("Redacted file information not found or link expired.", "error")
        session.pop(file_id, None)
        return redirect(url_for('main.index', feature_key='pii_redaction'))

    gcs_path = file_info['gcs_path']
    filename_for_download = file_info.get('filename', 'redacted_file')
    mimetype = file_info.get('mimetype', 'application/octet-stream')

    try:
        logging.info(f"Attempting to download redacted file from GCS: gs://{gcs_bucket.name}/{gcs_path}")
        blob = gcs_bucket.blob(gcs_path)
        
        if not blob.exists():
            logging.error(f"Blob not found at GCS path: {gcs_path}")
            flash("Error: Redacted file no longer found in cloud storage (it may have expired).", "error")
            session.pop(file_id, None)
            return redirect(url_for('main.index', feature_key='pii_redaction'))

        output_stream = io.BytesIO()
        blob.download_to_file(output_stream)
        output_stream.seek(0)
        
        logging.info(f"Successfully downloaded '{filename_for_download}' from GCS for serving.")
        
        session.pop(file_id, None) 

        return send_file(
            output_stream,
            as_attachment=True,
            download_name=filename_for_download,
            mimetype=mimetype
        )
    except Exception:
        logging.error(f"GCSNotFound: Blob not found at GCS path: {gcs_path} during download attempt.")
        flash("Error: Redacted file not found in cloud storage during download attempt.", "error")
        session.pop(file_id, None)
        return redirect(url_for('main.index', feature_key='pii_redaction'))
    except Exception as e:
        logging.error(f"Error serving redacted file from GCS '{gcs_path}': {e}", exc_info=True)
        flash(f"An error occurred while trying to serve the redacted file: {str(e)}", "error")
        session.pop(file_id, None)
        return redirect(url_for('main.index', feature_key='pii_redaction'))