# translate.py
import logging
import json # For potentially more complex batching later

# Fields within a slide dictionary that typically contain user-facing text to be translated
TRANSLATABLE_FIELDS = [
    'title',
    'key_message',
    # 'bullets' needs special handling as it's a list
    'visual', # Often contains descriptive text
    'design_note', # Can contain suggestions
    'notes', # Speaker notes often need translation
    'elaboration',
    'enhancement_suggestion',
    'best_practice_tip'
]

def build_translation_prompt(text_to_translate, target_language, source_language="English"):
    """Creates a simple prompt for translating a single piece of text."""
    # Basic prompt, assumes source is English but could be parameterized
    prompt = f"""Translate the following text from {source_language} to {target_language}.
Provide *only* the translated text, without any introductory phrases, explanations, or quotation marks.

Text to translate:
\"\"\"
{text_to_translate}
\"\"\"

Translation to {target_language}:"""
    return prompt

def translate_slide_data(slide_data_list, target_language, call_llm_func, source_language="English"):
    """
    Iterates through slide data and translates specified text fields.

    Args:
        slide_data_list: A list of dictionaries, where each dict represents a slide.
        target_language: The language to translate into (e.g., "Spanish").
        call_llm_func: The call_llm function imported from app.py.
        source_language: The source language of the text (defaults to English).

    Returns:
        The list of slide dictionaries with specified fields translated.
        Returns the original list if target_language is the same as source_language or empty.
    """
    if not target_language or target_language.lower() == source_language.lower():
        logging.debug("Target language is same as source or empty, skipping translation.")
        return slide_data_list

    logging.info(f"Starting translation of slide data to {target_language}...")
    translated_slide_data_list = []

    for i, slide in enumerate(slide_data_list):
        translated_slide = slide.copy() # Work on a copy
        logging.debug(f"Translating slide {i+1}...")

        # --- Translate standard string fields ---
        for field in TRANSLATABLE_FIELDS:
            if field in translated_slide and isinstance(translated_slide[field], str) and translated_slide[field].strip():
                original_text = translated_slide[field]
                # Avoid translating placeholders like N/A or suggestion defaults if they haven't changed
                if original_text in ["N/A", "None", "Suggestion not provided by AI."]:
                    logging.debug(f"  Skipping translation for default/placeholder field '{field}'.")
                    continue

                logging.debug(f"  Attempting translation for field '{field}': '{original_text[:100]}...'")
                try:
                    prompt = build_translation_prompt(original_text, target_language, source_language)
                    max_tokens = max(200, len(original_text) * 2) # Simple estimation + buffer
                    translated_text = call_llm_func(prompt, max_output_tokens=max_tokens)

                    if translated_text:
                        translated_text = translated_text.strip() # Strip result
                        logging.debug(f"    LLM returned translation: '{translated_text[:100]}...'")
                        translated_slide[field] = translated_text
                    else:
                        logging.warning(f"    LLM returned EMPTY translation for field '{field}' on slide {i+1}. Keeping original.")
                        # Keep original text (already in translated_slide copy)
                except Exception as e:
                    logging.error(f"    Error translating field '{field}' on slide {i+1}: {e}. Keeping original text.", exc_info=False)
                    # Keep original text

        # --- Translate bullets field ---
        if 'bullets' in translated_slide and isinstance(translated_slide['bullets'], list):
             original_bullets = translated_slide['bullets'] # Keep reference to original
             translated_bullets = []
             logging.debug(f"  Translating {len(original_bullets)} bullets for slide {i+1}...")
             for j, bullet_text in enumerate(original_bullets):
                 if isinstance(bullet_text, str) and bullet_text.strip():
                     logging.debug(f"    Attempting translation for bullet {j+1}: '{bullet_text}'")
                     try:
                         prompt = build_translation_prompt(bullet_text, target_language, source_language)
                         max_tokens = max(150, len(bullet_text) * 2) # Small buffer for translation
                         translated_bullet = call_llm_func(prompt, max_output_tokens=max_tokens)

                         if translated_bullet:
                             translated_bullet = translated_bullet.strip() # Strip result
                             logging.debug(f"      LLM returned translation: '{translated_bullet}'")
                             translated_bullets.append(translated_bullet)
                         else:
                             logging.warning(f"      LLM returned EMPTY translation for bullet {j+1} ('{bullet_text}'). Keeping original.")
                             translated_bullets.append(bullet_text) # Keep original
                     except Exception as e:
                         logging.error(f"      Error translating bullet {j+1} ('{bullet_text}'): {e}. Keeping original.", exc_info=False)
                         translated_bullets.append(bullet_text) # Keep original on error
                 else:
                     logging.debug(f"    Skipping non-string or empty bullet {j+1}.")
                     translated_bullets.append(bullet_text) # Keep non-strings or empty strings as is

             # Ensure the assignment happens correctly
             translated_slide['bullets'] = translated_bullets
             logging.debug(f"  Finished translating bullets for slide {i+1}. Resulting list length: {len(translated_bullets)}")

        translated_slide_data_list.append(translated_slide)

    logging.info(f"Finished translation process to {target_language}.")
    return translated_slide_data_list