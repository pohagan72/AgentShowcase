# features/blurring/routes.py
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

BLURRING_UPLOAD_FOLDER_PREFIX = "blurring_feature/uploads/"
BLURRING_RESULTS_FOLDER_PREFIX = "blurring_feature/results/"
DEFAULT_BLUR_STRENGTH = 65 

def define_blurring_routes(app_shell):
    
    @app_shell.route('/process/blurring/process_image', methods=['POST'])
    def process_blur_image_route():
        g.request_id = uuid.uuid4().hex
        req_start_time = time.time()
        log_extra = {'extra_data': {'request_id': g.request_id, 'feature': 'blurring'}}
        
        # Initialize the list for paths that DO need immediate cleanup (if any in the future)
        # For now, we are deciding NOT to immediately clean up the uploaded original.
        if not hasattr(g, 'gcs_urgent_temp_paths_to_clean'):
            g.gcs_urgent_temp_paths_to_clean = []

        @after_this_request
        def cleanup_gcs_uploads(response):
            # This function will now only clean up paths explicitly added to 'gcs_urgent_temp_paths_to_clean'
            if hasattr(g, 'gcs_urgent_temp_paths_to_clean') and g.gcs_urgent_temp_paths_to_clean:
                if current_app.gcs_bucket:
                    try:
                        blobs_to_delete = [current_app.gcs_bucket.blob(path) for path in g.gcs_urgent_temp_paths_to_clean]
                        existing_blobs_to_delete = [b for b in blobs_to_delete if b.exists()]
                        if existing_blobs_to_delete:
                            current_app.gcs_bucket.delete_blobs(blobs=existing_blobs_to_delete, on_error=lambda blob: logging.error(f"[{g.request_id}] Failed to delete GCS blob {blob.name} during urgent cleanup.", extra=log_extra))
                        logging.info(f"[{g.request_id}] Cleaned up URGENT temporary GCS uploads for blurring: {g.gcs_urgent_temp_paths_to_clean}", extra=log_extra)
                    except Exception as e_clean:
                        logging.error(f"[{g.request_id}] GCS URGENT cleanup error for blurring uploads: {e_clean}", exc_info=True, extra=log_extra)
            return response

        # ... (GCS_AVAILABLE, file checks remain the same) ...
        if not current_app.config.get('GCS_AVAILABLE'):
            logging.error(f"[{g.request_id}] GCS not available for blurring feature.", extra=log_extra)
            return render_template("blurring/templates/_blurring_error_partial.html", error_message="Cloud Storage service is unavailable. Cannot process image.")

        if 'file' not in request.files:
            logging.warning(f"[{g.request_id}] No file part in request for blurring.", extra=log_extra)
            return render_template("blurring/templates/_blurring_error_partial.html", error_message="No file part in the request.")

        file = request.files['file']
        if file.filename == '':
            logging.warning(f"[{g.request_id}] No file selected for blurring.", extra=log_extra)
            return render_template("blurring/templates/_blurring_error_partial.html", error_message="No file selected for upload.")

        if not file or not allowed_file(file.filename):
            logging.warning(f"[{g.request_id}] Invalid file type for blurring: {file.filename}", extra=log_extra)
            return render_template("blurring/templates/_blurring_error_partial.html", error_message="Invalid file type. Please upload a JPG, PNG, or WEBP image.")

        try:
            blur_selection = int(request.form.get('blur_strength', '2')) 
        except ValueError:
            blur_selection = 2
        # FIX: This mapping is reversed to match the new UI.
        # Top of slider ("Light") is max value (3), which now maps to the smallest blur size.
        # Bottom of slider ("Heavy") is min value (1), which now maps to the largest blur size.
        blur_strength_map = {1: 99, 2: DEFAULT_BLUR_STRENGTH, 3: 35} 
        blur_size = blur_strength_map.get(blur_selection, DEFAULT_BLUR_STRENGTH)

        original_filename = secure_filename(file.filename)
        file_root, file_ext = os.path.splitext(original_filename)
        
        gcs_original_upload_path = f"{BLURRING_UPLOAD_FOLDER_PREFIX}{g.request_id}/{original_filename}"
        
        # Using the simplified blurred filename from our previous successful step
        blurred_filename_gcs = f"{file_root}-blurred{file_ext if file_ext else '.png'}" 
        gcs_blurred_output_path = f"{BLURRING_RESULTS_FOLDER_PREFIX}{g.request_id}/{blurred_filename_gcs}"

        try:
            original_blob = current_app.gcs_bucket.blob(gcs_original_upload_path)
            file.seek(0) 
            original_blob.upload_from_file(file.stream, content_type=file.content_type)
            # DO NOT ADD original_blob.name (gcs_original_upload_path) to an immediate cleanup list
            # We will rely on GCS Lifecycle rules to clean this up later.
            logging.info(f"[{g.request_id}] Original image '{original_filename}' uploaded to {gcs_original_upload_path}", extra=log_extra)

            image_bytes = original_blob.download_as_bytes()
            processing_start_time = time.time()
            blurred_image_bytes = blur_image_opencv(image_bytes, blur_size)
            processing_duration = time.time() - processing_start_time

            if blurred_image_bytes is None:
                logging.error(f"[{g.request_id}] Face blurring process failed for '{original_filename}'.", extra=log_extra)
                # If original upload was successful but blurring failed, we might still want to clean up the original
                # g.gcs_urgent_temp_paths_to_clean.append(gcs_original_upload_path) # Consider this if blurring fails often
                return render_template("blurring/templates/_blurring_error_partial.html", error_message="Image processing failed during blurring.")

            blurred_blob = current_app.gcs_bucket.blob(gcs_blurred_output_path)
            blurred_content_type = f'image/{file_ext[1:] if file_ext else "png"}'
            blurred_blob.upload_from_string(blurred_image_bytes, content_type=blurred_content_type)
            # Blurred images are also not added to gcs_urgent_temp_paths_to_clean, rely on GCS Lifecycle.
            logging.info(f"[{g.request_id}] Blurred image '{blurred_filename_gcs}' uploaded to {gcs_blurred_output_path}", extra=log_extra)

            original_image_url = url_for('serve_blurring_image', type='original', r_id=g.request_id, filename=original_filename)
            blurred_image_url = url_for('serve_blurring_image', type='blurred', r_id=g.request_id, filename=blurred_filename_gcs)
            
            total_duration = time.time() - req_start_time
            logging.info(f"[{g.request_id}] Blurring complete for '{original_filename}'. Processing: {processing_duration:.2f}s, Total: {total_duration:.2f}s", extra=log_extra)
            
            return render_template("blurring/templates/_blurring_results_partial.html",
                                   original_image_url=original_image_url,
                                   blurred_image_url=blurred_image_url,
                                   processing_time=processing_duration,
                                   message="Image processed successfully.")

        except Exception as e:
            logging.error(f"[{g.request_id}] Error during blurring process for {original_filename}: {e}", exc_info=True, extra=log_extra)
            # If an error occurs after uploading the original, we might want to clean it up if it's in an inconsistent state.
            # However, for simplicity, we'll rely on GCS lifecycle for now.
            return render_template("blurring/templates/_blurring_error_partial.html", error_message=f'An unexpected error occurred: {str(e)}')

    # ... (serve_blurring_image route remains the same) ...
    @app_shell.route('/serve/blurring_image/<type>/<r_id>/<path:filename>')
    def serve_blurring_image(type, r_id, filename):
        log_extra = {'extra_data': {'request_id': r_id, 'feature': 'blurring_serve', 'type': type, 'filename': filename}}
        if not current_app.config.get('GCS_AVAILABLE'):
            logging.error(f"GCS not available attempt to serve image.", extra=log_extra)
            return "Cloud Storage not available", 503

        if type == 'original':
            gcs_path = f"{BLURRING_UPLOAD_FOLDER_PREFIX}{r_id}/{filename}"
        elif type == 'blurred':
            gcs_path = f"{BLURRING_RESULTS_FOLDER_PREFIX}{r_id}/{filename}"
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