# prompts.py
import logging
import re
from urllib.parse import urlparse # To help identify reddit URLs

# --- Constants ---
MAX_INPUT_CHARS = 3000000 # Applies PER document / web page

# --- Updated Classification Categories ---
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
    # --- Added New Categories ---
    "Legal Case Brief",
    "Legislative Bill/Regulation",
    "Business Plan",
    "SWOT Analysis Document",
    "Press Release",
    "System Design Document",
    "User Story / Feature Requirement Document",
    "Medical Journal Article",
    # --- End Added New Categories ---
    "Other",
]

# --- Get Classification Prompt ---
def get_classification_prompt(document_text_excerpt):
    """Creates a prompt specifically for classifying the document text excerpt."""
    max_excerpt_chars = 100000
    truncated_excerpt = document_text_excerpt[:max_excerpt_chars]
    categories_str = "\n - ".join(CLASSIFICATION_CATEGORIES)
    # Added keywords for new categories
    prompt = f"""
Analyze the following text excerpt. Based *only* on the content and structure, classify the document type. Pay close attention to common sections or keywords relevant to the categories (e.g.,
"Experience" for Resumes, "Claims" for Patents, `def`/`class`/`import` for Python Code, "Service Level" for SLAs, "Findings" for Case Studies,
"Financial Statements", "MD&A", "10-K", "Annual Report", "Risk Factors" for Financial Reports, "comments"/"r/" for Reddit Threads,
"versus"/"v."/"holding" for Legal Case Briefs, "Section"/"Article"/"Be it enacted" for Legislative Bills/Regulations,
"Executive Summary"/"Market Analysis"/"Financial Projections" for Business Plans, explicit "Strengths"/"Weaknesses"/"Opportunities"/"Threats" lists for SWOT Analysis,
"FOR IMMEDIATE RELEASE"/"Contact:" for Press Releases, "Architecture"/"Components"/"API Specification" for System Design Documents,
"As a"/"I want"/"Acceptance Criteria" for User Stories/Feature Requirements, "Abstract"/"Methods"/"Results"/"PICO" for Medical Journal Articles).
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
    """
    Extracts the classification category from the LLM's response,
    with fuzzy matching and specific checks.
    """
    potential_category = llm_response_text.strip()
    # Allow more chars for cleaning, but still limit to prevent abuse
    cleaned_category = ''.join(filter(lambda char: char.isalnum() or char in [' ', '(', ')', '/', '-', ',', ':'], potential_category[:100])).strip()
    cleaned_lower = cleaned_category.lower()

    # --- Heuristic Check 1: Check source_identifier (e.g., filename, URL) ---
    source_lower = source_identifier.lower()
    if "10-k" in source_lower or "10k" in source_lower or "annual_report" in source_lower or "annual report" in source_lower or "10-q" in source_lower or "10q" in source_lower:
         logging.info(f"Classified as 'Financial Report (Annual/10-K/10-Q)' based on source identifier: {source_identifier}")
         return "Financial Report (Annual/10-K/10-Q)"
    if 'reddit.com' in source_lower:
        try: # Check Reddit path structure
            parsed_url = urlparse(source_identifier)
            path_parts = [part for part in parsed_url.path.split('/') if part]
            if len(path_parts) >= 4 and path_parts[0].lower() == 'r' and path_parts[2].lower() == 'comments':
                logging.info(f"Classified as 'Reddit Thread' based on URL structure: {source_identifier}")
                return "Reddit Thread"
        except Exception: pass # Ignore parsing errors
    if any(kw in source_lower for kw in ["swot_analysis", "swot.docx", "swot.pdf"]):
        logging.info(f"Classified as 'SWOT Analysis Document' based on source identifier: {source_identifier}")
        return "SWOT Analysis Document"
    if any(kw in source_lower for kw in ["press_release", "release.docx", "for_immediate_release"]):
        logging.info(f"Classified as 'Press Release' based on source identifier: {source_identifier}")
        return "Press Release"
    if any(kw in source_lower for kw in ["medical_journal", "pubmed", "lancet", "nejm", "jama"]) or "doi.org" in source_lower:
        logging.info(f"Classified as 'Medical Journal Article' based on source identifier: {source_identifier}")
        return "Medical Journal Article"


    # --- Heuristic Check 2: Check LLM response directly (Exact/Cleaned) ---
    for cat in CLASSIFICATION_CATEGORIES:
        if cat.lower() == cleaned_lower:
            logging.info(f"Classified as: '{cat}' (Exact match from LLM)")
            # Override checks
            if cat == "Reddit Thread" and "reddit.com" not in source_lower: logging.warning(f"LLM classified as Reddit but source doesn't look like Reddit: {source_identifier}");
            if cat in ["Web Page Content", "News Article/Blog Post"] and "reddit.com" in source_lower: logging.info(f"Overriding LLM '{cat}' to 'Reddit Thread' based on URL."); return "Reddit Thread"
            if cat in ["General Business Document", "Technical Report/Documentation"] and ("10k" in source_lower or "annual_report" in source_lower or "10q" in source_lower): logging.info(f"Overriding LLM '{cat}' to 'Financial Report' based on filename."); return "Financial Report (Annual/10-K/10-Q)"
            return cat # Return the matched category
    if cleaned_category in CLASSIFICATION_CATEGORIES: # Check cleaned category directly against list
         logging.info(f"Classified as: '{cleaned_category}' (Cleaned match from LLM)")
         # Apply overrides here too
         if cleaned_category in ["Web Page Content", "News Article/Blog Post"] and "reddit.com" in source_lower: logging.info(f"Overriding LLM '{cleaned_category}' to 'Reddit Thread' based on URL."); return "Reddit Thread"
         if cleaned_category in ["General Business Document", "Technical Report/Documentation"] and ("10k" in source_lower or "annual_report" in source_lower or "10q" in source_lower): logging.info(f"Overriding LLM '{cleaned_category}' to 'Financial Report' based on filename."); return "Financial Report (Annual/10-K/10-Q)"
         return cleaned_category

    logging.warning(f"LLM class '{potential_category}' not exact match. Fuzzy matching...")

    # --- Heuristic Check 3: Specific Keyword Checks in LLM Response ---
    # Keep this as a fallback if cleaned_category isn't an exact list member
    if "financial statement" in cleaned_lower or "10-k" in cleaned_lower or "annual report" in cleaned_lower or "md&a" in cleaned_lower or "10-q" in cleaned_lower or "shareholder letter" in cleaned_lower:
         logging.info(f"Matched 'Financial Report (Annual/10-K/10-Q)' (Keywords)")
         return "Financial Report (Annual/10-K/10-Q)"
    if "reddit" in cleaned_lower or "subreddit" in cleaned_lower or "upvote" in cleaned_lower:
        logging.info(f"Matched 'Reddit Thread' (Keywords)")
        return "Reddit Thread"
    if ("web page" in cleaned_lower or "article" in cleaned_lower or "blog post" in cleaned_lower) and "reddit.com" not in source_lower:
         logging.info(f"Matched 'Web Page Content' or similar (Keywords)")
         # More precise fallback if not exact match
         if "news" in cleaned_lower or "blog" in cleaned_lower: return "News Article/Blog Post"
         return "Web Page Content"
    if "python" in cleaned_lower or ("code" in cleaned_lower and ("script" in cleaned_lower or "source" in cleaned_lower)):
        logging.info(f"Matched 'Python Source Code' (Keywords)"); return "Python Source Code"
    if "case study" in cleaned_lower or "research report" in cleaned_lower or "trial results" in cleaned_lower or "findings report" in cleaned_lower:
         logging.info(f"Matched 'Case Study / Research Report' (Keywords)"); return "Case Study / Research Report"
    if "resume" in cleaned_lower or "cv" in cleaned_lower or "curriculum vitae" in cleaned_lower:
        logging.info(f"Matched 'Resume/CV' (Keywords)"); return "Resume/CV"
    if "patent" in cleaned_lower:
         logging.info(f"Matched 'Patent' (Keywords)"); return "Patent"
    if "sla" in cleaned_lower or "service level" in cleaned_lower:
         logging.info(f"Matched 'Service Level Agreement (SLA)' (Keywords)"); return "Service Level Agreement (SLA)"
    if (("terms" in cleaned_lower and "service" in cleaned_lower) or "tos" in cleaned_lower or "user agreement" in cleaned_lower) and "agreement" not in cleaned_lower :
         logging.info(f"Matched 'Terms of Service (ToS)' (Keywords)"); return "Terms of Service (ToS)"
    if "privacy" in cleaned_lower and "policy" in cleaned_lower:
        logging.info(f"Matched 'Privacy Policy' (Keywords)"); return "Privacy Policy"
    if "contract" in cleaned_lower or ("agreement" in cleaned_lower and "service level" not in cleaned_lower and "user agreement" not in cleaned_lower):
        logging.info(f"Matched 'Contract/Agreement' (Keywords)"); return "Contract/Agreement"
    if "guide" in cleaned_lower or "manual" in cleaned_lower or "how to" in cleaned_lower:
         logging.info(f"Matched 'Informational Guide/Manual' (Keywords)"); return "Informational Guide/Manual"
    if "technical report" in cleaned_lower or "documentation" in cleaned_lower or "specifications" in cleaned_lower:
         logging.info(f"Matched 'Technical Report/Documentation' (Keywords)"); return "Technical Report/Documentation"

    # Keywords for new categories
    if "case brief" in cleaned_lower or "legal brief" in cleaned_lower or " v. " in cleaned_lower or " versus " in cleaned_lower or "holding" in cleaned_lower:
        logging.info(f"Matched 'Legal Case Brief' (Keywords)"); return "Legal Case Brief"
    if "bill" in cleaned_lower or "act" in cleaned_lower and "fact" not in cleaned_lower or "statute" in cleaned_lower or "regulation" in cleaned_lower and "financial" not in cleaned_lower: # Avoid "financial regulation"
        logging.info(f"Matched 'Legislative Bill/Regulation' (Keywords)"); return "Legislative Bill/Regulation"
    if "business plan" in cleaned_lower or "financial model" in cleaned_lower and "company" in cleaned_lower or "startup plan" in cleaned_lower:
        logging.info(f"Matched 'Business Plan' (Keywords)"); return "Business Plan"
    if "swot" in cleaned_lower or ("strengths" in cleaned_lower and "weaknesses" in cleaned_lower and "opportunities" in cleaned_lower and "threats" in cleaned_lower):
        logging.info(f"Matched 'SWOT Analysis Document' (Keywords)"); return "SWOT Analysis Document"
    if "press release" in cleaned_lower or "for immediate release" in cleaned_lower or "news release" in cleaned_lower:
        logging.info(f"Matched 'Press Release' (Keywords)"); return "Press Release"
    if "system design" in cleaned_lower or "architecture document" in cleaned_lower or "sdd" == cleaned_lower: # sdd should be exact
        logging.info(f"Matched 'System Design Document' (Keywords)"); return "System Design Document"
    if "user story" in cleaned_lower or ("feature" in cleaned_lower and "requirement" in cleaned_lower) or "acceptance criteria" in cleaned_lower:
        logging.info(f"Matched 'User Story / Feature Requirement Document' (Keywords)"); return "User Story / Feature Requirement Document"
    if "medical journal" in cleaned_lower or "clinical study" in cleaned_lower or "pico" in cleaned_lower or "systematic review" in cleaned_lower or "meta-analysis" in cleaned_lower or "abstract" in cleaned_lower and "methods" in cleaned_lower and "results" in cleaned_lower:
        logging.info(f"Matched 'Medical Journal Article' (Keywords)"); return "Medical Journal Article"


    # --- Heuristic Check 4: Fuzzy 'in' check (Less reliable, last resort) ---
    for cat in CLASSIFICATION_CATEGORIES:
        cat_lower = cat.lower()
        # Avoid fuzzy matching less specific types if keywords for more specific types exist
        if cat in ["Web Page Content", "News Article/Blog Post"] and ("reddit" in cleaned_lower or "reddit.com" in source_lower): continue
        if cat == "General Business Document" and ("financial statement" in cleaned_lower or "10-k" in cleaned_lower or "annual report" in cleaned_lower): continue
        if cat == "Technical Report/Documentation" and "code" in cleaned_lower: continue # Don't confuse code with tech docs via fuzzy match

        # Simple check: if the cleaned category contains the category lowercased, or vice versa, within reason
        if cat_lower in cleaned_lower or cleaned_lower in cat_lower: # Removed length check for now, simple inclusion is more robust
             logging.info(f"Matched '{cat}' (Fuzzy 'in' check)")
             # Apply overrides here too
             if cat in ["Web Page Content", "News Article/Blog Post"] and "reddit.com" in source_lower: logging.info(f"Overriding fuzzy '{cat}' to 'Reddit Thread' based on URL."); return "Reddit Thread"
             if cat in ["General Business Document", "Technical Report/Documentation"] and ("10k" in source_lower or "annual_report" in source_lower or "10q" in source_lower): logging.info(f"Overriding fuzzy '{cat}' to 'Financial Report' based on filename."); return "Financial Report (Annual/10-K/10-Q)"
             return cat

    logging.warning(f"Could not reliably classify '{potential_category}'. Falling back to 'Other'.")
    return "Other"

# --- Guidance Blocks (New Functions) ---

def get_audience_guidance(audience):
    """Generates prompt guidance based on the selected audience."""
    guidance = ""
    if audience == "Executives":
        guidance = """
