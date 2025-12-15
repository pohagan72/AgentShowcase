# features/multimedia/analytics_utils.py
import google.generativeai as genai
import json
import logging
from PIL import Image
import io

def build_analytics_prompt():
    """
    Creates a robust, structured prompt for the Gemini vision model.
    """
    return """
    You are a strict, literal-minded content safety analyst. Your task is to analyze the attached image and provide a factual, evidence-based analysis based ONLY on the visual information present. Do not make inferences, assumptions, or judgments based on historical, cultural, or symbolic context.

    Respond ONLY with a single, valid JSON object. Do not include markdown backticks (```json) or any text outside of the JSON object.

    The JSON object must adhere to the following strict definitions:
    {
      "description": "A 1-2 sentence, objective description of the visual elements in the image. This should be very concise and factual.",
      "rich_description": "A more detailed and engaging narrative description in a short paragraph (3-5 sentences). As a photo curator, describe the mood, composition, and potential interactions between subjects, while still grounding your description in visual evidence.",
      "extracted_text": "All text clearly legible in the image. If no text is found, provide an empty string.",
      "safety_flags": {
        "contains_people": "Set to true only if one or more distinct human figures (not statues) are clearly visible and identifiable as people. Do not set to true for indistinct figures in a distant crowd.",
        "contains_potential_pii": "Set to true only if there are clearly readable faces where an individual could be identified, or legible text showing names, addresses, or license plates. The mere presence of a person is not PII.",
        "is_graphic_or_violent": "CRITICAL: Set to true ONLY for explicit, unambiguous depictions of gore, blood, severe injury, acts of physical violence, or weapons being actively used in a threatening manner. The violence must be a direct visual element in the image itself. Symbolic, architectural, or religious items (like a cross, a sword in a museum, a statue of a soldier, or a historic building) are NOT considered violent in themselves and must be flagged as false."
      },
      "detected_objects": [
        "A list of 5-10 key, plainly visible objects or concepts in the image, as an array of strings."
      ]
    }
    """

def analyze_image_with_gemini(image_bytes: bytes, gemini_model) -> dict | None:
    """
    Sends the image and a structured prompt to the Gemini model for analysis.
    """
    if not image_bytes:
        return None

    try:
        image_for_model = Image.open(io.BytesIO(image_bytes))
        prompt = build_analytics_prompt()
        
        logging.info("Sending image to Gemini for analysis with robust prompt...")
        response = gemini_model.generate_content([prompt, image_for_model])

        # Clean the response text to isolate the JSON object
        raw_text = response.text.strip()
        json_start = raw_text.find('{')
        json_end = raw_text.rfind('}') + 1
        
        if json_start == -1 or json_end == 0:
            logging.error(f"Gemini response did not contain a valid JSON object. Response: {raw_text}")
            return {"error": "AI model returned an invalid format. Please try again."}

        json_string = raw_text[json_start:json_end]
        
        analysis = json.loads(json_string)
        logging.info("Successfully parsed Gemini analysis response.")
        return analysis

    except json.JSONDecodeError as e:
        logging.error(f"JSON parsing failed for Gemini response: {e}. Response was: {json_string}")
        return {"error": "Failed to parse the analysis from the AI model."}
    except Exception as e:
        logging.error(f"An unexpected error occurred during Gemini image analysis: {e}", exc_info=True)
        return {"error": f"An unexpected error occurred: {str(e)}"}

def extract_dominant_colors(image_bytes: bytes, num_colors: int = 5) -> list[str]:
    """
    Extracts a palette of the most dominant colors from an image using Pillow (PIL).
    Replaces the heavy scikit-learn dependency.

    Returns:
        A list of hex color strings.
    """
    try:
        # Open the image and convert to RGB
        image = Image.open(io.BytesIO(image_bytes)).convert('RGB')
        
        # Resize to a small thumbnail for speed
        image.thumbnail((150, 150))
        
        # Use Pillow's built-in quantization to reduce the image to 'num_colors'
        # Method 2 = Fast Octree
        quantized = image.quantize(colors=num_colors, method=2)
        
        # Get the palette (comes as a flat list [r, g, b, r, g, b, ...])
        palette = quantized.getpalette()
        
        hex_colors = []
        if palette:
            # We only want the first 'num_colors' RGB triplets
            for i in range(num_colors):
                idx = i * 3
                # Safety check to ensure we don't go out of bounds
                if idx + 2 < len(palette):
                    r = palette[idx]
                    g = palette[idx+1]
                    b = palette[idx+2]
                    
                    # Convert RGB to Hex
                    hex_color = '#{:02x}{:02x}{:02x}'.format(r, g, b)
                    hex_colors.append(hex_color)
            
        return hex_colors

    except Exception as e:
        logging.error(f"Could not extract dominant colors: {e}", exc_info=True)
        return []