from flask import render_template, request, flash, current_app, g
import os
import io
import uuid
from werkzeug.utils import secure_filename
import google.generativeai as genai
from docx import Document
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
import pandas as pd
import PyPDF2
import re # For cleaning classification response
import logging # For better logging

# --- Constants ---
MAX_CONTENT_LENGTH = 1000000  # Limit for text to be summarized
MAX_CLASSIFICATION_EXCERPT = 15000 # Max characters to send for classification

# --- Classification Categories (from your prompts.py) ---
CLASSIFICATION_CATEGORIES = [
    "Resume/CV", "Patent", "Terms of Service (ToS)", "Service Level Agreement (SLA)",
    "Contract/Agreement", "Privacy Policy", "Informational Guide/Manual",
    "Technical Report/Documentation", "Python Source Code", "News Article/Blog Post",
    "Marketing Plan/Proposal", "Meeting Notes/Summary", "Case Study / Research Report",
    "Financial Report (Annual/10-K/10-Q)", "Web Page Content", "Reddit Thread",
    "Legal Case Brief", "Legislative Bill/Regulation", "Business Plan",
    "SWOT Analysis Document", "Press Release", "System Design Document",
    "User Story / Feature Requirement Document", "Medical Journal Article",
    "Academic Paper/Research", "Collection of Mixed Documents", # Added from your list
    "General Business Document", # Ensure this is distinct enough or used as a fallback
    "Other",
]

# --- Helper Functions for Classification and Summarization ---

def get_classification_prompt_for_summarization(text_excerpt):
    """Creates a prompt for classifying the document text excerpt."""
    categories_str = "\n - ".join(CLASSIFICATION_CATEGORIES)
    prompt = f"""
Analyze the following text excerpt. Based ONLY on the content and structure, classify the document type.
Pay close attention to common sections or keywords relevant to the categories (e.g.,
"Experience" for Resumes, "Claims" for Patents, `def`/`class`/`import` for Python Code, "Service Level" for SLAs,
"Financial Statements", "MD&A", "10-K", "Annual Report", "Risk Factors" for Financial Reports, "comments"/"r/" for Reddit Threads,
"versus"/"v."/"holding" for Legal Case Briefs, "Section"/"Article"/"Be it enacted" for Legislative Bills/Regulations,
"Executive Summary"/"Market Analysis"/"Financial Projections" for Business Plans, explicit "Strengths"/"Weaknesses"/"Opportunities"/"Threats" lists for SWOT Analysis,
"FOR IMMEDIATE RELEASE"/"Contact:" for Press Releases, "Architecture"/"Components"/"API Specification" for System Design Documents,
"As a"/"I want"/"Acceptance Criteria" for User Stories/Feature Requirements, "Abstract"/"Methods"/"Results"/"PICO" for Medical Journal Articles).
Choose the *single most appropriate* category from the list below. Respond with ONLY the category name.

Available Categories:
 - {categories_str}

Document Excerpt (first {len(text_excerpt)} chars):
\"\"\"
{text_excerpt}
\"\"\"

Document Classification Category:"""
    return prompt

