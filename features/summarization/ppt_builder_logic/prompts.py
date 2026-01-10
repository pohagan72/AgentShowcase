# features/summarization/ppt_builder_logic/prompts.py
import logging
import re
from urllib.parse import urlparse

# --- Constants ---
MAX_INPUT_CHARS = 3000000 # Applies PER document / web page

# --- Classification Categories ---
CLASSIFICATION_CATEGORIES = [
    "Resume/CV",
    "Patent",
    "Terms of Service (ToS)",
    "Service Level Agreement (SLA)",
    "Contract/Agreement",
    "Privacy Policy",
    "Informational Guide/Manual",
    "Technical Report/Documentation",
    "Python Source Code",
    "News Article/Blog Post",
    "Marketing Plan/Proposal",
    "Meeting Notes/Summary",
    "Case Study / Research Report",
    "Financial Report (Annual/10-K/10-Q)",
    "Web Page Content",
    "Reddit Thread",
    "General Business Document",
    "Academic Paper/Research",
    "Collection of Mixed Documents",
    "Legal Case Brief",
    "Legislative Bill/Regulation",
    "Business Plan",
    "SWOT Analysis Document",
    "Press Release",
    "Investment Analysis / Due Diligence Report",
    "System Design Document",
    "User Story / Feature Requirement Document",
    "Medical Journal Article",
    "Other",
]

# --- Get Classification Prompt ---
def get_classification_prompt(document_text_excerpt):
    """Creates a prompt specifically for classifying the document text excerpt."""
    max_excerpt_chars = 100000
    truncated_excerpt = document_text_excerpt[:max_excerpt_chars]
    categories_str = "\n - ".join(CLASSIFICATION_CATEGORIES)
    
    prompt = f"""
Analyze the following text excerpt. Based *only* on the content and structure, classify the document type. Pay close attention to common sections or keywords relevant to the categories (e.g.,
"Experience" for Resumes, "Claims" for Patents, `def`/`class` for Python, "Financial Statements"/"10-K" for Financial Reports, "comments" for Reddit, "holding" for Legal Cases).
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
    cleaned_category = ''.join(filter(lambda char: char.isalnum() or char in [' ', '(', ')', '/', '-', ',', ':'], potential_category[:100])).strip()
    cleaned_lower = cleaned_category.lower()
    source_lower = source_identifier.lower()

    # --- Strong Heuristic Overrides (Trust Filenames/URLs over LLM sometimes) ---
    if any(x in source_lower for x in ["10-k", "10k", "annual_report", "annual report", "10-q", "10q"]):
         logging.info(f"Classified as 'Financial Report' based on filename: {source_identifier}")
         return "Financial Report (Annual/10-K/10-Q)"
    
    if 'reddit.com' in source_lower:
        return "Reddit Thread"
    
    if any(kw in source_lower for kw in ["swot_analysis", "swot.docx"]):
        return "SWOT Analysis Document"
    
    if any(kw in source_lower for kw in ["press_release", "for_immediate_release"]):
        return "Press Release"

    # --- Match against known categories ---
    for cat in CLASSIFICATION_CATEGORIES:
        if cat.lower() == cleaned_lower:
            return cat
        # Fuzzy match
        if cat.lower() in cleaned_lower:
            return cat

    # Fallback heuristics based on keywords in the *LLM response*
    if "financial" in cleaned_lower and "report" in cleaned_lower: return "Financial Report (Annual/10-K/10-Q)"
    if "resume" in cleaned_lower or "cv" in cleaned_lower: return "Resume/CV"
    if "code" in cleaned_lower or "python" in cleaned_lower: return "Python Source Code"
    if "contract" in cleaned_lower or "agreement" in cleaned_lower: return "Contract/Agreement"

    logging.warning(f"Could not reliably classify '{potential_category}'. Falling back to 'Other'.")
    return "Other"

# --- Guidance Blocks (The "Brain" of the Persona) ---

def get_audience_guidance(audience):
    """Generates prompt guidance based on the selected audience."""
    if audience == "Executives":
        return """
**Audience Guidance: Executives (The "CRO/CEO" Persona)**
*   **The Mindset:** Executives do not read summaries to "know what's in the document." They read to **make decisions**, **assess risk**, or **spot opportunities**.
*   **The "So What?" Rule:** For every bullet point, ask: "Does this impact Revenue, Cost, Risk, or Strategy?" If not, delete it.
*   **Numbers over Adjectives:** Never say "Sales grew significantly." Say "Sales grew 12% YoY." Never say "There are risks." Say "Currency headwinds may impact Q4 margins by 20bps."
*   **Strategic Narrative:** Identify the core commercial story. Is this a turnaround? A growth phase? A consolidation? Frame the bullets around that narrative.
*   **Suppress "Compliance Fluff":** actively ignore standard corporate boilerplate (e.g., "We strive to be ethical," "We follow NIST frameworks," "Internal controls are effective") unless there is a specific, material failure mentioned.
"""
    elif audience == "Technical Team":
        return """
