# features/multimedia/blur_utils.py
import os
import time
import cv2
import numpy as np
# from mtcnn import MTCNN  <-- REMOVE THIS GLOBAL IMPORT
from werkzeug.utils import secure_filename

VALID_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp')

def allowed_file(filename: str) -> bool:
    """Check if the file has one of the valid extensions."""
    return filename.lower().endswith(VALID_EXTENSIONS)

def validate_blur_size(blur_size: int) -> int:
    """Ensures the blur size is at least 1 and odd."""
    blur_size = max(1, blur_size) 
    return blur_size if blur_size % 2 == 1 else blur_size + 1 

def blur_image_opencv(image_bytes: bytes, blur_size: int) -> bytes | None:
    """
    Blurs or redacts detected faces in the image using MTCNN and OpenCV.
    """
    try:
        # --- NEW: LAZY IMPORT ---
        # Only load TensorFlow/MTCNN when this function is actually called.
        from mtcnn import MTCNN 
        # ------------------------

        nparr = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Could not decode image from bytes.")

        rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        
        detector = MTCNN() # Consider initializing this less frequently if performance is an issue
        faces = detector.detect_faces(rgb_image)
        
        if not faces:
            # Return original image bytes if no faces detected
            is_success, buffer = cv2.imencode('.png', image) 
            if is_success:
                return buffer.tobytes()
            else:
                raise ValueError("Could not re-encode image (no faces found).")

        height, width = image.shape[:2]
        
        for face in faces:
            x, y, w, h = face.get('box', (0, 0, 0, 0))

            if blur_size == -1:
                # OPAQUE REDACTION
                padding_w = int(w * 0.10)
                padding_h = int(h * 0.15)
            else:
                # BLURRING
                padding_w = int(w * 0.20)
                padding_h = int(h * 0.20)

            x1, y1 = max(0, x - padding_w), max(0, y - padding_h)
            x2, y2 = min(width, x + w + padding_w), min(height, y + h + padding_h)
            
            current_w, current_h = x2 - x1, y2 - y1

            if current_w > 0 and current_h > 0:
                if blur_size == -1:
                    cv2.rectangle(image, (x1, y1), (x2, y2), (0, 0, 0), -1)
                else:
                    face_roi = image[y1:y2, x1:x2]
                    if face_roi.size > 0:
                        validated_blur_size = validate_blur_size(blur_size)
                        blurred_roi = cv2.GaussianBlur(face_roi, (validated_blur_size, validated_blur_size), 0)
                        image[y1:y2, x1:x2] = blurred_roi
        
        is_success, buffer = cv2.imencode('.png', image)
        if is_success:
            return buffer.tobytes()
        else:
            raise ValueError("Could not encode processed image to PNG.")

    except cv2.error as cv_err:
        print(f"OpenCV error while processing image: {cv_err}")
        return None 
    except Exception as e:
        print(f"Unexpected error during face blurring/redaction: {e}")
        import traceback
        traceback.print_exc()
        return None