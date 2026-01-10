# features/summarization/ppt_builder_logic/core_processor.py
import logging
import re
from google.api_core import exceptions as google_exceptions
from . import prompts

def parse_llm_output(llm_text):
    """Parses the structured text output from LLM into a list of slide dictionaries."""
    slides = []
    if not llm_text or not llm_text.strip():
        logging.warning("LLM response was empty.")
        return slides

    llm_text_clean = llm_text.strip()
    if "### SLIDES START" in llm_text_clean:
        parts = llm_text_clean.split("### SLIDES START")
        if len(parts) > 1: llm_text_clean = parts[1].strip()
    
    if llm_text_clean.startswith('---'):
        llm_text_clean = re.sub(r'^\s*---\s*\n?', '', llm_text_clean, count=1)

    slide_blocks = re.split(r'\n\s*---\s*\n', llm_text_clean)
    logging.info(f"Found {len(slide_blocks)} potential slide blocks.")

    # Define fields
    core_required = {'title', 'content_type', 'key_message'}
    suggestion_fields = {'elaboration', 'enhancement_suggestion', 'best_practice_tip'}
    # Updated optional fields to map visual -> insight
    optional_fields = {'strategic_takeaway', 'visual', 'design_note', 'notes', 'bullets'}
    all_expected = core_required.union(suggestion_fields).union(optional_fields) - {'bullets'} 
    default_suggestion = "N/A"

    prefixes = {
        'slide title:': 'title', 'content type:': 'content_type', 'key message:': 'key_message',
        'strategic takeaway:': 'strategic_takeaway', # New key
        'visual suggestion:': 'strategic_takeaway',  # Backwards compat (map visual to insight)
        'design note:': 'design_note', 'notes:': 'notes', 'speaker notes:': 'notes',
        'elaboration:': 'elaboration', 'enhancement suggestion:': 'enhancement_suggestion',
        'best practice tip:': 'best_practice_tip'
    }
    lower_prefixes = {k.lower(): v for k, v in prefixes.items()}
    prefix_keys = list(lower_prefixes.keys())

    for block_idx, block in enumerate(slide_blocks):
        block = block.strip()
        if not block: continue

        current_slide = {field: '' for field in all_expected}
        current_slide['bullets'] = []
        current_key = None
        found_prefix = False
        buffer = []

        for line in block.split('\n'):
            line_strip = line.strip()
            line_lower = line_strip.lower()
            matched_key = None

            for prefix_lower in prefix_keys:
                if line_lower.startswith(prefix_lower):
                    matched_key = lower_prefixes[prefix_lower]
                    break

            if matched_key:
                found_prefix = True
                if current_key and current_key != 'bullets':
                    current_slide[current_key] = "\n".join(buffer).strip()
                current_key = matched_key
                prefix_orig = list(prefixes.keys())[prefix_keys.index(prefix_lower)]
                content = line_strip[len(prefix_orig):].strip()
                buffer = [content] if content else []
            elif line_strip.startswith(('- ', '* ')):
                if current_key and current_key != 'bullets':
                    current_slide[current_key] = "\n".join(buffer).strip()
                    buffer = []
                current_key = 'bullets'
                bullet = line_strip[2:].strip()
                if bullet: current_slide['bullets'].append(bullet)
            elif current_key and current_key != 'bullets':
                 if line_strip: buffer.append(line_strip)

        if current_key and current_key != 'bullets':
            current_slide[current_key] = "\n".join(buffer).strip()

        missing_core = [f for f in core_required if not current_slide.get(f, '').strip()]
        if found_prefix and not missing_core:
            for f in suggestion_fields:
                if not current_slide.get(f, '').strip(): current_slide[f] = default_suggestion
            slides.append(current_slide)
        else:
            logging.warning(f"Skipping Block {block_idx+1}. Missing: {missing_core}")

    return slides

def generate_slides_from_text(text, source_identifier, call_llm_func, translate_func, language, audience, tone, template_name, truncated, is_multi_doc=False, total_docs=1):
    slides = []
    cls = "Other"
    if not text or not text.strip(): return "ERROR: Input text content is empty."

    try:
        excerpt = text[:100000]
        c_prompt = prompts.get_classification_prompt(excerpt)
        c_resp = call_llm_func(c_prompt, max_output_tokens=100)
        if c_resp: cls = prompts.parse_classification_response(c_resp, source_identifier)

        prompt = prompts.build_generation_prompt(
            text, cls, source_identifier,
            is_multi_doc, total_docs, truncated, template_name, audience, tone
        )

        response = call_llm_func(prompt)
        slides = parse_llm_output(response) 
        
        if slides and language and language.lower() != 'english':
            try: slides = translate_func(slides, language, call_llm_func)
            except: pass

        return slides
    except Exception as e:
         logging.error(f"Error: {e}", exc_info=True)
         return f"ERROR: {str(e)}"