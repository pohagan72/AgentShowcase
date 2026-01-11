# features/summarization/agents/designer_agent.py
import json
import re
import os
import logging
import google.generativeai as genai
from flask import current_app, url_for

# Import the prompt definitions for the designer
from ..prompts import designer_prompts

# Import from the renderer
from ..ppt_renderer import create_presentation 

# --- HELPER FUNCTIONS (Defined first or at bottom, used in parser) ---

def validate_slide_structure(slide_data):
    """
    Validates that a parsed slide contains all required fields.
    """
    required_fields = ['title', 'key_message', 'bullets']
    
    # Check required fields exist and have content
    for field in required_fields:
        if not slide_data.get(field):
            return False
    
    # Title must be reasonable length (not empty, not too long)
    if len(slide_data['title']) < 5 or len(slide_data['title']) > 200:
        return False
    
    # Must have at least 2 bullets
    if len(slide_data['bullets']) < 2:
        return False
    
    return True

def get_fallback_slide_structure(text_chunk, slide_number):
    """
    Creates a basic slide structure when parsing fails completely.
    """
    # Split text into sentences and use first few as bullets
    sentences = [s.strip() for s in text_chunk.split('.') if s.strip()]
    
    return {
        'title': f'Key Points - Section {slide_number}',
        'key_message': sentences[0] if sentences else 'Analysis of source document',
        'strategic_takeaway': 'See detailed analysis in speaker notes',
        'notes': text_chunk[:500],  # Truncate for safety
        'bullets': sentences[1:6] if len(sentences) > 1 else ['Content analysis in progress']
    }

def extract_slide_confidence_score(slide_data):
    """
    Calculates a quality/completeness score for a parsed slide.
    """
    score = 0.0
    
    # Title quality
    if slide_data.get('title'):
        score += 0.2 if len(slide_data['title']) > 20 else 0.1
    
    # Key message
    if slide_data.get('key_message'):
        score += 0.2 if len(slide_data['key_message']) > 30 else 0.1
    
    # Strategic takeaway
    if slide_data.get('strategic_takeaway'):
        score += 0.2 if len(slide_data['strategic_takeaway']) > 20 else 0.1
    
    # Bullets quality
    bullets = slide_data.get('bullets', [])
    if len(bullets) >= 3:
        score += 0.2
        # Bonus for having good bullet length
        avg_bullet_length = sum(len(b) for b in bullets) / len(bullets)
        if avg_bullet_length > 30:
            score += 0.1
    elif len(bullets) >= 1:
        score += 0.1
    
    # Speaker notes
    if slide_data.get('notes') and len(slide_data['notes']) > 20:
        score += 0.1
    
    return min(score, 1.0)


def _split_into_slide_blocks(text):
    """
    Attempts to split text into slide blocks using multiple separator strategies.
    """
    # Strategy 1: Try the standard "---" separator
    blocks = re.split(r'\n\s*---\s*\n', text)
    if len(blocks) >= 2:
        logging.info(f"Split into {len(blocks)} blocks using '---' separator")
        return blocks
    
    # Strategy 2: Try alternative separators (***,  ___, ===)
    for separator in [r'\*\*\*', r'___', r'===']:
        blocks = re.split(rf'\n\s*{separator}\s*\n', text)
        if len(blocks) >= 2:
            logging.info(f"Split into {len(blocks)} blocks using '{separator}' separator")
            return blocks
    
    # Strategy 3: Split by "Slide Title:" occurrences
    blocks = re.split(r'(?=(?:Slide\s+)?Title:)', text, flags=re.IGNORECASE)
    blocks = [b.strip() for b in blocks if b.strip()]
    if len(blocks) >= 2:
        logging.info(f"Split into {len(blocks)} blocks by detecting 'Title:' headers")
        return blocks
    
    # Strategy 4: Give up and return as single block
    logging.warning("Could not detect slide separators, treating as single block")
    return [text] if text.strip() else []


def _flush_buffer_to_slide(slide_data, section, buffer):
    """
    Appends buffered multi-line content to the appropriate slide field.
    """
    if not buffer:
        return
    
    content = " ".join(buffer).strip()
    
    field_map = {
        'title': 'title',
        'key_message': 'key_message',
        'strategic_takeaway': 'strategic_takeaway',
        'speaker_notes': 'notes'
    }
    
    slide_key = field_map.get(section)
    if slide_key:
        if slide_data[slide_key]:
            slide_data[slide_key] += f" {content}"
        else:
            slide_data[slide_key] = content