**Audience Guidance: Executives**
*   **Prioritization:** Focus on high-level insights, strategic implications, key performance indicators (KPIs), business impact, future trends, and major risks/opportunities.
*   **Detail Level:** Keep explanations concise and high-level. Avoid deep technical or minor operational details unless they have significant strategic relevance.
*   **Language:** Use clear, business-oriented language. Summarize complex topics effectively.
*   **Key Message:** Each key message should clearly state the core takeaway or strategic significance of the slide's content for decision-makers.
*   **Elaboration:** Explain the 'so what?' – why is this information important for executives? What are the implications?
*   **Suggestions:** Suggest visuals that show trends, summaries (tables, dashboards), or strategic concepts. Enhancement/Best Practice tips should focus on strategic context, impact, or next steps for leadership.
"""
    elif audience == "Technical Team":
        guidance = """
**Audience Guidance: Technical Team**
*   **Prioritization:** Focus on technical details, implementation specifics, architecture, methodology, specific components/functions, dependencies, challenges, and technical considerations.
*   **Detail Level:** Provide sufficient technical detail to understand the underlying mechanisms. Use accurate technical terms.
*   **Language:** Use precise, technical language appropriate for domain experts.
*   **Key Message:** Each key message should state the core technical function, challenge, or solution presented on the slide.
*   **Elaboration:** Explain *how* something works, the technical reasoning, trade-offs, or underlying technical context based on the text.
*   **Suggestions:** Suggest visuals showing architecture diagrams, code snippets, data flows, technical comparisons, or system structures. Enhancement/Best Practice tips should focus on implementation details, testing, debugging, or technical best practices.
"""
    elif audience == "General":
        guidance = """
**Audience Guidance: General Audience**
*   **Prioritization:** Focus on the main concepts, overall purpose, key benefits, and user-facing aspects.
*   **Detail Level:** Keep explanations simple and accessible. Avoid jargon where possible, or define it clearly if necessary.
*   **Language:** Use plain, easy-to-understand language. Maintain a logical flow that is easy for someone new to the topic to follow.
*   **Key Message:** Each key message should clearly state the main idea or takeaway for a general audience.
*   **Elaboration:** Explain concepts simply, provide real-world analogies if appropriate (based on text), or clarify terms.
*   **Suggestions:** Suggest visuals that are simple and illustrative (icons, basic diagrams, charts explaining concepts). Enhancement/Best Practice tips should focus on clarity, simplicity, engaging presentation, and addressing common questions.
"""
    # Add guidance for other potential audiences here if you expand options
    return guidance

def get_tone_guidance(tone):
    """Generates prompt guidance based on the selected tone."""
    guidance = ""
    if tone == "Formal":
        guidance = """
**Tone Guidance: Formal**
*   **Style:** Maintain a strictly professional, objective, and serious tone. Use formal vocabulary and sentence structures.
*   **Content:** Present information factually and analytically. Avoid colloquialisms, exclamation points, or emotionally charged language.
*   **Language:** Ensure all language is precise and unambiguous.
"""
    elif tone == "Persuasive":
        guidance = """
**Tone Guidance: Persuasive**
*   **Style:** Adopt a confident and convincing tone. Use language that highlights benefits, opportunities, or the importance of taking action.
*   **Content:** Frame information strategically to support a central argument or call to action (if one exists in the text). Emphasize positive outcomes or solutions.
*   **Language:** Use active voice. Employ strong but professional vocabulary.
"""
    elif tone == "Informative":
        guidance = """
