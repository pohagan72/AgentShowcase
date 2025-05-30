# features/summarization/ppt_builder_logic/file_processor.py
import os
import logging
from io import BytesIO
# import codecs # Not used in the provided snippet
from docx import Document as DocxDocument # Assuming this is python-docx
import fitz # PyMuPDF

# This import should be relative since prompts.py is in the same directory
from .prompts import MAX_INPUT_CHARS

# Configuration specific to file processing
# This can serve as a default if not overridden by app.config via the routes
DEFAULT_ALLOWED_EXTENSIONS_PPT = {'docx', 'pdf', 'py'}
MAX_FILES = 10 # Max number of files allowed in a single upload (can be overridden by app.config)
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024 # 10 MB (can be overridden by app.config)

def allowed_file(filename, allowed_extensions_set=None): # MODIFIED: Added allowed_extensions_set
    """Checks if the filename has an allowed extension."""
    if allowed_extensions_set is None:
        logging.warning(f"allowed_file in file_processor.py called without allowed_extensions_set, using internal default: {DEFAULT_ALLOWED_EXTENSIONS_PPT}")
        current_allowed_extensions = DEFAULT_ALLOWED_EXTENSIONS_PPT
    else:
        current_allowed_extensions = allowed_extensions_set
        
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_allowed_extensions

# --- Text Extraction Helpers ---
def extract_text_from_docx(file_stream):
    try:
        file_stream.seek(0)
        doc = DocxDocument(file_stream)
        full_text = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
        return '\n'.join(full_text)
    except Exception as e:
        logging.error(f"Error extracting text from DOCX stream: {e}", exc_info=False)
        raise ValueError("Could not process DOCX file content.") from e

def extract_text_from_pdf_primary(file_stream):
    full_text = []
    doc = None
    try:
        file_stream.seek(0)
        pdf_data = file_stream.read()
        doc = fitz.open(stream=pdf_data, filetype="pdf")
        if not doc.page_count:
            logging.warning("PDF has no pages.")
            return ""
        for page_num in range(doc.page_count):
            try:
                page = doc.load_page(page_num)
                text = page.get_text("text")
                if text and text.strip():
                    full_text.append(text.strip())
            except Exception as page_e:
                logging.warning(f"Error processing PDF page {page_num + 1}: {page_e}")
                continue
        return '\n'.join(full_text)
    except Exception as e:
        logging.error(f"Error reading PDF stream with PyMuPDF: {e}", exc_info=False)
        raise ValueError("Primary PDF processing failed (PyMuPDF).") from e
    finally:
        if doc:
            try: doc.close()
            except Exception: pass

def extract_text_from_blob(blob, filename):
    file_ext = os.path.splitext(filename)[1].lower()
    logging.info(f"Extracting content from GCS blob '{blob.name}' ({file_ext})...")
    extracted_text = ""
    file_stream = None
    was_truncated = False

    try:
        content_bytes = blob.download_as_bytes()
        file_stream = BytesIO(content_bytes) # Use BytesIO for all types

        if file_ext == '.docx':
            extracted_text = extract_text_from_docx(file_stream)
        elif file_ext == '.pdf':
            extracted_text = extract_text_from_pdf_primary(file_stream)
        elif file_ext == '.py':
            logging.debug(f"Reading Python file '{filename}' as text.")
            try:
                extracted_text = content_bytes.decode('utf-8')
            except UnicodeDecodeError:
                logging.warning(f"UTF-8 decode failed for '{filename}'. Trying latin-1.")
                try: extracted_text = content_bytes.decode('latin-1')
                except Exception as decode_err:
                    logging.error(f"Failed decode for '{filename}' even with fallback: {decode_err}")
                    extracted_text = ""
        else:
            logging.warning(f"Attempting to extract unsupported file type '{file_ext}'. Skipping.")
            extracted_text = ""

        if extracted_text:
            original_length = len(extracted_text)
            if original_length > MAX_INPUT_CHARS: # Using MAX_INPUT_CHARS from .prompts
                extracted_text = extracted_text[:MAX_INPUT_CHARS]
                was_truncated = True
                logging.warning(f"Text from '{filename}' ({original_length:,} chars) truncated (>{MAX_INPUT_CHARS:,}).")
            logging.info(f"Extracted text for {filename} (Len: {len(extracted_text):,} chars, Trunc: {was_truncated})")
        else:
             # Use DEFAULT_ALLOWED_EXTENSIONS_PPT for this check if file_processor's own list is desired
             # Or, better, ensure ppt_allowed_file was called before this with the correct set
             if file_ext.replace('.', '') in DEFAULT_ALLOWED_EXTENSIONS_PPT: 
                 logging.warning(f"Failed text extraction or empty content for {filename} (type: {file_ext}).")

        return extracted_text if extracted_text else "", was_truncated

    except ValueError as ve:
         logging.error(f"Extraction error for blob '{blob.name}': {ve}")
         raise
    except Exception as e:
        logging.error(f"Fatal error processing blob '{blob.name}': {e}", exc_info=True)
        raise IOError(f"Could not read or process file blob '{filename}'.") from e
    finally:
        if file_stream:
            try: file_stream.close()
            except Exception: pass