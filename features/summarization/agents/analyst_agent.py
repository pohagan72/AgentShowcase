# features/summarization/agents/analyst_agent.py
import json
import logging
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from ..prompts import analyst_prompts

def classify_document(text_content, model, filename=""):
    """
    Determines the document type using a lightweight LLM call.
    Uses specific heuristics defined in analyst_prompts.
    """
    try:
        # Extract a snippet to save tokens, classification rarely needs the whole doc
        excerpt = text_content[:30000]
        
        # Build metadata dict for context
        metadata = {"filename": filename} if filename else None
        
        # UPDATED: Pass metadata to the prompt builder
        prompt = analyst_prompts.get_classification_prompt(excerpt, metadata=metadata)
        
        # We use a non-streaming call for classification as it's short and blocking
        response = model.generate_content(prompt)
        
        if response and response.text:
            # UPDATED: Pass metadata to parser for heuristic overrides (e.g. filename checks)
            return analyst_prompts.parse_classification_response(
                response.text, 
                source_identifier=filename, 
                metadata=metadata
            )
            
    except Exception as e:
        logging.warning(f"Classification failed: {e}. Defaulting to General.")
        
    return "General Business Document"

def stream_analysis(text_content, model_name, filename=""):
    """
    Main generator function for the Analyst Agent.
    
    Yields JSON strings (NDJSON format) to be consumed by the frontend:
    1. Metadata (Role/Classification)
    2. Content Chunks (Thinking tags + Markdown report)
    3. Error messages (if any)
    """
    try:
        if not text_content:
            raise ValueError("No text content provided for analysis.")

        model = genai.GenerativeModel(model_name)
        
        # --- Step 1: Classification & Mandate Selection ---
        # We do this first so the UI can update the "Role" badge immediately.
        doc_classification = classify_document(text_content, model, filename)
        mandate = analyst_prompts.get_mandate(doc_classification)
        
        # Yield Metadata to Frontend
        # This triggers the UI to update the "Agent Persona" badge
        yield json.dumps({
            "type": "meta",
            "classification": doc_classification,
            "role": mandate['role']
        }) + "\n"

        # --- Step 2: Expert Analysis Generation ---
        # Build metadata dict
        metadata = {"filename": filename} if filename else None

        # UPDATED: Pass metadata to the main prompt builder (Thinking Workbench)
        prompt = analyst_prompts.build_analyst_prompt(
            text_content, 
            doc_classification, 
            metadata=metadata
        )
        
        # Stream the response
        response_stream = model.generate_content(prompt, stream=True)
        
        for chunk in response_stream:
            if chunk.text:
                # Yield content chunks to the frontend parser
                yield json.dumps({
                    "type": "chunk", 
                    "content": chunk.text
                }) + "\n"

    except google_exceptions.GoogleAPICallError as e:
        logging.error(f"Gemini API Error in Analyst Agent: {e}")
        yield json.dumps({
            "type": "error", 
            "content": "AI Service Error: The model is currently overloaded or unavailable. Please try again."
        }) + "\n"
        
    except ValueError as e:
        logging.error(f"Input Error in Analyst Agent: {e}")
        yield json.dumps({
            "type": "error", 
            "content": str(e)
        }) + "\n"

    except Exception as e:
        logging.error(f"Unexpected Error in Analyst Agent: {e}", exc_info=True)
        yield json.dumps({
            "type": "error", 
            "content": f"An unexpected error occurred: {str(e)}"
        }) + "\n"