**Tone Guidance: Informative**
*   **Style:** Maintain a neutral, objective, and clear tone. The primary goal is to educate and explain.
*   **Content:** Present facts, procedures, and explanations thoroughly and logically. Ensure accuracy and cover key details.
*   **Language:** Use clear, straightforward language. Focus on being easy to understand and comprehensive.
"""
    # Add guidance for other potential tones here if you expand options
    return guidance

# --- Build Generation Prompt (Includes ALL Guidance Blocks) ---
def build_generation_prompt(
    document_text, classification, filename,
    is_part_of_multi_doc_request=False,
    total_docs_in_request=1,
    truncated=False, template_name='professional',
    audience="", tone=""
):
    """Builds the detailed generation prompt tailored for summarizing the source."""

    # Determine source type based on classification
    source_type = "Reddit Thread" if classification == "Reddit Thread" \
             else "Web Page" if classification in ["Web Page Content", "News Article/Blog Post"] \
             else "Financial Report" if classification == "Financial Report (Annual/10-K/10-Q)" \
             else "Legal Document" if classification in ["Legal Case Brief", "Legislative Bill/Regulation", "Terms of Service (ToS)", "Service Level Agreement (SLA)", "Contract/Agreement", "Privacy Policy", "Patent"] \
             else "Business Document" if classification in ["Business Plan", "SWOT Analysis Document", "Press Release", "Marketing Plan/Proposal", "Resume/CV"] \
             else "Technical Document" if classification in ["System Design Document", "User Story / Feature Requirement Document", "Python Source Code", "Technical Report/Documentation"] \
             else "Academic/Research Document" if classification in ["Medical Journal Article", "Academic Paper/Research", "Case Study / Research Report"] \
             else "Document" # Default to Document for others like Informational Guide/Manual, Meeting Notes
    source_identifier = f"'{filename}'"

    logging.info(f"Building generation prompt for {source_type}: {source_identifier} (Class: '{classification}', Truncated: {truncated}, Audience: '{audience or 'Default'}', Tone: '{tone or 'Default'}')")

    # Context note for multi-document requests
    context_note = ""
    if is_part_of_multi_doc_request and total_docs_in_request > 1:
         context_note = f"This document is part of a larger request involving {total_docs_in_request} sources. Summarize *this specific document's* content, but be mindful of its potential relation to other documents (e.g., if it's an appendix or a chapter)."

    truncation_warning = f"**IMPORTANT NOTE: Text extracted from the {source_type} might be truncated or incomplete due to extraction limits."
    if classification == "Reddit Thread": truncation_warning += " Discussion context, full comment threads, and vote counts are likely unavailable."
    if classification == "Financial Report (Annual/10-K/10-Q)" : truncation_warning += " Full financial statement details and notes might be incomplete."
    if classification == "Medical Journal Article": truncation_warning += " Full methodologies or supplementary data may be incomplete."
    truncation_warning += f" Summary must be based *solely on text provided*.**\n" if truncated or classification in ["Reddit Thread", "Financial Report (Annual/10-K/10-Q)", "Medical Journal Article"] else ""
    # Ensure warning for Reddit too, even if not truncated, due to inherent limitations
    if not truncated and classification == "Reddit Thread":
        truncation_warning = f"**IMPORTANT NOTE: Text extracted from the {source_type} is based on web page content. Discussion context, full comment threads, and vote counts are likely unavailable. Summary must be based *solely on text provided*.**\n"


    # --- Define Default Audience/Tone (Used if user doesn't select) ---
    default_audience = "General Audience"
    default_tone = "Informative and Objective"

    # Classification-specific defaults (used ONLY if user did *not* select)
    cls_defaults = {
        "Patent": ("Technical Reviewer, Legal Counsel", "Precise, Technical, Formal"),
        "Resume/CV": ("Hiring Manager, Recruiter", "Professional, Achievement-Oriented"),
        "Python Source Code": ("CTO, Engineering Manager", "Technical Summary, Concise"),
        "Case Study / Research Report": ("Executives, Stakeholders", "Insightful, Data-driven, Clear"),
        "Informational Guide/Manual": ("Users, Trainees", "Clear, Informative, Structured"),
        "Terms of Service (ToS)": ("Legal/Business Teams", "Precise, Legally Focused"),
        "Service Level Agreement (SLA)": ("Operations Teams, Client Reviewers", "Quantitative, Precise"),
        "Privacy Policy": ("General Users, Legal/Compliance", "Clear, Transparent"),
        "Contract/Agreement": ("Legal Reviewers, Business Stakeholders", "Formal, Precise, Objective"),
        "News Article/Blog Post": ("General Reader", "Informative, Engaging"),
        "Web Page Content": ("General Web Visitor", "Informative, Clear"),
        "Reddit Thread": ("Someone interested in the discussion", "Objective Summary, Nuanced"),
        "Financial Report (Annual/10-K/10-Q)": ("Executive Reviewer, Investor", "Concise, Data-Driven, Strategic"),
        # New Defaults
        "Legal Case Brief": ("Legal Professionals, Law Students", "Formal, Analytical, Precise"),
        "Legislative Bill/Regulation": ("Policy Analysts, Affected Parties, Legal Teams", "Formal, Objective, Clear"),
        "Business Plan": ("Investors, Lenders, Management", "Persuasive, Professional, Clear"),
        "SWOT Analysis Document": ("Strategic Planners, Management", "Objective, Structured, Concise"),
        "Press Release": ("Journalists, Public, Investors", "Factual, Clear, Concise"),
        "System Design Document": ("Engineering Managers, Architects, Developers", "Technical, Precise, Structured"),
        "User Story / Feature Requirement Document": ("Agile Development Teams, Product Owners", "Clear, Actionable, Concise"),
        "Medical Journal Article": ("Healthcare Professionals, Researchers", "Scientific, Precise, Objective"),
    }
    cls_audience, cls_tone = cls_defaults.get(classification, (default_audience, default_tone))

    # Use user selection if available, otherwise classification default, otherwise general default
    final_audience_label = audience if audience else cls_audience
    final_tone_label = tone if tone else cls_tone

    # --- Build Tailoring Instructions Blocks (using user selection if available) ---
    # Only add specific guidance if a concrete option was selected by the user
    audience_guidance_block = get_audience_guidance(audience) if audience in ["Executives", "Technical Team", "General"] else ""
    tone_guidance_block = get_tone_guidance(tone) if tone in ["Formal", "Persuasive", "Informative"] else ""

    tailoring_instructions = ""
    if audience_guidance_block or tone_guidance_block:
        tailoring_instructions = "**Tailoring Instructions:**\n"
        if audience_guidance_block: tailoring_instructions += audience_guidance_block
        if tone_guidance_block: tailoring_instructions += tone_guidance_block

    # --- Base Prompt Structure ---
    base_instructions = f"""
You are an expert presentation designer creating a **concise summary presentation** based *only* on the provided text extracted from a {source_type} identified by {source_identifier}, classified as '{classification}'. Follow the tailoring instructions below and classification-specific guidance. Highlight the most critical information from the text relevant to the target audience.

{truncation_warning}
**Source Context:**
**Identifier:** {source_identifier}
**Content Type:** {classification} ({source_type})
**Target Audience (Selected or Default):** {final_audience_label}
**Desired Tone (Selected or Default):** {final_tone_label}
**Visual Style Hint:** '{template_name.capitalize()}' theme.

{tailoring_instructions}

**CRITICAL INSTRUCTIONS:**
1. Generate slides summarizing **ONLY** the provided extracted text. **Prioritize information relevant to the Target Audience.**
2. **ALL fields (Slide Title, Content Type, Key Message, Bullets, Visual Suggestion, Design Note, Notes, Elaboration, Enhancement Suggestion, Best Practice Tip) ARE REQUIRED per slide.** Content MUST derive *directly* from source text. Use 'None'/'N/A' sparingly for suggestions *if truly nothing relevant can be inferred*. Field labels MUST be present. If specific details (like exact numbers or vote counts) are missing from the text, state that or infer importance/trends from language/repetition where appropriate and note the inference (e.g., "Trend suggests increase [based on discussion]").
3. **Use `---` on its own line ONLY as separator BETWEEN slides.**
4. **Bullets MUST be informative & concise.** Extract key facts/KPIs/arguments/points relevant to the slide's topic *from the extracted text*. Adapt number/length based on guidance.
5. Elaboration: Briefly explain significance/context based *only* on the extracted text. For discussions/financials, explain *why* this point/metric matters to the **target audience**.
6. Enhancement/Best Practice: Actionable advice relevant to presenting this *specific content* to the target audience, based on the content and desired tone.
7. **Structure/Slide Count:** Follow specific guidance below for '{classification}'. Ensure logical flow, appropriate detail level for the audience. **Prioritize creating slides for the MANDATORY sections listed in the guidance.**
8. **DO NOT Synthesize:** Base output *solely* on the provided text. Do not invent information not present.
9. **Security Note for Code:** If processing code, analyze as text ONLY. DO NOT execute. Highlight potential security considerations *mentioned* in code/comments.
10. {context_note} # Include multi-doc context if applicable