def parse_classification_response_for_summarization(llm_response_text, source_identifier=""):
    """
    Extracts the classification category from the LLM's response,
    with some heuristics adapted from your prompts.py.
    """
    potential_category = llm_response_text.strip()
    cleaned_category_llm = re.sub(r'[^\w\s/\(\)\-\.,:]', '', potential_category[:100]).strip() # Allow more chars for context
    cleaned_lower_llm = cleaned_category_llm.lower()

    source_lower = source_identifier.lower() if source_identifier else ""

    # --- Heuristic Check 1: Filename/Source Identifier Overrides (Simplified) ---
    if source_lower:
        if "10-k" in source_lower or "10k" in source_lower or "annual_report" in source_lower or "annual report" in source_lower or "10-q" in source_lower or "10q" in source_lower:
            logging.info(f"Classified as 'Financial Report (Annual/10-K/10-Q)' based on source: {source_identifier}")
            return "Financial Report (Annual/10-K/10-Q)"
        if 'reddit.com' in source_lower and '/comments/' in source_lower:
            logging.info(f"Classified as 'Reddit Thread' based on source URL: {source_identifier}")
            return "Reddit Thread"
        if any(kw in source_lower for kw in ["swot_analysis", "swot.docx", "swot.pdf"]):
            logging.info(f"Classified as 'SWOT Analysis Document' based on source: {source_identifier}")
            return "SWOT Analysis Document"
        # Add more source-based heuristics if critical

    # --- Heuristic Check 2: Check LLM response directly ---
    for cat in CLASSIFICATION_CATEGORIES:
        if cat.lower() == cleaned_lower_llm:
            logging.info(f"Classified as: '{cat}' (Exact match from LLM for '{cleaned_category_llm}')")
            # Apply a few critical overrides based on source if LLM is too generic
            if cat in ["Web Page Content", "News Article/Blog Post"] and 'reddit.com' in source_lower and '/comments/' in source_lower:
                logging.info(f"Overriding LLM '{cat}' to 'Reddit Thread' based on URL.")
                return "Reddit Thread"
            return cat

    logging.warning(f"LLM class '{potential_category}' not an exact match. Attempting keyword/fuzzy matching...")

    # --- Heuristic Check 3: Specific Keyword Checks in LLM Response (Simplified from your example) ---
    # This acts as a fallback if the LLM's direct output isn't clean
    if "financial statement" in cleaned_lower_llm or "10-k" in cleaned_lower_llm or "annual report" in cleaned_lower_llm:
        return "Financial Report (Annual/10-K/10-Q)"
    if "reddit" in cleaned_lower_llm or "subreddit" in cleaned_lower_llm:
        return "Reddit Thread"
    # Add more keyword checks for common misclassifications or key terms if needed

    # --- Heuristic Check 4: Fuzzy 'in' check (Simplified) ---
    for cat in CLASSIFICATION_CATEGORIES:
        if cat.lower() in cleaned_lower_llm: # If our category name is found in the LLM's (potentially noisy) response
            logging.info(f"Classified as: '{cat}' (Fuzzy 'in' match for '{cleaned_category_llm}')")
            if cat in ["Web Page Content", "News Article/Blog Post"] and 'reddit.com' in source_lower and '/comments/' in source_lower:
                logging.info(f"Overriding fuzzy LLM '{cat}' to 'Reddit Thread' based on URL.")
                return "Reddit Thread"
            return cat

    logging.warning(f"Could not reliably classify '{potential_category}' from LLM or source. Falling back to 'Other'.")
    return "Other"


