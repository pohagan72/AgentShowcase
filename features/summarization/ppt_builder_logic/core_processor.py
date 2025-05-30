# core_processor.py
import logging
import re

# Import prompts module for its functions and constants
from . import prompts
# Import translate module but expect the function to be passed in
from . import translate

# Import exceptions used by call_llm if needed for specific handling
from google.api_core import exceptions as google_exceptions

# --- Parsing Function (Moved from app.py) ---
def parse_llm_output(llm_text):
    """Parses the structured text output from LLM into a list of slide dictionaries."""
    slides = []
    if not llm_text or not llm_text.strip():
        # Return empty list instead of raising error immediately,
        # allows caller to decide how to handle empty LLM response.
        logging.warning("LLM response was empty or whitespace during parsing.")
        return slides
        # raise ValueError("AI response empty.") # Old behavior

    llm_text_clean = llm_text.strip()
    # Remove leading '---' if present
    if llm_text_clean.startswith('---'):
        llm_text_clean = re.sub(r'^\s*---\s*\n?', '', llm_text_clean, count=1)

    # Split slides based on '---' separator
    slide_blocks = re.split(r'\n\s*---\s*\n', llm_text_clean)
    logging.info(f"Found {len(slide_blocks)} potential slide blocks.")

    # Define expected fields
    core_required = {'title', 'content_type', 'key_message'}
    suggestion_fields = {'elaboration', 'enhancement_suggestion', 'best_practice_tip'}
    optional_fields = {'visual', 'design_note', 'notes', 'bullets'}
    all_expected = core_required.union(suggestion_fields).union(optional_fields) - {'bullets'} # Exclude list field from init dict
    default_suggestion = "Suggestion not provided by AI."

    # Define prefixes for parsing lines
    prefixes = {
        'slide title:': 'title', 'content type:': 'content_type', 'key message:': 'key_message',
        'visual suggestion:': 'visual', 'design note:': 'design_note', 'notes:': 'notes',
        'elaboration:': 'elaboration', 'enhancement suggestion:': 'enhancement_suggestion',
        'best practice tip:': 'best_practice_tip'
    }
    lower_prefixes = {k.lower(): v for k, v in prefixes.items()}
    prefix_keys = list(lower_prefixes.keys())

    for block_idx, block in enumerate(slide_blocks):
        block = block.strip()
        if not block: continue # Skip empty blocks

        logging.debug(f"Processing Block {block_idx+1}")
        current_slide = {field: '' for field in all_expected} # Initialize fields
        current_slide['bullets'] = [] # Initialize bullets list
        current_key = None
        found_prefix = False
        buffer = []

        for line in block.split('\n'):
            line_strip = line.strip()
            line_lower = line_strip.lower()
            matched_key = None

            # Check if line starts with a known prefix
            for prefix_lower in prefix_keys:
                if line_lower.startswith(prefix_lower):
                    matched_key = lower_prefixes[prefix_lower]
                    break

            if matched_key:
                found_prefix = True
                # Store buffered lines for the previous key
                if current_key and current_key != 'bullets':
                    current_slide[current_key] = "\n".join(buffer).strip()
                # Start buffering for the new key
                current_key = matched_key
                # Find the original prefix case for accurate stripping
                prefix_orig = list(prefixes.keys())[prefix_keys.index(prefix_lower)]
                content = line_strip[len(prefix_orig):].strip()
                buffer = [content] if content else [] # Start new buffer
            elif line_strip.startswith(('- ', '* ')): # Handle bullet points
                # Store buffer for previous non-bullet key
                if current_key and current_key != 'bullets':
                    current_slide[current_key] = "\n".join(buffer).strip()
                    buffer = []
                current_key = 'bullets'
                bullet = line_strip[2:].strip()
                if bullet: current_slide['bullets'].append(bullet)
            elif current_key and current_key != 'bullets': # Continue buffering for current key
                 if line_strip: buffer.append(line_strip)
            # Ignore lines before the first prefix or outside known structures

        # Store buffer for the last key in the block
        if current_key and current_key != 'bullets':
            current_slide[current_key] = "\n".join(buffer).strip()

        # Validate if core fields are present and non-empty
        missing_core = [f for f in core_required if not current_slide.get(f, '').strip()]
        if found_prefix and not missing_core:
            # Add default text for suggestion fields if they are missing/empty
            for f in suggestion_fields:
                if not current_slide.get(f, '').strip():
                     current_slide[f] = default_suggestion
            slides.append(current_slide)
            logging.debug(f"Block {block_idx+1} PASSED validation.")
        else:
            reason = f"Missing/Empty Core: {missing_core}" if missing_core else "No prefix found or invalid structure."
            logging.warning(f"Skipping Block {block_idx+1}. Reason: {reason}. Title='{current_slide.get('title', 'N/A')[:50]}...'")

    if not slides and slide_blocks: # Log if blocks were found but none passed parsing
        logging.error("Parsing failed: Found potential blocks but none yielded valid slides.")
        logging.debug(f"Raw LLM Snippet (first 500 chars):\n{llm_text[:500]}...")
        # Decide if this should raise an error or return empty list
        # Raising error might be better to signal failure clearly
        raise ValueError("AI response parsing failed. No valid slides extracted.")

    logging.info(f"Successfully parsed {len(slides)} slides.")
    return slides