**Required Slide Block Format:**
---
Slide Title: [Concise Title derived from text, relevant to audience]
Content Type: [E.g., Financial Highlights / Strategic Overview / Segment Performance / Risk Summary / Key Discussion Points / Main Themes / Code Snippet / Legal Issue / Bill Provision / Market Analysis / System Component / Feature Details / Study Findings]
Key Message: [**Single sentence core takeaway** of this slide for the target audience, from the text.]
- [Bullet 1: Key point/metric/argument from the text. Include YoY % change if available for financial metrics.]
- [...] (Adapt bullets per guidance, prioritize KPIs for financial reports)
Visual Suggestion: [Actionable suggestion. E.g., "KPI Table", "Trend Chart Concept", "Pull quote", "Segment Icon", "Risk Matrix Concept", "Flowchart of Process", "Architecture Diagram Snippet", "User Journey Map Idea"]
Design Note: [Optional: e.g., 'Highlight YoY changes', 'Use company branding elements', 'Emphasize clarity for legal text'.]
Notes: [Optional: e.g., 'Source: MD&A p.5', 'Source: Risk Factors', 'Ref: GAAP/Non-GAAP', 'Recurring comment theme', 'Clause X.Y', 'Section Z', 'Data from Table A'].
**Elaboration:** [REQUIRED: Explain significance/context based *only* on the text. Why does this matter to the audience?]
**Enhancement Suggestion:** [REQUIRED: Actionable idea for presenting THIS content. E.g., "Compare YoY", "Add industry benchmark if known", "Link to strategy", "Cross-reference with Clause A.B", "Suggest next steps for development team"].
**Best Practice Tip:** [REQUIRED: Presentation advice for THIS content/audience. E.g., "Focus on the story", "Keep financial details clear", "Acknowledge assumptions", "Ensure legal precision", "Use visuals to simplify complex systems"].
--- [Separator ONLY between slides]
...[Next slide]...
"""

    # --- Classification-Specific Guidance (Remains largely the same, acts as fallback/structure guide) ---
    specific_guidance = ""

    # --- REFINED FINANCIAL REPORT GUIDANCE ---
    if classification == "Financial Report (Annual/10-K/10-Q)":
        specific_guidance = """
**Financial Report (Annual/10-K/10-Q) Specific Guidance:**
*   **Goal:** Create an executive-level summary focusing on overall financial performance, strategic highlights, key segment results, major risks, and outlook/guidance if provided. Prioritize Key Performance Indicators (KPIs), Year-over-Year (YoY) comparisons, strategic narrative, risks, and outlook.
*   **Target Audience Focus (Default for this type):** Executive Reviewer, Investor. Need high-level understanding, key trends, strategic direction, and major concerns quickly. (This can be *overridden* by user selection, but provides context).
*   **Mandatory Sections (Generate slides for these first):**
    1.  **Executive Summary & Financial Highlights:** Must include KPIs like Revenue, Net Income/EPS (specify GAAP/Non-GAAP if mentioned), Free Cash Flow. **CRITICAL: Include Year-over-Year percentage change (%) for these KPIs if available in the text.** Use a Table concept visual.
    2.  **Key Risk Factors:** Must summarize the **top 2-4 most significant risks** explicitly mentioned (often in a dedicated "Risk Factors" section). Focus on the *nature* of the risk.
    3.  **Outlook / Guidance:** Must capture any forward-looking statements, financial targets, or qualitative guidance provided for future periods. State clearly if no explicit guidance is found in the text.
*   **Suggested Structure & Slide Count (Aim for ~8-12 slides total, prioritize mandatory sections):**
    *   **Slide 1 (Mandatory): Title Slide:** Company Name, Report Type (e.g., "2024 Annual Report Highlights"), Period Covered.
    *   **Slide 2 (Mandatory): Executive Summary & Financial Highlights:** Title: "Executive Summary & Key Financials". Key Message: Overall performance trend and outlook tone (e.g., "Strong growth driven by X, positive outlook"). Bullets: Extract **key KPIs** (Revenue, Net Income/EPS, FCF) **with YoY % changes if text provides them**. Visual: Suggest "KPI Table with YoY comparisons".
    *   **Slide 3 (Highly Recommended): Chairman/CEO Letter Highlights:** Title: "CEO/Chairman's Strategic Message". Key Message: Capture the main strategic theme or tone. Bullets: 2-4 key strategic priorities, achievements, or forward-looking statements from the letter. Visual: "Pull quote from letter".
    *   **Slide 4-5 (As Applicable): Business Segment Performance:** Title: "Segment Performance: [Segment Name]" or "Key Segment Highlights". Key Message: Summarize performance driver/trend for **major** segments. Bullets: Highlight Revenue (with YoY % change), and Operating Income/Margin trends **if mentioned**. Focus on segments discussed prominently. Visual: "Bar chart comparing segment revenue/growth" or "Table of segment KPIs".
    *   **Slide 6 (Optional but Recommended): Financial Position / Health:** Title: "Financial Position Highlights". Key Message: Key takeaway about balance sheet strength/changes. Bullets: Key figures like Cash & Equivalents, Total Debt (mention significant changes if discussed). Visual: "Simple Balance Sheet KPI comparison".
    *   **Slide 7 (Optional): MD&A Key Themes:** Title: "Management Discussion Highlights (MD&A)". Key Message: Summarize management's *explanation* for results/trends. Bullets: 2-4 key themes from MD&A text (e.g., impact of acquisitions, macroeconomic factors mentioned, productivity initiatives). Visual: "Icons representing themes".
    *   **Slide 8 (Mandatory): Key Risks Summary:** Title: "Key Risk Factors Summary". Key Message: Identify the category of top risks. Bullets: Summarize **top 2-4 significant risks** identified in the "Risk Factors" section of the text. Visual: "Risk icons" or "Simple risk matrix concept".
    *   **Slide 9 (Mandatory): Outlook / Guidance:** Title: "Company Outlook / Guidance". Key Message: State the core outlook. Bullets: List specific financial targets or qualitative statements if provided. *Explicitly state if no guidance was found in the provided text.* Visual: "Upward/downward trend arrows" or "Text focus".
*   **Content:** **Prioritize KPIs with YoY % changes.** Use specific numbers from the text. Summarize narratives concisely. Clearly label data sources (e.g., "Source: MD&A") in notes.
*   **Visuals:** Emphasize tables and charts for financial data comparison (KPIs, Segments). Use icons and simple diagrams for strategy/risks.
*   **Best Practice Tips:** Focus on the "so what?" for executives. Tell a clear story. Be precise with financial terms. Acknowledge limitations of extracted text (e.g., "Based on extracted text...").
        """
    # --- END: REFINED FINANCIAL REPORT GUIDANCE ---

    elif classification == "Reddit Thread":
        specific_guidance = """
**Reddit Thread Specific Guidance:**
*   **Goal:** Summarize the original post's (OP) main point/question and the key themes, arguments, sentiments, and notable points raised in the extracted comments. Focus on capturing the essence of the discussion.
*   **Important Caveat:** The provided text is extracted from a webpage and likely **DOES NOT CONTAIN RELIABLE VOTE COUNTS** or full comment nesting structure. Importance of points must be **inferred** from repetition, strong language, direct replies, or being presented as a distinct argument in the extracted text. Do NOT invent vote counts.
*   **Suggested Structure & Slide Count (Aim for ~6-10 slides):**
    1.  **Thread Topic & OP Summary:** Title: Use OP title if identifiable, otherwise "Reddit Thread Summary: [Topic]". Key Message: State the core question or statement from the Original Post (OP). Bullets: Summarize the OP's main points or context in 2-4 bullets. Note: Identify the OP based on context (usually the first main block of text).
    2.  **Key Discussion Theme 1:** Title: "Discussion Theme: [Identified Theme]". Key Message: Summarize the central idea of this recurring theme from the comments. Bullets: Provide 3-5 bullet points representing different facets or common arguments related to this theme found in the extracted comments.
    3.  **Key Discussion Theme 2 (Optional):** Repeat structure for another 1-2 major themes if clearly present and distinct in the comments.
    4.  **Prominent Viewpoints/Arguments (Multiple Slides Possible):** Title: "Viewpoint: [Concise description]" or "Argument: [Concise description]". Key Message: State the core argument or perspective clearly. Bullets: Use 2-4 bullets to capture the reasoning or supporting points *as presented in the comments*. Try to identify viewpoints that seem widely shared or strongly argued, based *only* on the text.
    5.  **Notable Comments/Insights (Optional):** Title: "Notable Comments/Insights". Key Message: Highlight specific interesting, unique, or frequently mentioned points from the comments that don't fit into broader themes. Bullets: Use 1-2 bullets per distinct point, perhaps paraphrasing or quoting briefly if text allows.
    6.  **Inferred Sentiment/Conclusion:** Title: "Overall Discussion Sentiment (Inferred)". Key Message: Based *only* on the language in the extracted comments, what is the general tone or conclusion? (e.g., "General agreement with OP", "Mixed opinions on feasibility", "Strong disagreement on ethics"). Bullets: Provide 2-3 observations supporting the inferred sentiment (e.g., "Multiple comments express skepticism", "Frequent use of positive language towards X", "No clear consensus reached in provided text"). *Acknowledge if sentiment is unclear or based on limited text.*