def build_expert_summary_prompt(text_to_summarize, classification, filename=""):
    """Builds a summarization prompt tailored by document classification."""
    source_identifier_text = f" from a document named '{filename}'" if filename else ""
    expert_focus = "Focus on its main topic, key arguments, evidence, and conclusions. Identify the core message." # Default

    # Tailor focus based on classification - adapt from your prompts.py logic
    if classification == "Resume/CV":
        expert_focus = "Focus on the candidate's key skills, quantifiable achievements, most relevant experiences, and overall career trajectory suitable for a hiring manager's review."
    elif classification == "Patent":
        expert_focus = "Focus on the core invention (what it is and does), its novelty, the main problem it solves, and the essence of its primary claims. Avoid excessive legal jargon."
    elif classification == "Terms of Service (ToS)" or classification == "Privacy Policy" or classification == "Contract/Agreement":
        expert_focus = "Focus on the purpose of the document, key user/party obligations, rights granted, critical limitations or disclaimers, and data usage/sharing if applicable (for Privacy Policy)."
    elif classification == "Service Level Agreement (SLA)":
        expert_focus = "Focus on the key service commitments, performance metrics (like uptime, response times), responsibilities of parties, and remedies or credits for service failures."
    elif classification == "Informational Guide/Manual":
        expert_focus = "Focus on the main purpose of the guide, key instructions or procedures, important definitions, and primary takeaways for a user."
    elif classification == "Technical Report/Documentation" or classification == "System Design Document":
        expert_focus = "Focus on the purpose of the system/technology, its main components or architecture, key functionalities, and critical findings or specifications."
    elif classification == "Python Source Code":
        expert_focus = "Briefly describe the purpose of the code, its main functions or classes, inputs/outputs, and any significant libraries or algorithms used. Do not attempt to execute the code, summarize its textual description and structure."
    elif classification == "News Article/Blog Post" or classification == "Web Page Content" or classification == "Press Release":
        expert_focus = "Focus on the main event or topic, key information presented (who, what, when, where, why), important quotes or data points, and the primary conclusion or call to action."
    elif classification == "Marketing Plan/Proposal" or classification == "Business Plan":
        expert_focus = "Focus on the core business/marketing objective, target audience, key strategies proposed, expected outcomes or KPIs, and the unique value proposition."
    elif classification == "Meeting Notes/Summary":
        expert_focus = "Focus on the main topics discussed, key decisions made, action items assigned (and to whom, if mentioned), and any deadlines set."
    elif classification == "Case Study / Research Report" or classification == "Academic Paper/Research" or classification == "Medical Journal Article":
        expert_focus = "Focus on the research question or problem, methodology used, key findings or results (including significant data if presented concisely), and the authors' main conclusions or implications."
    elif classification == "Financial Report (Annual/10-K/10-Q)":
        expert_focus = "Focus on overall financial performance (key metrics like revenue, net income, cash flow), significant trends (YoY changes if evident), major risk factors discussed, and any management outlook or guidance provided."
    elif classification == "Reddit Thread":
        expert_focus = "Focus on the original poster's (OP) main question or statement, the dominant themes of discussion in the comments, prevalent viewpoints or arguments, and any general sentiment or consensus that can be inferred. Acknowledge that the text is an excerpt."
    elif classification == "Legal Case Brief":
        expert_focus = "Focus on the key facts of the case, the primary legal issue(s) addressed by the court, the rule of law applied, the court's holding (decision), and the core reasoning behind the decision."
    elif classification == "Legislative Bill/Regulation":
        expert_focus = "Focus on the purpose of the bill/regulation, its main provisions or changes to existing law, who it applies to, and its intended impact or effective date."
    elif classification == "SWOT Analysis Document":
        expert_focus = "Identify and summarize the key Strengths, Weaknesses, Opportunities, and Threats presented in the document."
    elif classification == "User Story / Feature Requirement Document":
        expert_focus = "Focus on the target user (As a...), the desired functionality (I want to...), and the intended benefit (So that...). Also, summarize key acceptance criteria if listed."
    # "Collection of Mixed Documents" and "General Business Document" might use the default or a slightly more generic version.
    elif classification == "Collection of Mixed Documents":
        expert_focus = "Identify the overarching theme or purpose connecting the documents if discernible, or summarize the key individual components if they are distinct. Note that it's a collection."
    elif classification == "General Business Document":
        expert_focus = "Focus on the main purpose of the document, key information conveyed, any decisions or actions proposed, and the primary audience or context if evident."


    prompt = f"""SYSTEM: You are an expert summarization AI. Your task is to provide a concise, informative, and contextually relevant summary of the following text.
The document has been identified as a '{classification}'{source_identifier_text}.

INSTRUCTIONS:
1. Carefully read the provided text.
2. Based on the document type ('{classification}'), {expert_focus}
3. Generate a fluent, well-written summary that is approximately 3-6 sentences long.
4. The summary should be coherent, accurate, and capture the most important aspects of the original text according to its identified type.
5. Do not add any personal opinions, interpretations, or information not present in the original text.
6. Output ONLY the summary. Do not include preambles like "Here is the summary:" or any other conversational text.

TEXT TO SUMMARIZE:
---
{text_to_summarize}
---
"""
    return prompt

# --- Main Gemini Interaction (Combined Classification and Summarization) ---
def classify_and_summarize_with_gemini(text_content, model_name_from_config, filename=""):
    """
    First classifies the text, then generates a summary based on that classification.
    Returns a tuple: (classification_used_for_summary, summary_text, error_occurred_flag)
    """
    if not text_content or not text_content.strip():
        # This case should ideally be caught before calling this function
        return "N/A", "No text provided to summarize.", True

    classification = "Other" # Default
    final_summary = ""
    error_occurred = False
    request_id_tag = g.request_id if hasattr(g, 'request_id') else 'SUMMARIZE_TASK'


    try:
        model = genai.GenerativeModel(model_name_from_config)

        # 1. Classification Step
        classification_excerpt = text_content[:MAX_CLASSIFICATION_EXCERPT]
        classification_prompt_text = get_classification_prompt_for_summarization(classification_excerpt)
        
        logging.info(f"[{request_id_tag}] Sending classification prompt (excerpt length: {len(classification_excerpt)})...")
        classification_response = model.generate_content(classification_prompt_text)
        
        if classification_response and classification_response.text:
            classification = parse_classification_response_for_summarization(classification_response.text, filename)
            flash(f"Detected document type: {classification}", "info")
            logging.info(f"[{request_id_tag}] Classification result: {classification}")
        elif hasattr(classification_response, 'prompt_feedback') and classification_response.prompt_feedback.block_reason:
            block_reason = classification_response.prompt_feedback.block_reason.name
            msg = f"Classification blocked by AI safety filters ({block_reason}). Defaulting to 'Other' for summary."
            logging.warning(f"[{request_id_tag}] {msg}")
            flash(msg, "warning")
            classification = "Other" # Fallback
        else:
            msg = "Classification failed: AI returned no text for classification. Defaulting to 'Other' for summary."
            logging.warning(f"[{request_id_tag}] {msg}")
            flash(msg, "warning")
            classification = "Other" # Fallback

        # 2. Summarization Step
        summary_prompt_text = build_expert_summary_prompt(text_content, classification, filename)
        logging.info(f"[{request_id_tag}] Sending expert summarization prompt (classification: {classification})...")
        # For debugging the prompt: logging.debug(f"Summarization Prompt:\n{summary_prompt_text}")
        
        summary_response = model.generate_content(summary_prompt_text)

        if summary_response and summary_response.text:
            final_summary = summary_response.text.strip()
            logging.info(f"[{request_id_tag}] Summary generated successfully.")
        elif hasattr(summary_response, 'prompt_feedback') and summary_response.prompt_feedback.block_reason:
            block_reason = summary_response.prompt_feedback.block_reason.name
            msg = f"Summarization blocked by AI safety filters ({block_reason})."
            logging.warning(f"[{request_id_tag}] {msg}")
            flash(msg, "warning")
            final_summary = "(Summarization was blocked due to safety filters. Please review your text or try different content.)"
            error_occurred = True
        else:
            msg = "Summarization failed: The AI model did not return any summary text."
            logging.warning(f"[{request_id_tag}] {msg}")
            flash(msg, "error")
            final_summary = "(Summarization failed as the AI model did not return text.)"
            error_occurred = True
            
    except Exception as e:
        error_msg = f"An error occurred with the AI service: {str(e)}"
        logging.error(f"[{request_id_tag}] {error_msg}", exc_info=True) # Log full traceback
        flash(error_msg, "error")
        final_summary = "(An error occurred during the AI processing. Please check logs.)"
        error_occurred = True

    return classification, final_summary, error_occurred