# --- Core Slide Generation Orchestrator ---
def generate_slides_from_text(
    text: str,
    source_identifier: str,
    call_llm_func, # Pass the call_llm function from app.py
    translate_func, # Pass the translate_slide_data function from translate.py
    language: str,
    audience: str,
    tone: str,
    template_name: str,
    truncated: bool,
    is_multi_doc: bool = False, # Added flag for context
    total_docs: int = 1
    ):
    """
    Orchestrates classification, summarization, parsing, and translation.

    Args:
        text (str): The extracted text content.
        source_identifier (str): Filename or URL.
        call_llm_func (function): Function to call the LLM.
        translate_func (function): Function to translate slide data.
        language (str): Target language for translation (empty string for none).
        audience (str): Target audience.
        tone (str): Desired tone.
        template_name (str): Selected template name.
        truncated (bool): Whether the input text was truncated.
        is_multi_doc (bool): Whether this is part of a multi-document request.
        total_docs (int): Total number of documents in the request.


    Returns:
        list: A list of slide dictionaries if successful.
        str: An error message string (starting with "ERROR:") if failed.
    """
    slides = []
    cls = "Other" # Default classification

    if not text or not text.strip():
        logging.warning(f"Skipping processing for '{source_identifier}': Input text is empty.")
        return "ERROR: Input text content is empty."

    try:
        # 1. Dynamic Classification
        try:
            max_excerpt_len = 100000 # Match prompts.py
            excerpt = text[:max_excerpt_len]
            classification_prompt = prompts.get_classification_prompt(excerpt)
            logging.info(f"Calling LLM for classification of '{source_identifier}'...")
            # Use fewer tokens for classification response
            classification_response = call_llm_func(classification_prompt, max_output_tokens=100)
            if classification_response:
                cls = prompts.parse_classification_response(classification_response)
                logging.info(f"Dynamically classified '{source_identifier}' as: '{cls}'")
            else:
                cls = "Web Page Content" if source_identifier.startswith(('http://', 'https://')) else "General Document"
                logging.warning(f"Classification LLM returned empty for '{source_identifier}'. Using default '{cls}'.")
        except Exception as class_e:
            cls = "Web Page Content" if source_identifier.startswith(('http://', 'https://')) else "General Document"
            logging.error(f"Classification failed for '{source_identifier}': {class_e}. Using default '{cls}'.", exc_info=False)

        # 2. Build Summarization Prompt
        prompt = prompts.build_generation_prompt(
            document_text=text, classification=cls, filename=source_identifier,
            is_part_of_multi_doc_request=is_multi_doc, # Use passed flag
            total_docs_in_request=total_docs,         # Use passed count
            truncated=truncated, template_name=template_name,
            audience=audience, tone=tone
        )
        logging.info(f"Building generation prompt for '{source_identifier}' (Class: '{cls}', Truncated: {truncated})")

        # 3. Call LLM for Summarization
        logging.info(f"Calling LLM for summary of '{source_identifier}'...")
        # Use default (large) token limit for summary generation
        response = call_llm_func(prompt)

        # 4. Parse LLM Output
        slides = parse_llm_output(response) # This might raise ValueError
        logging.info(f"Generated {len(slides)} summary slides for '{source_identifier}'.")

        # 5. Translate (Optional)
        if slides and language and language.lower() != 'english':
            logging.info(f"Translating '{source_identifier}' to {language}...")
            try:
                slides = translate_func(slides, language, call_llm_func) # Pass call_llm again
                logging.info(f"Translated '{source_identifier}'.")
            except Exception as trans_e:
                # Log translation error but don't fail the whole process, return untranslated slides
                logging.error(f"Translate failed for '{source_identifier}': {trans_e}", exc_info=True)

        # If all steps succeeded, return the slides list
        return slides

    # Catch specific errors from the core process
    except (ValueError, IOError, google_exceptions.GoogleAPICallError) as e:
         err_msg = f"ERROR: AI Processing failed for '{source_identifier}': {str(e)}"
         logging.error(f"{err_msg}", exc_info=False)
         return err_msg # Return error string
    except Exception as e:
         # Catch any other unexpected errors during this core processing
         err_msg = f"ERROR: Unexpected failure during AI processing for '{source_identifier}': {str(e)}"
         logging.error(f"{err_msg}", exc_info=True)
         return err_msg # Return error string