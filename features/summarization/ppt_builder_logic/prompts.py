# features/summarization/ppt_builder_logic/prompts.py
import logging
import re
from urllib.parse import urlparse

# --- Constants ---
MAX_INPUT_CHARS = 3000000 

# --- Classification Categories (Unchanged) ---
CLASSIFICATION_CATEGORIES = [
    "Resume/CV", "Patent", "Terms of Service (ToS)", "Service Level Agreement (SLA)",
    "Contract/Agreement", "Privacy Policy", "Informational Guide/Manual",
    "Technical Report/Documentation", "Python Source Code", "News Article/Blog Post",
    "Marketing Plan/Proposal", "Meeting Notes/Summary", "Case Study / Research Report",
    "Financial Report (Annual/10-K/10-Q)", "Web Page Content", "Reddit Thread",
    "General Business Document", "Academic Paper/Research", "Collection of Mixed Documents",
    "Legal Case Brief", "Legislative Bill/Regulation", "Business Plan",
    "SWOT Analysis Document", "Press Release", "Investment Analysis / Due Diligence Report",
    "System Design Document", "User Story / Feature Requirement Document",
    "Medical Journal Article", "Other",
]

# --- Get Classification Prompt ---
def get_classification_prompt(document_text_excerpt):
    max_excerpt_chars = 100000
    truncated_excerpt = document_text_excerpt[:max_excerpt_chars]
    categories_str = "\n - ".join(CLASSIFICATION_CATEGORIES)
    return f"""Analyze the following text excerpt. Respond with ONLY the single most appropriate category name from the list below.
Available Categories:
 - {categories_str}
Document Excerpt:
\"\"\"
{truncated_excerpt}
\"\"\"
Document Classification Category:"""

# --- Parse Classification Response ---
def parse_classification_response(llm_response_text, source_identifier=""):
    potential_category = llm_response_text.strip()
    cleaned = ''.join(filter(lambda x: x.isalnum() or x in [' ', '(', ')', '/', '-', ',', ':'], potential_category[:100])).strip().lower()
    source_lower = source_identifier.lower()

    if any(x in source_lower for x in ["10-k", "10k", "annual_report", "annual report", "10-q"]): return "Financial Report (Annual/10-K/10-Q)"
    if 'reddit.com' in source_lower: return "Reddit Thread"
    
    for cat in CLASSIFICATION_CATEGORIES:
        if cat.lower() in cleaned: return cat
    
    if "financial" in cleaned and "report" in cleaned: return "Financial Report (Annual/10-K/10-Q)"
    if "contract" in cleaned: return "Contract/Agreement"
    
    return "General Business Document"

# --- Guidance Blocks ---
def get_audience_guidance(audience):
    return f"\n**Audience Guidance:** Tailor content for {audience}."

def get_tone_guidance(tone):
    return f"**Tone:** {tone}"

def get_critical_instructions(classification, context_note=""):
    return f"""**CRITICAL INSTRUCTIONS:**
1. Summarize ONLY the provided text.
2. Structure output based on '{classification}'.
3. {context_note}"""

# --- Build Generation Prompt (PPT) ---
def build_generation_prompt(document_text, classification, filename, is_part_of_multi_doc_request=False, total_docs_in_request=1, truncated=False, template_name='professional', audience="Executives", tone="Informative"):
    """
    Standard PPT Prompt. No streaming/thinking logs to ensure stability.
    """
    source_identifier = f"'{filename}'"
    context_note = ""
    if is_part_of_multi_doc_request: context_note = f"Part of {total_docs_in_request} documents."
    truncation_warning = "**NOTE: Text is truncated.**\n" if truncated else ""

    output_schema = """
**REQUIRED OUTPUT FORMAT (STRICT):**
Use `---` on a new line to separate slides.

Slide Title: [Title]
Content Type: Text
Key Message: [One sentence takeaway]
Strategic Takeaway: [A specific insight, metric, or implication to feature in the side panel]
Design Note: [Layout advice]
Speaker Notes: [Script]
Elaboration: [Context]
Enhancement Suggestion: [Tip]
Best Practice Tip: [Tip]
Bullets:
- [Point 1]
- [Point 2]
"""
    
    # Specific structure guidance
    structure = "**Required Slides:** Executive Summary, Key Themes, Critical Data, Strategic Implications."
    if classification == "Financial Report (Annual/10-K/10-Q)": structure = "**Required Slides:** Highlights, Segment Performance, Capital Allocation, Risks."

    prompt = f"""
You are an expert Domain Analyst. Create a presentation based on the text from {source_identifier}.
Document Class: {classification}
{truncation_warning}
Context: Audience: {audience} | Tone: {tone}

{get_audience_guidance(audience)}
{get_critical_instructions(classification, context_note)}

{output_schema}

{structure}

**Source Text:**
\"\"\"
{document_text}
\"\"\"

**Generate the complete slide deck now.** Start immediately with the first slide block.
"""
    return prompt

# --- EXPERT TEXT SUMMARY LOGIC (Unchanged) ---
def build_expert_text_summary_prompt(text_to_summarize, classification):
    # (Same as before)
    specific_guidance = ""
    if classification in ["Financial Report (Annual/10-K/10-Q)", "Investment Analysis / Due Diligence Report"]:
        specific_guidance = "**OUTPUT FORMAT: INVESTMENT MEMO**\n## Executive Thesis\n## Financial Scoreboard\n## Segment Deep Dive\n## Risk Radar"
    else:
        specific_guidance = "**OUTPUT FORMAT: EXECUTIVE BRIEFING**\n## Bottom Line (BLUF)\n## Key Themes\n## Critical Data\n## Action Items"

    prompt = f"""
SYSTEM: You are a Forensic Domain Analyst.
Document Class: '{classification}'

**SOURCE TEXT:**
\"\"\"
{text_to_summarize}
\"\"\"

{specific_guidance}

**CRITICAL INSTRUCTION: THINK BEFORE YOU WRITE**
You MUST output your analysis process as a series of log lines BEFORE generating the final report.

**REQUIRED LOG FORMAT:**
`::TYPE:: Content`

**REQUIRED STEPS:**
1. `::HYPO:: [State your initial hypothesis]`
2. `::EVIDENCE:: [Quote specific data point]`
3. `::DECISION:: [Explain structuring]`
4. `::NOTE:: [Mention uncertainty]`

**AFTER THE LOGS:**
Output `### REPORT START` on a new line, followed immediately by the Markdown report.
"""
    return prompt