# --- Routes for Summarization Feature ---
def define_summarization_routes(app_shell):

    @app_shell.route("/process/summarization/summarize", methods=["POST"])
    def process_summarize():
        g.request_id = uuid.uuid4().hex 
        logging.info(f"Received summarization request {g.request_id}")

        context = {
            "summary": "",
            "hx_target_is_result": True 
        }

        gemini_configured = current_app.config.get('GEMINI_CONFIGURED', False)
        if not gemini_configured:
            flash("Gemini API is not configured. Summarization service is unavailable.", "error")
            logging.error(f"[{g.request_id}] Gemini not configured.")
            return render_template("summarization/templates/summarization_content.html", **context)

        text_content = ""
        original_filename = ""
        file = request.files.get("file")

        if file and file.filename != "":
            original_filename = secure_filename(file.filename)
            file_extension = os.path.splitext(original_filename)[1].lower()
            logging.info(f"[{g.request_id}] Processing uploaded file: {original_filename}")

            try:
                file_stream = io.BytesIO(file.read())
                if file_extension == ".docx": text_content = read_text_from_docx(file_stream)
                elif file_extension == ".pptx": text_content = read_text_from_pptx(file_stream)
                elif file_extension == ".xlsx": text_content = read_text_from_excel(file_stream)
                elif file_extension == ".pdf": text_content = read_text_from_pdf(file_stream)
                else:
                    flash(f"Unsupported file type: {file_extension}. Only .docx, .pptx, .xlsx, and .pdf are supported.", "error")
                    logging.warning(f"[{g.request_id}] Unsupported file type: {file_extension}")
                    return render_template("summarization/templates/summarization_content.html", **context)
                
                if not text_content.strip():
                    flash(f"Could not extract text from the uploaded file: {original_filename}. It might be empty, password-protected, or image-based.", "warning")
                    logging.warning(f"[{g.request_id}] No text extracted from file: {original_filename}")
            except Exception as e:
                logging.error(f"[{g.request_id}] Error reading file '{original_filename}': {e}", exc_info=True)
                flash(f"Error processing uploaded file '{original_filename}': {str(e)}", "error")
                return render_template("summarization/templates/summarization_content.html", **context)

        if not text_content or not text_content.strip():
            text_content = request.form.get("text_to_summarize", "").strip()
            if text_content and not original_filename:
                logging.info(f"[{g.request_id}] Processing text from textarea.")
            elif text_content and original_filename: 
                logging.info(f"[{g.request_id}] File content used ({original_filename}). Text from textarea ignored as file was provided.")

        if not text_content:
            flash("No file uploaded or text provided for summarization.", "warning")
            logging.info(f"[{g.request_id}] No text content available for summarization.")
            return render_template("summarization/templates/summarization_content.html", **context)

        if len(text_content) > MAX_CONTENT_LENGTH:
            flash(f"Input text (length: {len(text_content):,}) exceeds the maximum allowed length of {MAX_CONTENT_LENGTH:,} characters. Please provide shorter text.", "error")
            logging.warning(f"[{g.request_id}] Text length {len(text_content)} exceeds limit.")
            return render_template("summarization/templates/summarization_content.html", **context)

        logging.info(f"[{g.request_id}] Text length for summarization: {len(text_content):,} chars. Filename: '{original_filename or 'N/A'}'")
        
        gemini_model_name = current_app.config.get('GEMINI_MODEL_NAME')
        if not gemini_model_name:
            flash("Gemini model name is not configured in the application.", "error")
            logging.error(f"[{g.request_id}] Gemini model name not configured.")
            return render_template("summarization/templates/summarization_content.html", **context)

        _classification, summary_result, error_flag = classify_and_summarize_with_gemini(text_content, gemini_model_name, original_filename)
        context["summary"] = summary_result
        
        if not error_flag and summary_result and not ("(Summarization was blocked" in summary_result or "(Summarization failed" in summary_result or "(An error occurred" in summary_result):
            # Only flash general success if no specific error/block message was part of the summary itself
            # The classify_and_summarize_with_gemini function already flashes more specific messages.
            pass # Consider if a generic "Summarization process attempted" is needed or if existing flashes are enough.

        return render_template("summarization/templates/summarization_content.html", **context)


