# features/multimedia/routes.py
import os
import io
import uuid
import time
import logging
from flask import (
    Blueprint, render_template, request, flash, current_app, url_for, g, jsonify, send_file, after_this_request
)
from werkzeug.utils import secure_filename
from google.cloud import storage
from google.cloud.exceptions import NotFound as GCSNotFound

from .blur_utils import allowed_file, blur_image_opencv 

# --- UPDATED GCS PATHS ---
MULTIMEDIA_BLUR_UPLOAD_FOLDER_PREFIX = "multimedia_feature/blurring/uploads/"
MULTIMEDIA_BLUR_RESULTS_FOLDER_PREFIX = "multimedia_feature/blurring/results/"
DEFAULT_BLUR_STRENGTH = 65 

def define_multimedia_routes(app_shell): # RENAMED
    
    @app_shell.route('/process/multimedia/blur/process_image', methods=['POST']) # RENAMED ROUTE
    def process_multimedia_blur_image_route(): # RENAMED FUNCTION
        g.request_id = uuid.uuid4().hex
        req_start_time = time.time()
        log_extra = {'extra_data': {'request_id': g.request_id, 'feature': 'multimedia-blur'}} # UPDATED
        
        if not hasattr(g, 'gcs_urgent_temp_paths_to_clean'):
            g.gcs_urgent_temp_paths_to_clean = []

        @after_this_request
        def cleanup_gcs_uploads(response):
            if hasattr(g, 'gcs_urgent_temp_paths_to_clean') and g.gcs_urgent_temp_paths_to_clean:
                if current_app.gcs_bucket:
                    try:
                        blobs_to_delete = [current_app.gcs_bucket.blob(path) for path in g.gcs_urgent_temp_paths_to_clean]
                        existing_blobs_to_delete = [b for b in blobs_to_delete if b.exists()]
                        if existing_blobs_to_delete:
                            current_app.gcs_bucket.delete_blobs(blobs=existing_blobs_to_delete, on_error=lambda blob: logging.error(f"[{g.request_id}] Failed to delete GCS blob {blob.name} during urgent cleanup.", extra=log_extra))
                        logging.info(f"[{g.request_id}] Cleaned up URGENT temporary GCS uploads for multimedia-blur: {g.gcs_urgent_temp_paths_to_clean}", extra=log_extra)
                    except Exception as e_clean:
                        logging.error(f"[{g.request_id}] GCS URGENT cleanup error for multimedia-blur uploads: {e_clean}", exc_info=True, extra=log_extra)
            return response

        if not current_app.config.get('GCS_AVAILABLE'):
            logging.error(f"[{g.request_id}] GCS not available for multimedia-blur feature.", extra=log_extra)
            return render_template("multimedia/templates/_blurring_error_partial.html", error_message="Cloud Storage service is unavailable. Cannot process image.")

        if 'file' not in request.files:
            logging.warning(f"[{g.request_id}] No file part in request for multimedia-blur.", extra=log_extra)
            return render_template("multimedia/templates/_blurring_error_partial.html", error_message="No file part in the request.")

        file = request.files['file']
        if file.filename == '':
            logging.warning(f"[{g.request_id}] No file selected for multimedia-blur.", extra=log_extra)
            return render_template("multimedia/templates/_blurring_error_partial.html", error_message="No file selected for upload.")

        if not file or not allowed_file(file.filename):
            logging.warning(f"[{g.request_id}] Invalid file type for multimedia-blur: {file.filename}", extra=log_extra)
            return render_template("multimedia/templates/_blurring_error_partial.html", error_message="Invalid file type. Please upload a JPG, PNG, or WEBP image.")

        try:
            blur_selection = int(request.form.get('blur_strength', '2')) 
        except ValueError:
            blur_selection = 2
        blur_strength_map = {1: 99, 2: DEFAULT_BLUR_STRENGTH, 3: 35} 
        blur_size = blur_strength_map.get(blur_selection, DEFAULT_BLUR_STRENGTH)

        original_filename = secure_filename(file.filename)
        file_root, file_ext = os.path.splitext(original_filename)
        
        gcs_original_upload_path = f"{MULTIMEDIA_BLUR_UPLOAD_FOLDER_PREFIX}{g.request_id}/{original_filename}"
        
        blurred_filename_gcs = f"{file_root}-blurred{file_ext if file_ext else '.png'}" 
        gcs_blurred_output_path = f"{MULTIMEDIA_BLUR_RESULTS_FOLDER_PREFIX}{g.request_id}/{blurred_filename_gcs}"

        try:
            original_blob = current_app.gcs_bucket.blob(gcs_original_upload_path)
            file.seek(0) 
            original_blob.upload_from_file(file.stream, content_type=file.content_type)
            logging.info(f"[{g.request_id}] Original image '{original_filename}' uploaded to {gcs_original_upload_path}", extra=log_extra)

            image_bytes = original_blob.download_as_bytes()
            processing_start_time = time.time()
            blurred_image_bytes = blur_image_opencv(image_bytes, blur_size)
            processing_duration = time.time() - processing_start_time

            if blurred_image_bytes is None:
                logging.error(f"[{g.request_id}] Face blurring process failed for '{original_filename}'.", extra=log_extra)
                return render_template("multimedia/templates/_blurring_error_partial.html", error_message="Image processing failed during blurring.")

            blurred_blob = current_app.gcs_bucket.blob(gcs_blurred_output_path)
            blurred_content_type = f'image/{file_ext[1:] if file_ext else "png"}'
            blurred_blob.upload_from_string(blurred_image_bytes, content_type=blurred_content_type)
            logging.info(f"[{g.request_id}] Blurred image '{blurred_filename_gcs}' uploaded to {gcs_blurred_output_path}", extra=log_extra)

            original_image_url = url_for('serve_multimedia_blur_image', type='original', r_id=g.request_id, filename=original_filename)
            blurred_image_url = url_for('serve_multimedia_blur_image', type='blurred', r_id=g.request_id, filename=blurred_filename_gcs)
            
            total_duration = time.time() - req_start_time
            logging.info(f"[{g.request_id}] Blurring complete for '{original_filename}'. Processing: {processing_duration:.2f}s, Total: {total_duration:.2f}s", extra=log_extra)
            
            return render_template("multimedia/templates/_blurring_results_partial.html",
                                   original_image_url=original_image_url,
                                   blurred_image_url=blurred_image_url,
                                   processing_time=processing_duration,
                                   message="Image processed successfully.")

        except Exception as e:
            logging.error(f"[{g.request_id}] Error during blurring process for {original_filename}: {e}", exc_info=True, extra=log_extra)
            return render_template("multimedia/templates/_blurring_error_partial.html", error_message=f'An unexpected error occurred: {str(e)}')

    @app_shell.route('/serve/multimedia/blur_image/<type>/<r_id>/<path:filename>') # RENAMED ROUTE
    def serve_multimedia_blur_image(type, r_id, filename): # RENAMED FUNCTION
        log_extra = {'extra_data': {'request_id': r_id, 'feature': 'multimedia_serve', 'type': type, 'filename': filename}}
        if not current_app.config.get('GCS_AVAILABLE'):
            logging.error(f"GCS not available attempt to serve image.", extra=log_extra)
            return "Cloud Storage not available", 503

        if type == 'original':
            gcs_path = f"{MULTIMEDIA_BLUR_UPLOAD_FOLDER_PREFIX}{r_id}/{filename}"
        elif type == 'blurred':
            gcs_path = f"{MULTIMEDIA_BLUR_RESULTS_FOLDER_PREFIX}{r_id}/{filename}"
        else:
            logging.warning(f"Invalid image type requested: {type}", extra=log_extra)
            return "Invalid image type", 404
        
        try:
            blob = current_app.gcs_bucket.blob(gcs_path)
            if not blob.exists():
                logging.warning(f"Image not found in GCS: {gcs_path}", extra=log_extra)
                return "Image not found", 404
            
            image_data = io.BytesIO(blob.download_as_bytes())
            image_data.seek(0)
            
            mimetype = 'image/jpeg' 
            lowered_filename = filename.lower()
            if lowered_filename.endswith('.png'):
                mimetype = 'image/png'
            elif lowered_filename.endswith('.webp'):
                mimetype = 'image/webp'
            
            logging.info(f"Serving image from GCS: {gcs_path}", extra=log_extra)
            return send_file(image_data, mimetype=mimetype)
            
        except GCSNotFound:
            logging.warning(f"GCSNotFound for image: {gcs_path}", extra=log_extra)
            return "Image not found (GCS Error)", 404
        except Exception as e:
            logging.error(f"Error serving image {gcs_path} from GCS: {e}", exc_info=True, extra=log_extra)
            return "Error serving image", 500