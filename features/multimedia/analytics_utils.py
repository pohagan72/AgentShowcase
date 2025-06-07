# features/multimedia/analytics_utils.py
import google.generativeai as genai
import json
import logging
from PIL import Image # type: ignore
import io

def build_analytics_prompt():
    """
    Creates a robust, structured prompt for the Gemini vision model.
    This prompt establishes a persona and provides strict, evidence-based
    guidelines to improve accuracy and reduce false positives.
    """
    return """
    You are a strict, literal-minded content safety analyst. Your task is to analyze the attached image and provide a factual, evidence-based analysis based ONLY on the visual information present. Do not make inferences, assumptions, or judgments based on historical, cultural, or symbolic context.

    Respond ONLY with a single, valid JSON object. Do not include markdown backticks (```json) or any text outside of the JSON object.

    The JSON object must adhere to the following strict definitions:
    {
      "description": "A 1-3 sentence, objective description of the visual elements in the image.",
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
    
    Returns:
        A dictionary with the parsed analysis results, or None if an error occurs.
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
    Extracts a palette of the most dominant colors from an image.
    This is a classic computer vision task, not GenAI, but complements the analysis.
    
    Returns:
        A list of hex color strings.
    """
    try:
        # Open the image using Pillow
        image = Image.open(io.BytesIO(image_bytes))
        
        # Resize to a small thumbnail for performance.
        # This averages the colors and makes processing much faster.
        thumbnail = image.resize((100, 100))
        
        # Get a list of all colors in the thumbnail. The result is a list of (count, pixel) tuples.
        # The `getcolors` method is efficient for this. Maxcolors needs to be high enough.
        color_data = thumbnail.getcolors(thumbnail.width * thumbnail.height)

        if not color_data:
            # This can happen on some complex images, fall back to a slower method
            # For simplicity, we'll just return an empty list here.
            logging.warning("getcolors() returned None, skipping dominant color extraction.")
            return []
            
        # Sort the colors by count (descending)
        sorted_colors = sorted(color_data, key=lambda t: t[0], reverse=True)
        
        # Get the top `num_colors` and convert RGB to HEX
        palette = []
        for i in range(min(num_colors, len(sorted_colors))):
            rgb_color = sorted_colors[i][1]
            # Handle RGBA images by ignoring the alpha channel
            if len(rgb_color) == 4:
                rgb_color = rgb_color[:3]
            hex_color = '#{:02x}{:02x}{:02x}'.format(*rgb_color)
            palette.append(hex_color)
            
        return palette
    except Exception as e:
        logging.error(f"Could not extract dominant colors: {e}", exc_info=True)
        return [] # Return empty list on failure