def parse_slides_from_llm_output(llm_text):
    """
    Parses the structured text output from the LLM into a list of slide dictionaries.
    Robustly handles Markdown code blocks, multiple separator formats, and validation.
    """
    slides = []
    if not llm_text:
        logging.error("parse_slides_from_llm_output received empty text")
        return slides

    # 1. Clean the text
    clean_text = llm_text.strip()
    clean_text = re.sub(r'^```[a-zA-Z]*\s*$', '', clean_text, flags=re.MULTILINE)
    clean_text = clean_text.replace('```', '')
    
    # 2. Try multiple separator strategies
    slide_blocks = _split_into_slide_blocks(clean_text)
    
    if not slide_blocks:
        logging.warning("Failed to split text into slides, attempting fallback parsing")
        slide_blocks = [clean_text]
    
    logging.info(f"Detected {len(slide_blocks)} potential slide blocks")

    # 3. Define Regex patterns
    patterns = {
        'title': re.compile(r'(?:Slide\s+)?Title:\s*(.*)', re.IGNORECASE),
        'key_message': re.compile(r'Key\s+Message:\s*(.*)', re.IGNORECASE),
        'strategic_takeaway': re.compile(r'(?:Strategic\s+Takeaway|Visual\s+Suggestion):\s*(.*)', re.IGNORECASE),
        'speaker_notes': re.compile(r'(?:Speaker\s+)?Notes:\s*(.*)', re.IGNORECASE)
    }

    # 4. Process each block
    for block_idx, block in enumerate(slide_blocks):
        if not block.strip():
            continue

        slide_data = {
            'title': f'Slide {block_idx + 1}',
            'key_message': '',
            'strategic_takeaway': '',
            'notes': '',
            'bullets': []
        }

        lines = block.split('\n')
        current_section = None
        temp_buffer = []

        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                continue

            # Check for header fields
            matched_field = False
            for field, pattern in patterns.items():
                match = pattern.match(line_stripped)
                if match:
                    # Flush previous buffer
                    if current_section and temp_buffer:
                        _flush_buffer_to_slide(slide_data, current_section, temp_buffer)
                        temp_buffer = []
                    
                    # Extract new field content
                    content = match.group(1).strip()
                    
                    # Map to slide keys
                    field_map = {
                        'title': 'title',
                        'key_message': 'key_message',
                        'strategic_takeaway': 'strategic_takeaway',
                        'speaker_notes': 'notes'
                    }
                    slide_key = field_map.get(field)
                    if slide_key and content:
                        slide_data[slide_key] = content
                    
                    current_section = field
                    matched_field = True
                    break
            
            if matched_field:
                continue

            # Check for bullet points
            if line_stripped.startswith(('-', '*', '•')):
                if current_section and current_section != 'bullets' and temp_buffer:
                    _flush_buffer_to_slide(slide_data, current_section, temp_buffer)
                    temp_buffer = []
                
                clean_bullet = line_stripped.lstrip('-*• ').strip()
                if clean_bullet:
                    slide_data['bullets'].append(clean_bullet)
                current_section = 'bullets'
            
            elif re.match(r'bullets?:\s*$', line_stripped, re.IGNORECASE):
                if current_section and temp_buffer:
                    _flush_buffer_to_slide(slide_data, current_section, temp_buffer)
                    temp_buffer = []
                current_section = 'bullets'
            
            # Handle continuation lines
            else:
                if current_section == 'bullets':
                    if slide_data['bullets']:
                        slide_data['bullets'][-1] += f" {line_stripped}"
                    else:
                        slide_data['bullets'].append(line_stripped)
                elif current_section:
                    temp_buffer.append(line_stripped)

        # Flush final buffer
        if current_section and temp_buffer:
            _flush_buffer_to_slide(slide_data, current_section, temp_buffer)

        # Validate slide structure (Using local function)
        if validate_slide_structure(slide_data):
            confidence = extract_slide_confidence_score(slide_data)
            logging.info(f"Slide {block_idx + 1} parsed successfully (confidence: {confidence:.2f})")
            slides.append(slide_data)
        else:
            logging.warning(f"Slide {block_idx + 1} failed validation, attempting fallback")
            fallback_slide = get_fallback_slide_structure(block, block_idx + 1)
            slides.append(fallback_slide)

    # Final check
    if not slides:
        logging.error("No valid slides parsed from LLM output, creating emergency fallback")
        slides.append(get_fallback_slide_structure(llm_text[:1000], 1))
    
    return slides