**Audience Guidance: Technical Team (The "CTO/Lead Dev" Persona)**
*   **Prioritization:** Focus on architecture, implementation details, dependencies, data flow, and trade-offs.
*   **Precision:** Use exact technical terminology found in the text. Do not simplify API names or library versions.
*   **The "How" over the "What":** Explain *how* the system works or *how* the results were achieved, not just the high-level purpose.
"""
    elif audience == "General":
        return """
**Audience Guidance: General Audience**
*   **Prioritization:** Focus on the "Big Picture," key benefits, and high-level takeaways.
*   **Clarity:** Use plain language. Explain jargon if it must be used.
*   **Flow:** Ensure a logical narrative that guides a novice through the topic.
"""
    return ""

def get_tone_guidance(tone):
    """Generates prompt guidance based on the selected tone."""
    if tone == "Formal":
        return "**Tone:** Professional, objective, and analytical. Avoid colloquialisms."
    elif tone == "Persuasive":
        return "**Tone:** Confident and compelling. Frame facts to support the central value proposition or argument."
    elif tone == "Informative":
        return "**Tone:** Neutral, clear, and educational. Focus on balance and completeness."
    return ""

def get_critical_instructions(classification, context_note=""):
    """
    Generates critical instructions tailored to the document classification.
    This is where we enforce the "Commercial" view for business docs.
    """
    
    # Defaults
    bullet_instruction = "4. **Bullets MUST be informative & concise.** Extract key facts from the text."
    elaboration_instruction = "5. **Elaboration:** Briefly explain the context of the bullet points."

    # --- 1. Financial & Strategic (The "Money" Docs) ---
    if classification in ["Financial Report (Annual/10-K/10-Q)", "Investment Analysis / Due Diligence Report", "Business Plan", "Marketing Plan/Proposal"]:
        bullet_instruction = """4. **Bullets MUST be Quantitative and Commercial.**
    *   **The Scoreboard:** You MUST extract specific numbers: Revenue, Net Income, Margins, Cash Flow, and **YoY Growth %**.
    *   **Segment Performance:** Break down performance by business unit (e.g., Software vs. Hardware). Who is the winner? Who is the loser?
    *   **Forward-Looking:** Extract specific guidance numbers (e.g., "Expect $10B FCF in 2025").
    *   **Ignore Boilerplate:** Do NOT create bullets for general "Risk Factors" or "Internal Controls" unless a specific, non-standard threat is detailed."""
        elaboration_instruction = """5. **Elaboration:** Connect the dots. Why did revenue drop? (e.g., "Due to divestiture of X"). Why is the margin improving? (e.g., "Shift to software mix"). Explain the *business driver* behind the number."""

    # --- 2. Legal (The "Risk" Docs) ---
    elif classification in ["Contract/Agreement", "Terms of Service (ToS)", "SLA", "Legal Case Brief"]:
        bullet_instruction = """4. **Bullets MUST focus on Rights, Obligations, and Anomalies.**
    *   **Hard Dates & Dollars:** Payment terms, termination dates, liability caps (specific $ amounts).
    *   **The "Gotchas":** Exclusions, indemnities, and non-standard restrictions.
    *   **Standard vs. Strange:** Highlight clauses that seem restrictive or unusual."""
        elaboration_instruction = "5. **Elaboration:** Explain the practical implication. (e.g., 'This liability cap implies we carry the risk for data breaches above $1M')."

    # --- 3. Technical (The "Builder" Docs) ---
    elif classification in ["System Design Document", "Python Source Code", "Technical Report/Documentation"]:
        bullet_instruction = """4. **Bullets MUST be Technical and Structural.**
    *   **Architecture:** Components, data flow, patterns used.
    *   **Stack:** Specific languages, libraries, APIs.
    *   **Constraints:** Latency requirements, storage limits, security protocols."""
        
    # --- 4. Resume/CV (The "Hiring" Docs) ---
    elif classification == "Resume/CV":
        bullet_instruction = """4. **Bullets MUST be Outcome-Based (STAR Method).**
    *   **Metrics:** "$10M revenue," "20% efficiency gain," "Managed 15 people."
    *   **Impact:** What changed because this person was there?
    *   **Skills in Context:** Don't just list skills; show where they were applied."""

    return f"""
**CRITICAL INSTRUCTIONS:**
1. Generate slides summarizing **ONLY** the provided extracted text.
2. **ALL fields (Title, Key Message, Bullets, Notes, Elaboration, Suggestions) ARE REQUIRED.**
3. **Use `---` on its own line ONLY as separator BETWEEN slides.**
{bullet_instruction}
{elaboration_instruction}
6. **Structure/Slide Count:** Follow specific guidance below for '{classification}'.
7. **DO NOT Synthesize:** Base output *solely* on the provided text.
8. {context_note}
"""

