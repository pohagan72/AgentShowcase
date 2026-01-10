# features/summarization/ppt_builder_logic/prompts.py
import logging
import re
from urllib.parse import urlparse

# --- Constants ---
MAX_INPUT_CHARS = 3000000 

# --- Classification Categories ---
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
    """Creates a prompt specifically for classifying the document text excerpt."""
    max_excerpt_chars = 100000
    truncated_excerpt = document_text_excerpt[:max_excerpt_chars]
    categories_str = "\n - ".join(CLASSIFICATION_CATEGORIES)
    
    prompt = f"""
Analyze the following text excerpt. Based *only* on the content and structure, classify the document type. Pay close attention to common sections or keywords relevant to the categories.
Choose the *single most appropriate* category from the list below. Respond with ONLY the category name.

Available Categories:
 - {categories_str}

Document Excerpt (first {max_excerpt_chars} chars):
\"\"\"
{truncated_excerpt}
\"\"\"

Document Classification Category:"""
    return prompt

# --- Parse Classification Response ---
def parse_classification_response(llm_response_text, source_identifier=""):
    """Extracts the classification category from the LLM's response with heuristic overrides."""
    potential_category = llm_response_text.strip()
    cleaned = ''.join(filter(lambda x: x.isalnum() or x in [' ', '(', ')', '/', '-', ',', ':'], potential_category[:100])).strip().lower()
    source_lower = source_identifier.lower()

    if any(x in source_lower for x in ["10-k", "10k", "annual_report", "annual report", "10-q", "10q"]):
         logging.info(f"Classified as 'Financial Report' based on filename: {source_identifier}")
         return "Financial Report (Annual/10-K/10-Q)"
    
    if 'reddit.com' in source_lower: return "Reddit Thread"
    if any(kw in source_lower for kw in ["swot_analysis", "swot.docx"]): return "SWOT Analysis Document"
    if any(kw in source_lower for kw in ["press_release", "for_immediate_release"]): return "Press Release"

    for cat in CLASSIFICATION_CATEGORIES:
        if cat.lower() == cleaned: return cat
        if cat.lower() in cleaned: return cat

    if "financial" in cleaned and "report" in cleaned: return "Financial Report (Annual/10-K/10-Q)"
    if "resume" in cleaned or "cv" in cleaned: return "Resume/CV"
    if "code" in cleaned or "python" in cleaned: return "Python Source Code"
    if "contract" in cleaned or "agreement" in cleaned: return "Contract/Agreement"

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
3. **DO NOT USE PLACEHOLDERS.** If a number (like Revenue) is not in the text, DO NOT make up a format like "$[Amount]". Instead, summarize what IS in the text (e.g. "Revenue figures were not disclosed in this excerpt").
4. {context_note}"""

# --- Build Generation Prompt (POWERPOINT - FORENSIC UPGRADE) ---
def build_generation_prompt(
    document_text, classification, filename,
    is_part_of_multi_doc_request=False,
    total_docs_in_request=1,
    truncated=False,
    template_name='professional',
    audience="Executives",
    tone="Informative"
):
    source_identifier = f"'{filename}'"
    
    context_note = ""
    if is_part_of_multi_doc_request and total_docs_in_request > 1:
         context_note = f"This document is part of a larger request involving {total_docs_in_request} sources. Summarize *this specific document* but note connections."

    truncation_warning = ""
    if truncated:
        truncation_warning = "**NOTE: Text is truncated/incomplete. Summarize based ONLY on what is present.**\n"

    # --- 1. The Output Schema ---
    output_schema = """