def stream_ppt_generation(text_content, model_name, template, req_id, filename="Presentation", metadata=None):
    """
    Main generator function for the Designer Agent.
    """
    try:
        yield json.dumps({"type": "status", "message": "Designer Agent: Analyzing content structure..."}) + "\n"
        
        model = genai.GenerativeModel(model_name)
        
        # Prepare metadata
        prompt_metadata = metadata or {}
        if filename and 'filename' not in prompt_metadata:
            prompt_metadata['filename'] = filename
        
        # Build prompt
        truncated_text = text_content[:50000]
        prompt = designer_prompts.get_slide_design_prompt(
            truncated_text, 
            template_style=template,
            metadata=prompt_metadata
        )
        
        yield json.dumps({"type": "status", "message": "Designer Agent: Drafting slide layouts..."}) + "\n"
        
        # Generate with streaming
        response_chunks = []
        chunk_count = 0
        
        try:
            response_stream = model.generate_content(prompt, stream=True)
            
            for chunk in response_stream:
                if chunk.text:
                    response_chunks.append(chunk.text)
                    chunk_count += 1
                    
                    # Heartbeat
                    if chunk_count % 5 == 0:
                        yield json.dumps({
                            "type": "heartbeat", 
                            "chunks_received": chunk_count
                        }) + "\n"
            
            full_response = "".join(response_chunks)
            
        except Exception as stream_error:
            logging.error(f"Streaming error during PPT generation: {stream_error}")
            raise ValueError(f"AI generation interrupted: {str(stream_error)}")
        
        if not full_response or not full_response.strip():
            raise ValueError("AI returned empty design content.")

        # Parse
        yield json.dumps({"type": "status", "message": "Parsing slide structure..."}) + "\n"
        
        slides_data = parse_slides_from_llm_output(full_response)
        
        count = len(slides_data)
        if count == 0:
            raise ValueError("Failed to parse valid slides from AI output.")
        
        # Bounds check
        if count < 3:
            yield json.dumps({
                "type": "warning", 
                "message": f"Generated {count} slides instead of expected 5. Proceeding with available content."
            }) + "\n"
        elif count > 7:
            slides_data = slides_data[:7]
            count = 7

        yield json.dumps({"type": "status", "message": f"Generated designs for {count} slides."}) + "\n"

        # Build Binary
        yield json.dumps({"type": "status", "message": "Rendering PowerPoint file..."}) + "\n"
        
        presentation_data = {filename: slides_data}
        
        try:
            pptx_buffer = create_presentation(presentation_data, template_name=template)
        except Exception as render_error:
            logging.error(f"PPT rendering error: {render_error}", exc_info=True)
            raise ValueError(f"Failed to create PowerPoint file: {str(render_error)}")
        
        # Upload
        yield json.dumps({"type": "status", "message": "Uploading to secure storage..."}) + "\n"
        
        safe_name = re.sub(r'[^\w\-]+', '_', os.path.splitext(filename)[0])[:50]
        dl_filename = f"{safe_name}_Deck_{req_id}.pptx"
        gcs_path = f"{req_id}/output/{dl_filename}"
        
        if current_app.config.get('GCS_AVAILABLE') and current_app.gcs_bucket:
            try:
                blob = current_app.gcs_bucket.blob(gcs_path)
                pptx_buffer.seek(0)
                blob.upload_from_file(
                    pptx_buffer, 
                    content_type='application/vnd.openxmlformats-officedocument.presentationml.presentation'
                )
            except Exception as upload_error:
                logging.error(f"GCS upload error: {upload_error}", exc_info=True)
                raise EnvironmentError(f"Failed to upload file to cloud storage: {str(upload_error)}")
        else:
            logging.error("GCS not available for PPT upload")
            raise EnvironmentError("Cloud Storage is not configured.")

        # Success Link
        dl_url = url_for('summarization.download_generated_ppt', file_id=req_id, filename=dl_filename)
        
        avg_confidence = sum(extract_slide_confidence_score(s) for s in slides_data) / len(slides_data) if slides_data else 0.0
        
        success_html = f"""
        <div style="background: #f0fdf4; border: 1px solid #bbf7d0; padding: 2rem; border-radius: 8px; text-align: center; color: #166534; animation: fadeIn 0.5s;">
            <div style="background: #dcfce7; width: 60px; height: 60px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 1rem auto;">
                <i class="fas fa-check" style="font-size: 1.5rem; color: #16a34a;"></i>
            </div>
            <h3 style="margin: 0 0 0.5rem 0; color: #14532d; font-size: 1.25rem;">Presentation Ready</h3>
            <p style="margin-bottom: 1.5rem; color: #166534;">
                Created {count} slides using '{template}' template.
                <span style="font-size: 0.9em; opacity: 0.8;">
                    (Quality score: {avg_confidence:.0%})
                </span>
            </p>
            <a href="{dl_url}" class="submit-button" style="background: #16a34a; border: none; box-shadow: 0 4px 6px -1px rgba(22, 163, 74, 0.4); padding: 0.75rem 1.5rem; color: white; border-radius: 8px; text-decoration: none; display: inline-flex; align-items: center; gap: 0.5rem;">
                <i class="fas fa-download"></i> Download .pptx
            </a>
        </div>
        """
        
        yield json.dumps({"type": "result", "html": success_html}) + "\n"

    except ValueError as ve:
        error_msg = str(ve)
        logging.error(f"Designer Agent ValueError: {error_msg}")
        yield json.dumps({
            "type": "error", 
            "message": error_msg,
            "suggestion": "Try using a different source document or simplifying the content."
        }) + "\n"
        
    except EnvironmentError as ee:
        error_msg = str(ee)
        logging.error(f"Designer Agent EnvironmentError: {error_msg}")
        yield json.dumps({
            "type": "error", 
            "message": error_msg,
            "suggestion": "This is a system configuration issue. Please contact support."
        }) + "\n"
    
    except Exception as e:
        logging.error(f"Designer Agent unexpected error: {e}", exc_info=True)
        yield json.dumps({
            "type": "error", 
            "message": f"An unexpected error occurred: {str(e)}",
            "suggestion": "Please try again. If the problem persists, contact support with your request ID."
        }) + "\n"