*   **Content:** Distinguish between the OP and comments where possible. Focus on summarizing arguments and themes. Use cautious language when inferring sentiment or importance due to lack of metadata.
*   **Visuals:** Suggest pull quotes for representative comments, icons for themes (e.g., lightbulb for idea, question mark for query, checkmark for agreement, X for disagreement), simple pro/con list concept if applicable.
*   **Best Practice Tips:** Clearly label slides distinguishing OP summary from comment summary. Acknowledge limitations (missing votes/nesting). Aim for objective representation of the discussion points found in the text. Avoid taking sides.
*   **Elaboration/Enhancement:** Focus these on explaining the *significance* of achievements or suggesting how the presenter could tailor the slide further for a specific job application (e.g., "Expand on AI/ML experience for AI roles").
        """
    elif classification == "Patent":
        specific_guidance = """
**Patent Specific Guidance:**
*   **Goal:** Create an executive summary highlighting the core invention, key claims, technical field, and assignee/inventors. Focus on novelty and scope.
*   **Suggested Structure & Slide Count (Aim for ~6-10 slides):**
    1.  **Title Slide:** Patent Title, Patent Number, Date of Patent, Assignee. (Use info from top of patent doc).
    2.  **Abstract Summary:** Key message summarizing the abstract provided in the patent. Bullets can break down key aspects mentioned in the abstract.
    3.  **Technical Field / Background:** Briefly explain the problem the invention solves or the technical area it belongs to (derived from Background/Field sections). Use 2-4 bullets.
    4.  **Core Invention Summary:** Explain the main concept/solution of the invention in relatively clear terms (derived from Summary/Detailed Description). Use 3-5 key bullets highlighting the novelty or core mechanism. Visual Suggestion: Key Figure from the patent drawings that best illustrates the core concept.
    5.  **Key Claims Overview:** Select and paraphrase 2-4 of the most important *independent* claims (usually claim 1 and potentially others) to capture the essential scope of the invention. Focus on *what* is claimed. Use clear bullets.
    6.  **Key Figures (Optional but Recommended):** Dedicate a slide to show 1-2 key figures with brief captions explaining what they illustrate (reference figure numbers).
    7.  **Inventors/Assignee:** List the inventors and the assignee company as stated on the patent document.
*   **Content:** Focus on technical accuracy and clearly explaining the invention's essence and scope based *only* on the provided text. Avoid excessive legal jargon where possible for a summary, but retain precision for claims.
*   **Visuals:** Suggest using figures directly from the patent document (placeholder text should reference Figure number, e.g., "Placeholder for Figure 1 from Patent"), icons for technical fields.
*   **Best Practice Tips:** Clarity, accuracy, focus on the core novelty/problem solved, use visuals from the patent effectively. Define technical terms if audience is mixed.
*   **Elaboration/Enhancement:** Explain the potential significance or application of the invention if mentioned, or suggest searching for related patents/prior art (as an external action).
        """
    elif classification == "Resume/CV":
        specific_guidance = """
**Resume/CV Specific Guidance (Hiring Manager/Recruiter Perspective):**
*   **Goal:** Create a compelling executive summary highlighting the candidate's qualifications, key experience, skills, and potential impact. Focus on information relevant to potential employers.
*   **Suggested Structure & Slide Count (Aim for ~8-15 slides total):**
    1.  **Title Slide:** Candidate Name, Current/Target Role Area (e.g., "Paul O'Hagan - AI Product Management Leader").
    2.  **Executive Summary / Profile:** Synthesize the resume's summary section into 3-4 impactful bullet points capturing the candidate's core value proposition, years of experience, and key areas of expertise.
    3.  **Key Skills Overview:** Group major skills logically (e.g., Technical Skills, Leadership Skills, Domain Expertise). Use the "Strengths Breakdown" section if available, otherwise extract from the entire resume. Icons can be effective here. (1-2 slides)
    4.  **Career Highlights / Trajectory:** Showcase major achievements or a timeline of key roles/promotions. Pull from the most impressive parts of the experience or dedicated "Highlights" sections (like patents, major product launches). (1-2 slides)
    5.  **Recent/Relevant Experience:** Dedicate slides to the *most recent 2-3 roles*. For each role:
        *   Slide Title: Role Title @ Company Name (Dates Optional).
        *   Key Message: Summarize the core responsibility or biggest impact in that role.
        *   Bullets: Extract **3-5 key achievements or responsibilities**, focusing on *impact and quantifiable results* where possible (e.g., "Grew revenue by $XM", "Led team of X", "Launched X product"). Do *not* just list all resume bullets. Synthesize and select. (2-4 slides total)
    6.  **Key Accomplishments (Optional but Recommended):** If distinct sections like "Patents," "Publications," "Projects," or "Awards" exist, create a dedicated slide highlighting these. (1 slide)
    7.  **Education/Certifications (Optional):** Briefly list key degrees or certifications if relevant to the target audience/role. (0-1 slide)
    8.  **Contact Information:** Include key contact details (LinkedIn, Email, Phone) from the resume. (1 slide)
*   **Content:** Focus on *achievements and impact* over just listing duties. Use strong action verbs. Synthesize information – don't just copy/paste paragraphs or long lists of bullets from the resume.
*   **Visuals:** Suggest professional headshot (placeholder text: "[Placeholder for Headshot]"), company logos for experience slides (placeholder text: "[Logo for Company X]"), icons for skills/contact info, simple timeline graphic for career trajectory. Keep it clean and professional.
*   **Best Practice Tips:** Emphasize clarity, conciseness, highlighting the candidate's unique value proposition, and ensuring the summary aligns with the likely interests of the target audience (hiring managers).
*   **Elaboration/Enhancement:** Focus these on explaining the *significance* of achievements or suggesting how the presenter could tailor the slide further for a specific job application (e.g., "Expand on AI/ML experience for AI roles").
        """
    elif classification == "Python Source Code":
        specific_guidance = """
**Python Source Code Specific Guidance (Technical Audience):**
*   **Goal:** Summarize the code's purpose, structure, key components, dependencies, and potential implications for a technical leader (like a CTO or Engineering Manager). Focus on the "what" and "why," less on the line-by-line "how."
*   **Security:** Analyze as text. Highlight security considerations *mentioned* (e.g., in comments) or obvious patterns (secrets handling), but *do not make definitive judgments*.
*   **Suggested Structure (~5-8 slides):**
    1.  **Overview:** Title: "Code Purpose & Function". Key Message: What it does. Bullets: Goal, Input/Output, Type (script, lib, API).
    2.  **Components/Structure:** Title: "Core Modules & Classes". Key Message: Main structure. Bullets: Key classes/functions, their purpose.
    3.  **Dependencies:** Title: "Key Imports & Dependencies". Key Message: External reliance. Bullets: Significant imports (frameworks, SDKs, complex libs).
    4.  **Data Handling / IO:** Title: "Data Interaction". Key Message: How it interacts with data/systems. Bullets: Mention file IO, DBs, APIs based on imports/names.
    5.  **Configuration:** Title: "Configuration & Environment". Key Message: How configured. Bullets: Env vars, config files, args, hardcoded values (note risk).
    6.  **Considerations:** Title: "Notable Aspects". Key Message: Interesting/impactful points. Bullets: Complexity, performance notes, error handling, security notes (from comments), licensing.
    7.  **Summary:** Title: "Overall Summary". Key Message: Value/purpose. Bullets: Key takeaways, integration points, next steps.
*   **Content:** Use names, docstrings, comments, imports. Code snippets sparingly for illustration, mark clearly.
*   **Visuals:** Suggest "Architecture Diagram Concept", "Dependency Graph Concept", "Flowchart Concept". Often "Text Focus" or "Code Snippet Example".
*   **Best Practice Tips:** Conciseness, highlight resource needs, technical accuracy, translate to business impact.
        """
    elif classification == "Case Study / Research Report":
        specific_guidance = """