# --- Build Generation Prompt ---
def build_generation_prompt(
    document_text, classification, filename,
    is_part_of_multi_doc_request=False,
    total_docs_in_request=1,
    truncated=False,
    template_name='professional',
    audience="Executives",
    tone="Informative"
):
    """Builds the final, persona-driven prompt."""

    source_identifier = f"'{filename}'"
    
    # Context note for multi-document requests
    context_note = ""
    if is_part_of_multi_doc_request and total_docs_in_request > 1:
         context_note = f"This document is part of a larger request involving {total_docs_in_request} sources. Summarize *this specific document* but note connections."

    truncation_warning = ""
    if truncated or classification in ["Financial Report (Annual/10-K/10-Q)", "Reddit Thread"]:
        truncation_warning = "**NOTE: Text is truncated/incomplete. Summarize based ONLY on what is present. Do not hallucinate missing data.**\n"

    # Tailoring Blocks
    audience_block = get_audience_guidance(audience)
    tone_block = get_tone_guidance(tone)
    critical_block = get_critical_instructions(classification, context_note)

    base_instructions = f"""
You are an expert Strategy Consultant and Presentation Designer. Your task is to analyze the provided text from {source_identifier} (Class: {classification}) and generate a high-impact presentation.

{truncation_warning}
**Context:**
**Target Audience:** {audience}
**Desired Tone:** {tone}
**Style:** '{template_name.capitalize()}'

{audience_block}
{tone_block}
{critical_block}
"""

    # --- Classification-Specific Guidance (The "Playbook") ---
    specific_guidance = ""

    if classification == "Financial Report (Annual/10-K/10-Q)":
        specific_guidance = """
**Financial Report Playbook (The "CRO/Investor" View):**
*   **Slide 1: The Scoreboard (Executive Summary).** Title: "FY Performance Snapshot". Key Message: The one-sentence narrative of the year (e.g., "Growth driven by Software, offset by Infrastructure"). Bullets: Revenue ($ & YoY%), Net Income/EPS, Free Cash Flow.
*   **Slide 2: Segment Deep Dive.** Title: "Performance by Segment". Key Message: Where is the growth coming from? Bullets: Break down Revenue/Profit for key units (e.g., Software, Consulting, Infrastructure). Use specific numbers from tables.
*   **Slide 3: The Narrative & Strategy.** Title: "Strategic Pivot & Drivers". Key Message: What is management doing? (e.g., "Focusing on AI/Hybrid Cloud"). Bullets: Key acquisitions, divestitures, or product launches mentioned.
*   **Slide 4: Headwinds & Risks.** Title: "Commercial Risks". Key Message: What could stop the growth? Bullets: Currency impacts, specific competitive threats, or supply chain issues mentioned in MD&A. **IGNORE generic boilerplate risks.**
*   **Slide 5: Outlook.** Title: "Forward Guidance". Key Message: Management's target. Bullets: Revenue/FCF targets for the next fiscal year.
"""
    elif classification == "Reddit Thread":
        specific_guidance = """
**Reddit Thread Playbook:**
*   **Slide 1: The Core Question.** Summary of the OP (Original Post).
*   **Slide 2: The Consensus.** Is there one? (e.g., "YTA", "Buy", "Don't do it").
*   **Slide 3: Key Arguments (Pro).** The strongest points made by top commenters.
*   **Slide 4: Key Arguments (Con).** The counter-points.
*   **Slide 5: The "Niche" Insight.** A unique but valuable perspective buried in the comments.
*   **Note:** Do not invent vote counts. Infer sentiment from text.
"""
    elif classification == "Resume/CV":
        specific_guidance = """
**Resume Playbook (Hiring Manager View):**
*   **Slide 1: Candidate Profile.** Name + The "One Liner" value prop.
*   **Slide 2: The Highlights Reel.** Top 3 quantifiable achievements across entire career.
*   **Slide 3: Recent Experience.** Role & Impact. Focus on *results* not *tasks*.
*   **Slide 4: Skills & Tech.** Grouped logically (e.g., Languages, Frameworks, Leadership).
"""
    elif classification == "News Article/Blog Post" or classification == "Web Page Content":
        specific_guidance = """
**Article/Web Playbook:**
*   **Slide 1: Headline & Lede.** What happened?
*   **Slide 2: The "Why It Matters".** Contextualize the news.
*   **Slide 3: Key Details/Data.** The supporting evidence.
*   **Slide 4: Key Quotes.** Who said what?
*   **Slide 5: Conclusion/Next Steps.**
"""
    else: # Default
        specific_guidance = """
**General Document Playbook:**
1. **Overview:** The "Bottom Line Up Front" (BLUF).
2. **Key Theme 1:** Deep dive into the first major section.
3. **Key Theme 2:** Deep dive into the second major section.
4. **Key Data/Evidence:** specific stats or facts found.
5. **Conclusion:** Summary of findings or next steps.
"""

    # --- Assemble Final Prompt ---
    prompt = f"""
{base_instructions}

{specific_guidance}

**Source Text:**
\"\"\"
{document_text}
\"\"\"

**Generate the complete slide deck now.** Start immediately with the first slide block.
"""
    return prompt