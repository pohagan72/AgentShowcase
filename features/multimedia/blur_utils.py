# features/multimedia/blur_utils.py
import os
import time
import cv2
import numpy as np
from mtcnn import MTCNN # type: ignore
from werkzeug.utils import secure_filename

VALID_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp')

def allowed_file(filename: str) -> bool:
    """Check if the file has one of the valid extensions."""
    return filename.lower().endswith(VALID_EXTENSIONS)

def validate_blur_size(blur_size: int) -> int:
    """Ensures the blur size is at least 1 and odd."""
    blur_size = max(1, blur_size) # Ensure blur_size is at least 1
    # Ensure blur_size is odd for GaussianBlur kernel
    return blur_size if blur_size % 2 == 1 else blur_size + 1 

def blur_image_opencv(image_bytes: bytes, blur_size: int) -> bytes | None:
    """
    Blurs or redacts detected faces in the image using MTCNN and OpenCV.
    If blur_size is -1, it applies an opaque black box (redaction).
    Returns processed image as bytes, or None if an error occurs.
    """
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Could not decode image from bytes.")

        rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        
        detector = MTCNN() # Consider initializing this less frequently if performance is an issue
        faces = detector.detect_faces(rgb_image)
        
        if not faces:
            # Return original image bytes if no faces detected
            is_success, buffer = cv2.imencode('.png', image) # Use PNG for lossless return
            if is_success:
                return buffer.tobytes()
            else:
                raise ValueError("Could not re-encode image (no faces found).")

        height, width = image.shape[:2]
        
        for face in faces:
            x, y, w, h = face.get('box', (0, 0, 0, 0))

            # ======================= MODIFIED SECTION START =======================
            if blur_size == -1:
                # OPAQUE REDACTION: Use less padding for a tighter black box
                padding_w = int(w * 0.10)
                padding_h = int(h * 0.15)
            else:
                # BLURRING: Use more padding for a softer, wider blur effect
                padding_w = int(w * 0.20)
                padding_h = int(h * 0.20)

            x1, y1 = max(0, x - padding_w), max(0, y - padding_h)
            x2, y2 = min(width, x + w + padding_w), min(height, y + h + padding_h)
            
            current_w, current_h = x2 - x1, y2 - y1

            if current_w > 0 and current_h > 0:
                # Check for the special -1 flag to redact instead of blur
                if blur_size == -1:
                    # Draw a filled, black rectangle. Color is (B,G,R). Thickness -1 fills it.
                    cv2.rectangle(image, (x1, y1), (x2, y2), (0, 0, 0), -1)
                else:
                    # If not redacting, proceed with blurring as before
                    face_roi = image[y1:y2, x1:x2]
                    if face_roi.size > 0:
                        validated_blur_size = validate_blur_size(blur_size)
                        blurred_roi = cv2.GaussianBlur(face_roi, (validated_blur_size, validated_blur_size), 0)
                        image[y1:y2, x1:x2] = blurred_roi
            # ======================== MODIFIED SECTION END ========================
        
        is_success, buffer = cv2.imencode('.png', image) # Default to PNG for output consistency
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