**Case Study / Research Report Specific Guidance (Executive/Stakeholder Audience):**
*   **Goal:** Create an executive summary focusing on the core question/problem studied, the key findings/insights discovered, and the primary recommendations or conclusions.
*   **Structure & Slide Count (Aim for ~6-10 slides):**
    1.  **Title Slide:** Use the report/study title. Include authors/date if prominent.
    2.  **Executive Summary/Overview:** Title: e.g., "Study Overview & Key Conclusion". Key Message: State the main purpose and the single most important outcome/finding. Bullets: Briefly outline the problem/question, the context (e.g., industry, timeframe), and the main result.
    3.  **Key Findings/Insights (Multiple Slides):** Title: e.g., "Key Insight 1: [Insight Theme]", "Finding: [Finding Theme]". Dedicate one slide per major finding or insight. *Look for explicit numbered lists (like "1.", "2.") or sections titled "Findings", "Insights", "Results"*. Key Message: State the finding clearly. Bullets: Provide 2-4 supporting details, data points, or examples *from the text* for that specific finding.
    4.  **Methodology Summary (Optional, 1 slide max):** Title: "Approach / Methodology". Key Message: Briefly describe how the results were obtained. Bullets: Mention key methods (e.g., survey, trials, analysis, blind study) only if necessary context for findings. Keep very concise for executives.
    5.  **Recommendations/Lessons Learned (Multiple Slides):** Title: e.g., "Recommendation 1: [Action/Theme]", "Lesson Learned: [Topic]". Dedicate one slide per major recommendation or lesson. *Look for explicit numbered lists or sections titled "Recommendations", "Lessons", "Next Steps"*. Key Message: State the recommendation/lesson clearly. Bullets: Add 1-3 points elaborating on the 'why' or 'how' *based on the text*.
    6.  **Conclusion/Implications:** Title: "Conclusion & Business Implications". Key Message: Restate the overall significance of the study/report. Bullets: Summarize the main impact for the target audience, potential next steps mentioned in the text, or broader implications discussed.
*   **Content:** Prioritize extracting verbatim findings and recommendations if they are clearly stated. Use the document's own structure (especially numbered lists) as a primary guide.
*   **Visuals:** Suggest charts for quantitative data mentioned, icons for findings/recommendations, simple process flows for methodology.
*   **Best Practice Tips:** Focus on clarity and impact for leadership. Directly answer "What did we learn?" and "What should we do?". Ensure findings/recommendations are distinct.
        """
    elif classification == "Informational Guide/Manual":
        specific_guidance = """
**Informational Guide/Manual Specific Guidance (User/Trainee Audience):**
*   **Structure:** Mirror the source document's sections and headings closely. Use the source's headings directly as Slide Titles where possible. If the source has nested sections (e.g., 1, 1.1, 1.2), consider grouping related subsections onto a single slide or creating multiple slides per major section. Use an Agenda slide based on main headings. Target **15-30+ slides** depending on text length, prioritizing thoroughness.
*   **Content:** Extract key definitions, procedures, rules, lists, contact points, resources, and important takeaways from EACH section presented in the text. Use bullet points to list steps, options, or criteria clearly. Quote specific rules or important notes where precision matters. Aim for **4-6 detailed bullets** per slide.
*   **Comprehensiveness:** Aim to represent *all significant information* present in the provided text. Generate a sufficient number of slides to cover the topics without over-simplifying. If a section in the text is detailed, the corresponding slide(s) should be detailed.
*   **Visuals:** Suggest flowcharts for processes, tables for comparisons or lists of resources/contacts, diagrams to illustrate concepts, screenshots if applicable (placeholder text: "[Placeholder for Screenshot of X]").
*   **Best Practice Tips:** Focus on clarity, logical flow matching the guide, ease of navigation for the reader, and highlighting actionable information (like contact details or steps to take). Use consistent formatting for steps/lists.
*   **Truncation Handling:** If input was truncated, add a final slide titled "Note on Scope" or similar, stating the presentation covers only the initial part of the guide due to input limits.
        """
    elif classification == "Terms of Service (ToS)":
        specific_guidance = """
**Terms of Service (ToS) Specific Guidance (Legal/Business Audience):**
*   **Mandatory Sections:** Ensure dedicated slides cover: Scope & Acceptance, Definitions, Services Offered, User Obligations/Acceptable Use Policy (AUP), Provider Rights/Disclaimers, Fees/Payment Terms (if any), Intellectual Property (IP), Confidentiality, **Limitation of Liability (CRITICAL: Use Caps/Bold, highlight exclusions)**, Indemnification, Term/Termination, Governing Law/Dispute Resolution, Privacy Policy reference, Contact Info.
*   **Structure:** Follow document structure generally; group related sub-clauses logically (e.g., all payment terms together).
*   **Content:** Extract exact key phrases/limitations, especially for liability, disclaimers, and user obligations. Use bullets for specific rules or rights. Summarize less critical sections.
*   **Visuals:** Use icons (IP, payment, user rights), flowcharts (disputes process), tables (fees). Often "Text Focus" is appropriate, but use formatting (bolding, lists) for readability.
*   **Best Practice Tips:** Prioritize clarity on key risks and obligations. Ensure legal precision is maintained in summaries. Highlight sections users most need to understand (obligations, liability).
        """
    elif classification == "Service Level Agreement (SLA)":
        specific_guidance = """
**Service Level Agreement (SLA) Specific Guidance (Technical/Operations Audience):**
*   **Mandatory Sections:** Ensure dedicated slides cover: **Definitions (CRITICAL: Uptime, Downtime, Severity Levels, Response Time, Resolution Time, etc.)**, Scope of Services Covered, **Performance Metrics (CRITICAL: Uptime %, Latency targets, etc. - use exact numbers)**, Measurement Methods & Reporting, Support Procedures (Contact, Hours, Escalation), **Incident Response/Resolution Times (CRITICAL: Often best in a table by Severity)**, **Service Credits/Remedies (CRITICAL: Use table linking metrics to credits, show examples if provided)**, Exclusions from SLA, Customer Responsibilities.
*   **Structure:** Definitions first, then guarantees/metrics, support processes, remedies, and finally exclusions/responsibilities.
*   **Content:** Must be quantitative and precise. Extract exact numbers, percentages, timeframes. Use tables extensively for metrics, response times, and service credits.
*   **Visuals:** Tables are essential. Process flowcharts (support/escalation paths). Simple charts (e.g., uptime level vs. service credit percentage).
*   **Best Practice Tips:** Extreme clarity on definitions and metrics is crucial. Ensure commitments, remedies, and exclusions are unambiguous. Visually separate different service levels if applicable.
        """
    elif classification == "Privacy Policy":
        specific_guidance = """
**Privacy Policy Specific Guidance (General/Legal Audience):**
*   **Key Sections:** Ensure coverage of: What Information is Collected (Types), How Information is Collected (Sources), How Information is Used (Purposes), How/With Whom Information is Shared/Disclosed (Third Parties), Data Security Measures, Data Retention Periods, **User Rights & Choices (CRITICAL: Detail rights like access, deletion, opt-out and HOW to exercise them)**, Cookie Policy/Tracking Technologies, International Data Transfers (if applicable), Children's Privacy, Policy Updates/Changes, Contact Information.
*   **Structure:** Follow the policy's flow logically. Group related uses or sharing practices. Use clear headings matching policy sections.
*   **Content:** Summarize key practices clearly and concisely. Use bullets for lists (e.g., types of data, user rights). Quote critical statements regarding rights or sensitive data sharing directly if needed for precision.
*   **Visuals:** Use icons (data types collected, user rights symbols, security icon), simple flowcharts (how data is used/shared), tables (e.g., data types vs. purposes/sharing). Keep visuals simple and clear.
*   **Best Practice Tips:** Emphasize transparency and user control. Ensure language is accessible to the average user. Clearly explain how users can exercise their rights. Highlight compliance with relevant regulations (e.g., GDPR, CCPA) if mentioned.
        """
    elif classification == "Contract/Agreement":
        specific_guidance = """
