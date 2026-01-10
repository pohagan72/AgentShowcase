# features/multimedia/routes.py
import os
import io
import uuid
import time
import logging
import json
import base64
from flask import (
    Blueprint, render_template, request, flash, current_app, url_for, g, jsonify, send_file, after_this_request, session
)
from werkzeug.utils import secure_filename
import google.generativeai as genai
from PIL import Image, ImageOps

from .blur_utils import allowed_file, blur_image_opencv
from .analytics_utils import analyze_image_with_gemini, extract_dominant_colors

# Define the Blueprint
bp = Blueprint('multimedia', __name__)

MULTIMEDIA_BLUR_UPLOAD_FOLDER_PREFIX = "multimedia_feature/blurring/uploads/"
MULTIMEDIA_BLUR_RESULTS_FOLDER_PREFIX = "multimedia_feature/blurring/results/"
TARGET_RESOLUTION = (1920, 1920)

def normalize_and_resize_image(image_bytes: bytes) -> bytes:
    try:
        logging.info(f"Normalizing image for optimal processing...")
        img = Image.open(io.BytesIO(image_bytes))
        img = ImageOps.exif_transpose(img)
        img.thumbnail(TARGET_RESOLUTION, Image.Resampling.LANCZOS)
        output_buffer = io.BytesIO()
        img_format = img.format if img.format in ['JPEG', 'PNG', 'WEBP'] else 'JPEG'
        if img.mode != 'RGB':
            img = img.convert('RGB')
        img.save(output_buffer, format=img_format, quality=85)
        resized_bytes = output_buffer.getvalue()
        logging.info(f"Image normalized from {len(image_bytes) / 1024 / 1024:.2f}MB to {len(resized_bytes) / 1024 / 1024:.2f}MB.")
        return resized_bytes
    except Exception as e:
        logging.error(f"Failed to normalize image: {e}", exc_info=True)
        return image_bytes

@bp.route('/process/multimedia/blur/process_image', methods=['POST'])
def process_multimedia_blur_image_route():
    g.request_id = uuid.uuid4().hex
    req_start_time = time.time()
    log_extra = {'extra_data': {'request_id': g.request_id, 'feature': 'multimedia-blur'}}
    
    # 1. Clean up OLD files from the PREVIOUS request before starting a new one.
    if 'multimedia_temp_files' in session and current_app.gcs_bucket:
        old_paths_to_clean = session.pop('multimedia_temp_files', [])
        if old_paths_to_clean:
            try:
                blobs_to_delete = [current_app.gcs_bucket.blob(path) for path in old_paths_to_clean]
                existing_blobs_to_delete = [b for b in blobs_to_delete if b.exists()]
                if existing_blobs_to_delete:
                    current_app.gcs_bucket.delete_blobs(blobs=existing_blobs_to_delete, on_error=lambda blob: logging.error(f"[{g.request_id}] Failed to delete old GCS blob {blob.name}.", extra=log_extra))
                logging.info(f"[{g.request_id}] Cleaned up old temporary files from session: {old_paths_to_clean}", extra=log_extra)
            except Exception as e_clean:
                logging.error(f"[{g.request_id}] GCS cleanup error for old session files: {e_clean}", exc_info=True, extra=log_extra)
    
    if not current_app.config.get('GCS_AVAILABLE'):
        return render_template("multimedia/templates/_blurring_results_partial.html", error_message="Cloud Storage service is unavailable. Cannot process image.")

    if 'file' not in request.files:
        return render_template("multimedia/templates/_blurring_results_partial.html", error_message="No file part in the request.")

    file = request.files['file']
    if file.filename == '' or not allowed_file(file.filename):
        return render_template("multimedia/templates/_blurring_results_partial.html", error_message="No valid file selected. Please upload a JPG, PNG, or WEBP image.")
    
    try:
        image_bytes_original = file.read()
        resized_image_bytes = normalize_and_resize_image(image_bytes_original)

        blur_selection = int(request.form.get('blur_strength', '2'))
        blur_strength_map = {1: 35, 2: 151, 3: -1} 
        blur_size = blur_strength_map.get(blur_selection, 151)

        original_filename = secure_filename(file.filename)
        file_root, _ = os.path.splitext(original_filename)
        blurred_filename_gcs = f"{file_root}-blurred.png"
        
        gcs_original_upload_path = f"{MULTIMEDIA_BLUR_UPLOAD_FOLDER_PREFIX}{g.request_id}/{original_filename}"
        gcs_blurred_output_path = f"{MULTIMEDIA_BLUR_RESULTS_FOLDER_PREFIX}{g.request_id}/{blurred_filename_gcs}"
        
        # 2. Store the NEW paths for this request in the session.
        session['multimedia_temp_files'] = [gcs_original_upload_path, gcs_blurred_output_path]

        original_blob = current_app.gcs_bucket.blob(gcs_original_upload_path)
        original_blob.upload_from_string(resized_image_bytes, content_type=file.content_type)
        logging.info(f"[{g.request_id}] Original image '{original_filename}' uploaded to {gcs_original_upload_path}", extra=log_extra)

        processing_start_time = time.time()
        blurred_image_bytes = blur_image_opencv(resized_image_bytes, blur_size)
        processing_duration = time.time() - processing_start_time

        if blurred_image_bytes is None:
            return render_template("multimedia/templates/_blurring_results_partial.html", error_message="Image processing failed during blurring.")

        blurred_blob = current_app.gcs_bucket.blob(gcs_blurred_output_path)
        blurred_blob.upload_from_string(blurred_image_bytes, content_type='image/png')
        logging.info(f"[{g.request_id}] Blurred image '{blurred_filename_gcs}' uploaded to {gcs_blurred_output_path}", extra=log_extra)

        original_image_url = url_for('multimedia.serve_multimedia_blur_image', type='original', r_id=g.request_id, filename=original_filename)
        blurred_image_url = url_for('multimedia.serve_multimedia_blur_image', type='blurred', r_id=g.request_id, filename=blurred_filename_gcs)
        
        total_duration = time.time() - req_start_time
        logging.info(f"[{g.request_id}] Blurring complete for '{original_filename}'. Processing: {processing_duration:.2f}s, Total: {total_duration:.2f}s", extra=log_extra)
        
        return render_template("multimedia/templates/_blurring_results_partial.html",
                               original_image_url=original_image_url,
                               blurred_image_url=blurred_image_url,
                               processing_time=processing_duration,
                               message="Image processed successfully.")

    except Exception as e:
        logging.error(f"[{g.request_id}] Error during blurring process for {file.filename}: {e}", exc_info=True, extra=log_extra)
        return render_template("multimedia/templates/_blurring_results_partial.html", error_message=f'An unexpected error occurred: {str(e)}')