**REQUIRED OUTPUT FORMAT (STRICT):**
You MUST use exactly this format for every slide. Do not use Markdown headers (#).
Use `---` on a new line to separate slides.

Slide Title: [Title]
Content Type: Text
Key Message: [One sentence takeaway]
Strategic Takeaway: [A specific insight, metric, or implication to feature in the side panel]
Design Note: [Layout advice]
Speaker Notes: [Script for presenter]
Elaboration: [Context]
Enhancement Suggestion: [Advice]
Best Practice Tip: [Tip]
Bullets:
- [Point 1]
- [Point 2]
"""

    # --- 2. Expert Persona Instructions ---
    base_instructions = f"""
SYSTEM: You are a Forensic Domain Analyst creating a presentation for {audience}.
Document Class: '{classification}'

**YOUR MISSION:**
1.  **Extract Real Data:** You must hunt for actual numbers, dates, and names in the text.
2.  **No Templates:** Do not output generic bullets like "Revenue: $X". If you find "Revenue was $61.9 Billion", output "Revenue: $61.9 Billion".
3.  **Adaptability:** If the specific financial table is missing, summarize the *narrative* (e.g., "Management focused on AI growth strategy") instead of leaving blank placeholders.
"""

    # --- 3. Class-Specific Logic (Fixed to prevent placeholders) ---
    specific_guidance = ""

    if classification in ["Financial Report (Annual/10-K/10-Q)", "Investment Analysis / Due Diligence Report"]:
        specific_guidance = """
**REQUIRED SLIDES (Financial Forensics):**
**Slide 1: Executive Thesis.** Title: "Strategic Overview". Key Message: The single most important trend identified in the text. Bullets: Summarize the CEO/Management's core message.
**Slide 2: Performance Drivers.** Title: "Key Performance Indicators". Key Message: What is driving the business? Bullets: Extract ANY specific financial metrics found (Revenue, Net Income, Growth %). If no numbers are found, list the strategic priority areas.
**Slide 3: Capital & Strategy.** Title: "Capital Allocation". Key Message: How is money being used? Bullets: Look for mentions of Buybacks, Dividends, or Acquisitions. 
**Slide 4: Material Risks.** Title: "Risk Radar". Key Message: Primary threats mentioned. Bullets: Summarize specific risks from the 'Risk Factors' section.
"""
    elif classification in ["Contract/Agreement", "Terms of Service (ToS)", "SLA"]:
        specific_guidance = """
**REQUIRED SLIDES (Legal Audit):**
**Slide 1: Deal Summary.** Title: "Commercial Terms". Key Message: The main purpose of the agreement. Bullets: Extract Party Names, Effective Date, and Term Length if present.
**Slide 2: Financial Exposure.** Title: "Liability & Fees". Key Message: Financial obligations. Bullets: Extract Fees, Payment Terms, and Liability Caps.
**Slide 3: Critical Clauses.** Title: "Operational Constraints". Key Message: Key obligations. Bullets: Termination rights, Indemnities, Confidentiality terms.
"""
    elif classification == "Resume/CV":
        specific_guidance = """
**REQUIRED SLIDES (Candidate Audit):**
**Slide 1: Profile Snapshot.** Title: "Candidate Summary". Key Message: High-level overview of the candidate. Bullets: Current Title, Years of Experience, Primary Skills.
**Slide 2: Impact Analysis.** Title: "Key Achievements". Key Message: The candidate's biggest wins. Bullets: Extract quantified achievements (e.g., "Grew sales 20%").
**Slide 3: Skill Gap.** Title: "Capabilities & Gaps". Key Message: Assessment of fit. Bullets: Technical skills listed versus missing skills.
"""
    elif classification in ["System Design Document", "Technical Report/Documentation"]:
        specific_guidance = """
**REQUIRED SLIDES (Tech Review):**
**Slide 1: System Architecture.** Title: "High-Level Design". Key Message: The core system pattern. Bullets: List components and technologies mentioned.
**Slide 2: Scalability Constraints.** Title: "Performance Analysis". Key Message: System limits. Bullets: Extract constraints (throughput, latency, storage).
**Slide 3: Reliability Strategy.** Title: "Resilience". Key Message: How the system handles failure. Bullets: Backup strategies, failover mechanisms.
"""
    else: # General
        specific_guidance = """
**REQUIRED SLIDES (Executive Briefing):**
**Slide 1: The Bottom Line (BLUF).** Title: "Executive Summary". Key Message: The main conclusion of the document. Bullets: Top 3 critical facts found in the text.
**Slide 2: Key Theme 1.** Title: [Topic Name]. Key Message: Why this topic matters. Bullets: Supporting details from the text.
**Slide 3: Key Theme 2.** Title: [Topic Name]. Key Message: Secondary impact. Bullets: Supporting details from the text.
**Slide 4: Action Plan.** Title: "Recommendations". Key Message: Suggested next steps based on the text. Bullets: Actionable items.
"""

    prompt = f"""
{base_instructions}

{truncation_warning}

{specific_guidance}

{output_schema}

**SOURCE TEXT:**
\"\"\"
{document_text}
\"\"\"

**Generate the slides now.** Start immediately with the first slide block.
"""
    return prompt

# --- EXPERT TEXT SUMMARY LOGIC (Unchanged) ---
def build_expert_text_summary_prompt(text_to_summarize, classification):
    thinking_instructions = """
**PHASE 1: LIVE DELIBERATION (MANDATORY)**
Before generating the report, you MUST output a series of "Thinking Logs".
Format: `::TYPE:: Content`
Types: `::HYPO::`, `::EVIDENCE::`, `::DECISION::`, `::NOTE::`.
Sequence: Hypo -> Evidence (x3) -> Decisions (x2) -> Note.

**PHASE 2: THE REPORT**
Output `### REPORT START` on a new line, then the Markdown summary.
"""
    # (Rest of text summary logic preserved)
    specific_guidance = ""
    if classification in ["Financial Report (Annual/10-K/10-Q)", "Investment Analysis / Due Diligence Report"]:
        specific_guidance = "**OUTPUT FORMAT: INVESTMENT MEMO**\n## Executive Thesis\n## Financial Scoreboard\n## Segment Deep Dive\n## Risk Radar"
    elif classification in ["Contract/Agreement", "Terms of Service (ToS)", "SLA"]:
        specific_guidance = "**OUTPUT FORMAT: DEAL SHEET**\n## Commercial Terms\n## Critical Exposure\n## Operational Constraints"
    elif classification in ["System Design Document", "Python Source Code"]:
        specific_guidance = "**OUTPUT FORMAT: ARCHITECTURE REVIEW**\n## System Overview\n## Scalability\n## Reliability"
    else:
        specific_guidance = "**OUTPUT FORMAT: EXECUTIVE BRIEFING**\n## Bottom Line (BLUF)\n## Key Themes\n## Critical Data\n## Action Items"

    return f"""
SYSTEM: You are a Forensic Domain Analyst.
Document Class: '{classification}'

**SOURCE TEXT:**
\"\"\"
{text_to_summarize}
\"\"\"

{specific_guidance}

{thinking_instructions}

**FORMATTING:** Use Markdown headers (##), bullets, and **bold** metrics.
"""