**General Contract/Agreement Guidance (Legal/Business Audience):**
*   **Key Sections Focus:** Parties, Effective Date/Term, Purpose/Scope of Agreement, Core Obligations of Each Party, Payment Terms (Amount, Schedule, Conditions), Term & Termination Clauses (Reasons, Notice Periods), Confidentiality Obligations, Intellectual Property Rights (Ownership, Licenses), Warranties/Disclaimers, Limitation of Liability/Indemnity, Governing Law/Dispute Resolution.
*   **Content:** Use precise language from the contract for key obligations and definitions. Summarize background/recitals briefly. Use bullets to list specific duties or conditions. Reference specific clauses/sections in the 'Notes' field where helpful for reviewers.
*   **Structure:** Follow the contract's article/section flow logically. Group related topics if beneficial (e.g., all payment details).
*   **Visuals:** Primarily "Text Focus". Tables can be useful for key dates, payment schedules, or liability caps. Simple icons for parties or governing law might add minor visual aid.
*   **Best Practice Tips:** Focus on clarity and accuracy for legal/business review. Highlight critical clauses, obligations, risks, and key dates. Avoid interpreting legal language; summarize or quote carefully.
        """
    elif classification == "News Article/Blog Post" or classification == "Web Page Content": # Combined similar guidance
        specific_guidance = """
**Web Page / Article / Blog Post Specific Guidance:**
*   **Goal:** Summarize the main topic, key arguments, supporting points, and any conclusions or calls to action presented in the extracted text.
*   **Structure & Slide Count (Aim for ~5-10 slides):**
    1.  **Title Slide:** Use the web page title or article headline if available in the text, otherwise create a concise title based on the main topic. Include source URL in notes.
    2.  **Core Message/Thesis:** State the central point or main topic of the page/article.
    3.  **Key Sections/Arguments (Multiple Slides):** Dedicate slides to major themes or sections identified in the text. Use headings from the text if available. Extract 3-5 supporting bullet points for each theme.
    4.  **Key Data/Evidence (Optional):** If the text presents significant data, statistics, or specific examples, highlight them on a dedicated slide.
    5.  **Conclusion/Takeaway:** Summarize the final points, conclusions, or calls to action mentioned in the text.
*   **Content:** Focus on the primary information presented. Extract key sentences or rephrase main ideas concisely. Use bullet points for lists or supporting details.
*   **Visuals:** Suggest relevant icons, simple charts for data, pull quotes for impactful statements, or potentially a placeholder for a relevant image if the text describes one.
*   **Best Practice Tips:** Ensure logical flow, clear summaries of key sections, and accurate representation of the main message. Define jargon if the audience might be unfamiliar.
*   **Note:** Extraction quality varies. Base summary *only* on the provided text, even if it seems incomplete.
        """
    # --- NEW EXPERT GUIDANCE BLOCKS START HERE ---
    elif classification == "Legal Case Brief":
        specific_guidance = """
**Legal Case Brief Specific Guidance (Legal Professional Audience):**
*   **Goal:** Structure the summary according to the FIRAC/IRAC method (Facts, Issue, Rule, Application/Analysis, Conclusion). Highlight key legal principles and the court's reasoning.
*   **Mandatory Sections (Generate slides for these):**
    1.  **Case Identification:** Title of the case (Plaintiff v. Defendant), Court, Citation, Date.
    2.  **Facts of the Case:** Key relevant facts leading to the legal dispute.
    3.  **Legal Issue(s):** The specific legal question(s) the court is addressing.
    4.  **Rule(s) of Law:** The legal principles, statutes, or precedents applied by the court.
    5.  **Application/Analysis (Reasoning):** How the court applied the rule(s) to the facts. This is the core of the court's reasoning.
    6.  **Conclusion (Holding):** The court's decision or answer to the legal issue(s).
    7.  **Concurring/Dissenting Opinions (If Present & Significant):** Briefly summarize key points from concurrences or dissents.
*   **Content:** Extract precise legal language for rules and holdings. Summarize facts and analysis concisely. Use bullet points for clarity within sections.
*   **Visuals:** Primarily "Text Focus". Consider a simple flowchart for the FIRAC structure. Use icons for scales of justice, legal books, etc.
*   **Best Practice Tips:** Maintain neutrality and objectivity. Clearly distinguish between facts, rules, and the court's analysis. Accuracy is paramount.
*   **Elaboration/Enhancement:** Explain the significance of the holding or its potential impact on future cases if stated in the source. Suggest related case law to research (as an external activity).
        """
    elif classification == "Legislative Bill/Regulation":
        specific_guidance = """
**Legislative Bill/Regulation Specific Guidance (Policy Analyst/Affected Party Audience):**
*   **Goal:** Summarize the purpose, key provisions, scope, impact, and effective date of the legislation or regulation.
*   **Mandatory Sections (Generate slides for these):**
    1.  **Bill/Regulation Identification:** Bill Number/Name or Regulation Title, Issuing Body, Date of Enactment/Publication.
    2.  **Purpose/Objective:** The stated reason for the bill or regulation.
    3.  **Key Provisions/Changes:** Summarize the main requirements, prohibitions, or changes introduced.
    4.  **Scope/Applicability:** Who or what entities are affected by this legislation/regulation?
    5.  **Enforcement/Penalties (If Stated):** How will it be enforced and what are the consequences for non-compliance?
    6.  **Effective Date(s):** When does this come into force?
    7.  **Stated Impact/Rationale (If Present):** Any expected outcomes or justifications provided in the text.
*   **Content:** Extract specific requirements and definitions. Use bullet points to list key provisions clearly.
*   **Visuals:** "Text Focus" often appropriate. Simple flowcharts for processes introduced. Tables for comparing old vs. new rules if applicable. Icons for government, compliance, etc.
*   **Best Practice Tips:** Clarity and accuracy are essential. Use direct language. Highlight what changes for affected parties.
*   **Elaboration/Enhancement:** Explain the context or background leading to this legislation if provided in the text. Suggest resources for further information if mentioned.
        """
    elif classification == "Business Plan":
        specific_guidance = """
**Business Plan Specific Guidance (Investor/Lender Audience):**
*   **Goal:** Create a concise executive summary highlighting the core business concept, market opportunity, strategy, team, and financial outlook.
*   **Mandatory Sections (Generate slides for these, prioritize):**
    1.  **Executive Summary:** A high-level overview of the entire plan (often a dedicated section in the plan itself).
    2.  **Company Description & Mission:** What the business does and its core purpose/values.
    3.  **Problem & Solution (Value Proposition):** The customer pain point and how the business solves it.
    4.  **Products/Services:** Description of offerings.
    5.  **Target Market & Opportunity:** Size, characteristics, and potential of the target market.
    6.  **Marketing & Sales Strategy:** How the business will reach and acquire customers.
    7.  **Management Team:** Key personnel and their expertise.
    8.  **Financial Highlights/Projections:** Key financial forecasts (revenue, profit) and funding request if applicable.
*   **Suggested Structure & Slide Count (Aim for ~10-15 slides):** Structure should follow the typical business plan flow.
*   **Content:** Extract key metrics, strategic differentiators, and growth plans. Summarize complex sections clearly.
*   **Visuals:** Charts for financial projections/market size. Icons for team, product, market. Simple diagrams for business model.
*   **Best Practice Tips:** Focus on clarity, compelling narrative, and demonstrating viability/potential. Highlight competitive advantages.
*   **Elaboration/Enhancement:** Explain the significance of market trends or competitive advantages. Suggest key questions an investor might ask based on the content.
        """
    elif classification == "SWOT Analysis Document":
        specific_guidance = """
**SWOT Analysis Specific Guidance (Strategic Planning Audience):**
*   **Goal:** Clearly present the identified Strengths, Weaknesses, Opportunities, and Threats.
*   **Mandatory Structure (Generate slides explicitly for these - 4 content slides + title):**
    1.  **Title Slide:** "SWOT Analysis: [Subject/Company Name]"
    2.  **Strengths:** List all identified internal strengths.
    3.  **Weaknesses:** List all identified internal weaknesses.
    4.  **Opportunities:** List all identified external opportunities.
    5.  **Threats:** List all identified external threats.
*   **Content:** Extract each point verbatim or as a very close paraphrase. Use clear bullet points under each of the four categories. Ensure distinction between internal (S, W) and external (O, T) factors is maintained if the source text makes it clear.
*   **Visuals:** Classic 2x2 SWOT matrix visual concept is highly recommended. Use icons for each quadrant (e.g., muscle for Strengths, broken link for Weaknesses, lightbulb for Opportunities, storm cloud for Threats).
*   **Best Practice Tips:** Ensure clear separation of the four categories. Points should be concise and actionable if possible (though the summary should reflect the source).
*   **Elaboration/Enhancement:** If the document draws connections (e.g., how a strength can address an opportunity), highlight this in the elaboration. Suggest next steps in strategic planning based on the SWOT (e.g., "Develop strategies to leverage strengths for opportunities").
        """
    elif classification == "Press Release":
        specific_guidance = """