@bp.route('/process/multimedia/analytics/analyze_image', methods=['POST'])
def process_multimedia_analyze_image_route():
    g.request_id = uuid.uuid4().hex
    log_extra = {'extra_data': {'request_id': g.request_id, 'feature': 'multimedia-analytics'}}
    if not current_app.config.get('GEMINI_CONFIGURED'):
        return render_template("multimedia/templates/_analytics_results_partial.html", 
                               analysis_results={"error": "AI service is not configured. Cannot analyze image."})
    if 'file' not in request.files:
        return render_template("multimedia/templates/_analytics_results_partial.html",
                               analysis_results={"error": "No file part in the request."})
    file = request.files['file']
    if file.filename == '' or not allowed_file(file.filename):
        return render_template("multimedia/templates/_analytics_results_partial.html",
                               analysis_results={"error": "No valid file selected. Please upload a JPG, PNG, or WEBP image."})
    try:
        image_bytes_original = file.read()
        image_bytes = normalize_and_resize_image(image_bytes_original)
        file_mimetype = file.mimetype
        base64_encoded_data = base64.b64encode(image_bytes).decode('utf-8')
        image_data_url = f"data:{file_mimetype};base64,{base64_encoded_data}"
        model_name = current_app.config.get('GEMINI_MODEL_NAME', 'gemini-1.5-flash-latest')
        gemini_model = genai.GenerativeModel(model_name)
        analysis_results = analyze_image_with_gemini(image_bytes, gemini_model)
        dominant_colors = extract_dominant_colors(image_bytes)
        if analysis_results is None:
             return render_template("multimedia/templates/_analytics_results_partial.html",
                               analysis_results={"error": "Image analysis failed."})
        return render_template("multimedia/templates/_analytics_results_partial.html",
                               analysis_results=analysis_results,
                               dominant_colors=dominant_colors,
                               image_data_url=image_data_url)
    except Exception as e:
        logging.error(f"[{g.request_id}] Error during analytics process for {file.filename}: {e}", exc_info=True, extra=log_extra)
        return render_template("multimedia/templates/_analytics_results_partial.html", 
                               analysis_results={"error": f'An unexpected error occurred: {str(e)}'})

@bp.route('/serve/multimedia/blur_image/<type>/<r_id>/<path:filename>')
def serve_multimedia_blur_image(type, r_id, filename):
    log_extra = {'extra_data': {'request_id': r_id, 'feature': 'multimedia_serve', 'type': type, 'filename': filename}}
    if not current_app.config.get('GCS_AVAILABLE'):
        return "Cloud Storage not available", 503
    if type == 'original':
        gcs_path = f"{MULTIMEDIA_BLUR_UPLOAD_FOLDER_PREFIX}{r_id}/{filename}"
    elif type == 'blurred':
        gcs_path = f"{MULTIMEDIA_BLUR_RESULTS_FOLDER_PREFIX}{r_id}/{filename}"
    else:
        return "Invalid image type", 404
    
    # 3. Security Check: Only serve files that are listed in the current user's session.
    if 'multimedia_temp_files' not in session or gcs_path not in session['multimedia_temp_files']:
        logging.warning(f"Unauthorized access attempt for GCS path: {gcs_path}", extra=log_extra)
        return "Access denied or file has expired.", 403

    try:
        blob = current_app.gcs_bucket.blob(gcs_path)
        if not blob.exists():
            return "Image not found", 404
        
        image_data = io.BytesIO(blob.download_as_bytes())
        image_data.seek(0)
        mimetype = 'image/png' # Since output is now always PNG
        if type == 'original':
            lowered_filename = filename.lower()
            if lowered_filename.endswith('.jpg') or lowered_filename.endswith('.jpeg'):
                mimetype = 'image/jpeg'
            elif lowered_filename.endswith('.webp'):
                mimetype = 'image/webp'

        return send_file(image_data, mimetype=mimetype)
        
    except Exception:
        return "Image not found (GCS Error)", 404
    except Exception as e:
        logging.error(f"Error serving image {gcs_path} from GCS: {e}", exc_info=True, extra=log_extra)
        return "Error serving image", 500