# --- File Reading Utility Functions ---
# (Ensure these are complete and robust as per your previous working versions)
def read_text_from_docx(file_stream):
    try:
        file_stream.seek(0)
        doc = Document(file_stream)
        full_text = [p.text for p in doc.paragraphs if p.text.strip()]
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    cell_text = "\n".join([p.text for p in cell.paragraphs if p.text.strip()])
                    if cell_text: full_text.append(cell_text)
        return "\n".join(full_text)
    except Exception as e:
        logging.error(f"Error reading DOCX: {e}", exc_info=True)
        raise # Re-raise to be caught by main handler

def read_text_from_pptx(file_stream):
    try:
        file_stream.seek(0)
        ppt = Presentation(file_stream)
        full_text = []
        for slide in ppt.slides:
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for p in shape.text_frame.paragraphs:
                        if p.text.strip(): full_text.append(p.text)
                if shape.has_table:
                    for row in shape.table.rows:
                        for cell in row.cells:
                            if cell.text_frame and cell.text_frame.text.strip():
                                full_text.append(cell.text_frame.text)
                if hasattr(shape, 'shape_type') and shape.shape_type == MSO_SHAPE_TYPE.GROUP:
                    for subshape in shape.shapes:
                         if hasattr(subshape, 'has_text_frame') and subshape.has_text_frame:
                             for p in subshape.text_frame.paragraphs:
                                if p.text.strip(): full_text.append(p.text)
        return "\n".join(full_text)
    except Exception as e:
        logging.error(f"Error reading PPTX: {e}", exc_info=True)
        raise

def read_text_from_excel(file_stream):
    try:
        file_stream.seek(0)
        excel_data = pd.read_excel(file_stream, sheet_name=None)
        text_list = []
        if excel_data:
            for sheet_name, df in excel_data.items():
                for r in range(df.shape[0]):
                    for c in range(df.shape[1]):
                        cell_value = df.iat[r,c]
                        if pd.notna(cell_value):
                            cell_str = str(cell_value).strip()
                            if cell_str: text_list.append(cell_str)
        return "\n".join(text_list)
    except Exception as e:
        logging.error(f"Error reading Excel: {e}", exc_info=True)
        raise

def read_text_from_pdf(file_stream):
    try:
        file_stream.seek(0)
        reader = PyPDF2.PdfReader(file_stream)
        text_list = []
        if reader.pages: # Check if there are pages
            for page_num in range(len(reader.pages)):
                page = reader.pages[page_num]
                extracted_text = page.extract_text()
                if extracted_text: # Ensure text was actually extracted
                    text_list.append(extracted_text)
        if not text_list: # If no text was extracted from any page
            logging.warning("PDF processed, but no text could be extracted (possibly image-based or empty).")
            return ""
        return "\n".join(text_list)
    except PyPDF2.errors.PdfReadError as pdf_err: # Specific PyPDF2 error
        logging.error(f"PyPDF2 could not read PDF (possibly corrupted or password-protected without providing password): {pdf_err}", exc_info=True)
        raise ValueError(f"Could not read PDF: {pdf_err}. It might be corrupted or password-protected.") from pdf_err
    except Exception as e: # Generic catch-all
        logging.error(f"Generic error reading PDF: {e}", exc_info=True)
        raise