**Press Release Specific Guidance (Journalist/Public Audience):**
*   **Goal:** Summarize the key announcement, providing essential details (5 Ws & H), important quotes, and contact information.
*   **Mandatory Sections (Generate slides for these):**
    1.  **Headline:** The main title of the press release.
    2.  **Dateline & Introduction (The Lede):** City, State – Date – and the opening paragraph summarizing the core news (Who, What, When, Where, Why).
    3.  **Key Details/Body:** Further elaboration on the announcement, key facts, figures, or context.
    4.  **Key Quotes:** Extract 1-2 significant quotes from individuals mentioned.
    5.  **Boilerplate/About Us:** Standardized information about the company/organization.
    6.  **Contact Information:** Media contact details.
*   **Content:** Extract information directly. The structure of a press release is usually quite standard.
*   **Visuals:** "Text Focus" is common. Company logo placeholder. Icons for news, quotes, contact.
*   **Best Practice Tips:** Maintain the factual and objective tone of the press release. Ensure all key elements are captured.
*   **Elaboration/Enhancement:** Explain the potential impact or significance of the announcement if hinted at in the text. Suggest angles for journalists to explore.
        """
    elif classification == "System Design Document":
        specific_guidance = """
**System Design Document Specific Guidance (Technical/Engineering Audience):**
*   **Goal:** Summarize the system's architecture, key components, interfaces, data flows, and critical non-functional requirements.
*   **Mandatory Sections (Generate slides for these, adapt based on document content):**
    1.  **System Overview & Purpose:** What the system does and its goals.
    2.  **High-Level Architecture:** A diagram or description of the main components and their interactions.
    3.  **Key Components Deep Dive:** For 2-3 most critical components, detail their responsibilities and technologies.
    4.  **Data Model/Storage:** How data is structured, stored, and managed.
    5.  **API Specifications/Interfaces:** Key external and internal APIs or interfaces.
    6.  **Non-Functional Requirements (NFRs):** Key considerations like Scalability, Performance, Security, Reliability, Maintainability.
    7.  **Technology Stack:** Major technologies, frameworks, and platforms used.
    8.  **Deployment Strategy (If Covered):** How the system is deployed and managed.
*   **Content:** Focus on technical specifics. Extract diagrams or descriptions of them. List technologies and NFRs.
*   **Visuals:** Suggest "Architecture Diagram Concept," "Component Diagram Concept," "Data Flow Diagram Concept," "Sequence Diagram Concept." Tables for NFRs or API endpoints.
*   **Best Practice Tips:** Clarity and accuracy for a technical audience. Use consistent terminology. Highlight design choices and trade-offs if mentioned.
*   **Elaboration/Enhancement:** Explain the rationale behind key architectural decisions if provided. Suggest areas for further technical review or potential bottlenecks.
        """
    elif classification == "User Story / Feature Requirement Document":
        specific_guidance = """
**User Story / Feature Requirement Specific Guidance (Agile Team/Product Owner Audience):**
*   **Goal:** Present each user story or feature clearly, including its user, goal, benefit, and acceptance criteria.
*   **Structure (One or more slides per story/feature, depending on detail):**
    *   **Slide Title:** "User Story: [Short Title/ID]" or "Feature: [Feature Name]"
    *   **Content Type:** "User Story Details" or "Feature Specification"
    *   **Key Message:** The core "As a [user], I want [goal], so that [benefit/reason]" statement.
    *   **Bullets:**
        *   **User/Role:** [Target user persona]
        *   **Goal/Need:** [What the user wants to accomplish]
        *   **Benefit/Value:** [Why this is important to the user/business]
        *   **Acceptance Criteria:** (List each criterion as a sub-bullet or separate bullets)
            - AC1: [Specific condition to be met]
            - AC2: [Another specific condition]
        *   **Notes/Dependencies (If any):** [Other relevant info like priority, linked issues]
*   **Content:** Extract the structured elements of each story/feature. Ensure all acceptance criteria are listed.
*   **Visuals:** "Text Focus" is primary. Use icons to represent user, goal, checklist for ACs. Simple flow for a user journey if multiple related stories are presented.
*   **Best Practice Tips:** Ensure each component of the story is clearly captured. ACs should be testable. Maintain consistency in presentation.
*   **Elaboration/Enhancement:** Explain the business impact of the story/feature if context is given. Suggest potential edge cases or questions for backlog refinement based on the provided text.
        """
    elif classification == "Medical Journal Article":
        specific_guidance = """
**Medical Journal Article Specific Guidance (Healthcare Professional/Researcher Audience):**
*   **Goal:** Summarize the research using the PICO framework (Population, Intervention, Comparison, Outcome), detailing study design, key results, and clinical significance.
*   **Mandatory Sections (Generate slides for these, following IMRAD if possible):**
    1.  **Title & Citation:** Full Article Title, Authors, Journal, Year, DOI (if available).
    2.  **Abstract Summary/Background:** Briefly state the research question and context.
    3.  **PICO Summary:**
        *   **P (Population/Problem):** Characteristics of the study participants or the health problem.
        *   **I (Intervention):** The treatment, diagnostic test, or exposure being studied.
        *   **C (Comparison):** The control group or alternative intervention. State if none.
        *   **O (Outcome):** Key results and measurements.
    4.  **Study Design & Methods:** Type of study (e.g., RCT, Cohort, Case-Control), key methodological aspects.
    5.  **Key Results/Findings:** Main quantitative and qualitative findings, including statistical significance if reported (e.g., p-values, confidence intervals).
    6.  **Discussion/Authors' Conclusions:** The authors' interpretation of the results and their main conclusions.
    7.  **Limitations:** Stated limitations of the study.
    8.  **Clinical Significance/Implications:** How the findings might impact clinical practice or future research.
*   **Content:** Prioritize accuracy and use of medical terminology from the source. Extract specific data points and statistical values.
*   **Visuals:** Tables for PICO or results. Charts if data is presented visually in the source. "Text Focus" for discussion/conclusions. Icons for study design types.
*   **Best Practice Tips:** Maintain objectivity. Clearly differentiate results from authors' interpretations. Highlight the strength of evidence if discussed.
*   **Elaboration/Enhancement:** Explain complex statistical terms simply if possible. Suggest how these findings compare to current guidelines or other research (as an external thought, not from the text itself unless the text discusses it).
*   **Ethical Consideration Note (for prompt author):** This AI should only summarize provided text. It cannot and should not make medical diagnoses or treatment recommendations. The summary is for informational purposes based on the article content.
        """
    # --- NEW EXPERT GUIDANCE BLOCKS END HERE ---
    else: # Default/General/Other/Mixed
        specific_guidance = """
**General Presentation Flow Guidance (Adapt based on content):**
1. Overview/Introduction (Based on start of this text)
2. Key Theme/Section 1 (Extract key points/findings - 2-5 slides)
3. Key Theme/Section 2 (Extract key points/findings - 2-5 slides)
   [...]
6. Key Findings/Analysis Summary (If applicable)
7. Conclusion/Key Takeaways (From this text)
*   **Adapt Slide Count:** Based on length/density of this text.
        """

    # --- Assemble Final Prompt ---
    content_style_guidelines = f"""
{specific_guidance}

**General Content & Style Guidelines (Apply unless overridden by specific guidance):**
*   **Cohesive Narrative:** Summarize the extracted text logically.
*   **Prioritize Key Info:** Extract *most important* messages/findings/arguments relevant.
*   **Detail & Specificity:** Use precise terms, facts, figures from source text where appropriate.
*   **Attribute:** Use 'Notes:' field minimally for source refs (like URL if applicable or 'OP'/'Comment Thread').
*   **Consistent Voice:** Maintain '{final_tone_label}' for '{final_audience_label}'.
*   **Actionable Suggestions:** Ensure Enhancement/Best Practice tips are practical for presenting *this* content to the **target audience**.
*   **Accuracy:** Represent concepts accurately based *only* on provided extracted text. Acknowledge limitations of extracted text if necessary (e.g., for discussions).
    """
    prompt = f"""
{base_instructions}
{content_style_guidelines}

**Source Text (Extracted from {source_type}: {source_identifier}, potentially truncated):**
\"\"\"
{document_text}
\"\"\"

Generate the **complete summary presentation** for the source: {source_identifier}. Follow ALL instructions meticulously, especially the Tailoring Instructions and Classification-Specific Guidance. Ensure all required fields are present and accurate based *solely* from the text provided. Use `---` ONLY as a separator **between** slides. Begin directly with the first slide block.
"""
    logging.debug(f"Generated prompt length for {source_identifier}: {len(prompt)} chars")
    return prompt

# --- End of prompts.py ---