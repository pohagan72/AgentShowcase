# features/summarization/prompts/analyst_prompts.py
import logging

# --- 1. MANDATE DEFINITIONS (The "Expert Brains") ---
# These definitions decouple the "Role" from the specific document type.
# When a document is classified, we look up the corresponding mandate here.

DEFAULT_MANDATE = {
    "role": "Chief of Staff",
    "decision": "strategic prioritization and resource allocation",
    "constraints": [
        "Focus on the 'Bottom Line Up Front' (BLUF).",
        "Highlight immediate action items and specific owners.",
        "Ignore generic background information and marketing fluff."
    ]
}

MANDATES = {
    "Financial Report (Annual/10-K/10-Q)": {
        "role": "Chief Financial Officer (CFO)",
        "decision": "capital allocation, investment viability, and risk mitigation",
        "constraints": [
            "Focus strictly on EBITDA, revenue drivers, and cash flow obligations.",
            "Ignore generic market commentary and PR language.",
            "Highlight non-recurring items, debt maturity profiles, and material risks."
        ]
    },
    "Investment Analysis / Due Diligence Report": {
        "role": "Private Equity Partner",
        "decision": "deal valuation and go/no-go judgment",
        "constraints": [
            "Identify synergies, cost-saving opportunities, and growth levers.",
            "Flag any inconsistencies in management's narrative.",
            "Quantify upside potential and downside protection explicitly."
        ]
    },
    "Contract/Agreement": {
        "role": "General Counsel",
        "decision": "signing risk, liability exposure, and commercial terms",
        "constraints": [
            "Focus on indemnification, termination rights, warranties, and liability caps.",
            "Ignore standard boilerplate definitions unless they deviate from market norms.",
            "Highlight unusual or non-standard clauses that create leverage."
        ]
    },
    "Terms of Service (ToS)": {
        "role": "Chief Compliance Officer",
        "decision": "user data privacy impact and regulatory compliance",
        "constraints": [
            "Focus on data retention, third-party sharing, and user rights.",
            "Identify binding arbitration clauses and jurisdiction waivers.",
            "Flag any permissions that exceed service requirements."
        ]
    },
    "System Design Document": {
        "role": "Chief Technology Officer (CTO)",
        "decision": "technical feasibility, scalability, and architectural debt",
        "constraints": [
            "Focus on bottlenecks, single points of failure, and security perimeters.",
            "Evaluate technology choices against modern industry standards.",
            "Identify scalability limits and maintenance overhead."
        ]
    },
    "Python Source Code": {
        "role": "Lead Software Architect",
        "decision": "code maintainability, security, and refactoring needs",
        "constraints": [
            "Focus on modularity, error handling patterns, and algorithmic complexity.",
            "Ignore standard syntax details; focus on the logic flow.",
            "Identify potential security vulnerabilities (e.g., injection points)."
        ]
    },
    "Resume/CV": {
        "role": "Hiring Manager",
        "decision": "candidate capability fit and interview prioritization",
        "constraints": [
            "Focus on quantifiable achievements (metrics) and specific skill gaps.",
            "Ignore subjective self-assessments (e.g., 'hard worker', 'team player').",
            "Map experience directly to seniority and impact."
        ]
    },
    "News Article/Blog Post": {
        "role": "Market Intelligence Analyst",
        "decision": "market sentiment analysis and competitive positioning",
        "constraints": [
            "Distinguish between reported fact and editorial opinion.",
            "Identify the underlying narrative or agenda of the source.",
            "Extract specific entities, dates, and claims."
        ]
    },
    "Scientific/Academic Paper": {
        "role": "R&D Director",
        "decision": "technological validity and potential application",
        "constraints": [
            "Focus on methodology, results, and statistical significance.",
            "Ignore the abstract/intro; look for the actual data findings.",
            "Assess the replicability and limitations of the study."
        ]
    }
}

# --- 2. CLASSIFICATION CATEGORIES ---
# The taxonomy used by the classifier to select a mandate.
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
    "Scientific/Academic Paper", 
    "Legal Case Brief", 
    "Legislative Bill/Regulation", 
    "Business Plan", 
    "SWOT Analysis Document", 
    "Press Release", 
    "Investment Analysis / Due Diligence Report",
    "System Design Document", 
    "User Story / Feature Requirement Document",
    "Medical Journal Article", 
    "Other"
]

# --- 3. HELPER FUNCTIONS ---

def get_mandate(classification):
    """
    Retrieves the specific mandate definition for a given classification.
    Returns the DEFAULT_MANDATE if the classification isn't explicitly defined in MANDATES.
    """
    return MANDATES.get(classification, DEFAULT_MANDATE)

def get_classification_prompt(document_text_excerpt, metadata=None):
    """
    Generates the prompt used to classify the document type.
    Now includes optional metadata hints for improved accuracy.
    
    Args:
        document_text_excerpt (str): Text sample from the document
        metadata (dict): Optional metadata like filename, title, author, etc.
    """
    max_excerpt_chars = 25000
    truncated_excerpt = document_text_excerpt[:max_excerpt_chars]
    categories_str = "\n - ".join(CLASSIFICATION_CATEGORIES)
    
    # Build metadata context if available
    metadata_context = ""
    if metadata:
        metadata_parts = []
        if metadata.get('filename'):
            metadata_parts.append(f"Filename: {metadata['filename']}")
        if metadata.get('title'):
            metadata_parts.append(f"Document Title: {metadata['title']}")
        if metadata.get('author'):
            metadata_parts.append(f"Author: {metadata['author']}")
        if metadata.get('subject'):
            metadata_parts.append(f"Subject: {metadata['subject']}")
        
        if metadata_parts:
            metadata_context = f"\nDocument Metadata:\n" + "\n".join(metadata_parts) + "\n"
    
    prompt = f"""
    Analyze the following text excerpt and metadata. Based *only* on the content and structure, classify the document type. 
    Choose the *single most appropriate* category from the list below.
    
    CRITICAL INSTRUCTIONS:
    - Respond with ONLY the category name exactly as written below
    - Do not add punctuation, explanation, or preamble
    - Do not wrap in quotes or add any formatting
    - If metadata strongly suggests a type (e.g., filename contains "10-K"), prioritize that signal
    
    Available Categories:
    - {categories_str}
    {metadata_context}
    Document Excerpt:
    \"\"\"
    {truncated_excerpt}
    \"\"\"

    Document Classification Category:
    """
    return prompt

def parse_classification_response(llm_response_text, source_identifier="", metadata=None):
    """
    Cleans up the LLM's classification response with hybrid approach.
    Includes heuristic overrides and conflict detection.
    
    Args:
        llm_response_text (str): Raw LLM output
        source_identifier (str): Filename or document identifier
        metadata (dict): Optional document metadata for heuristics
    """
    if not llm_response_text:
        return "General Business Document"

    # Clean LLM response
    potential_category = llm_response_text.strip()
    cleaned = ''.join(filter(
        lambda x: x.isalnum() or x in [' ', '(', ')', '/', '-', ',', ':'], 
        potential_category[:100]
    )).strip().lower()
    
    source_lower = source_identifier.lower()
    
    # --- HEURISTIC CLASSIFICATION ---
    heuristic_match = _get_heuristic_classification(source_lower, metadata)
    
    # --- LLM CLASSIFICATION ---
    llm_match = _get_llm_classification(cleaned)
    
    # --- CONFLICT RESOLUTION ---
    if heuristic_match and llm_match and heuristic_match != llm_match:
        logging.info(
            f"Classification conflict detected: "
            f"Heuristic={heuristic_match}, LLM={llm_match}, Source={source_identifier}"
        )
        
        # Financial documents are highly formulaic - trust heuristics
        if heuristic_match in ["Financial Report (Annual/10-K/10-Q)", "Investment Analysis / Due Diligence Report"]:
            logging.info(f"Preferring heuristic classification for financial document: {heuristic_match}")
            return heuristic_match
        
        # For code files, trust file extension over content
        if heuristic_match == "Python Source Code":
            return heuristic_match
    
    # Return first match found (heuristic takes precedence if both exist)
    return heuristic_match or llm_match or "General Business Document"

def _get_heuristic_classification(source_lower, metadata=None):
    """
    Apply rule-based classification using filename, metadata, and known patterns.
    Returns None if no strong heuristic match found.
    """
    # Financial document patterns
    financial_indicators = ["10-k", "10k", "10-q", "10q", "annual_report", "annual report", "form 10"]
    if any(x in source_lower for x in financial_indicators):
        return "Financial Report (Annual/10-K/10-Q)"
    
    # Check metadata title/subject for financial keywords
    if metadata:
        title = (metadata.get('title') or '').lower()
        subject = (metadata.get('subject') or '').lower()
        if any(x in title or x in subject for x in financial_indicators):
            return "Financial Report (Annual/10-K/10-Q)"
    
    # Due diligence patterns
    dd_indicators = ["due diligence", "investment memo", "deal analysis", "valuation"]
    if any(x in source_lower for x in dd_indicators):
        return "Investment Analysis / Due Diligence Report"
    
    # Source code patterns
    code_extensions = [".py", ".js", ".java", ".cpp", ".c", ".go", ".rs", ".ts"]
    if any(source_lower.endswith(ext) for ext in code_extensions):
        return "Python Source Code"  # Generalize this if needed
    
    # Web content patterns
    if 'reddit.com' in source_lower:
        return "Reddit Thread"
    
    # Contract patterns
    contract_keywords = ["agreement", "contract", "msa", "nda", "sow", "statement of work"]
    if any(x in source_lower for x in contract_keywords):
        return "Contract/Agreement"
    
    # ToS patterns
    tos_keywords = ["terms of service", "terms and conditions", "user agreement"]
    if any(x in source_lower for x in tos_keywords):
        return "Terms of Service (ToS)"
    
    return None

def _get_llm_classification(cleaned_response):
    """
    Match LLM response to known categories using fuzzy matching.
    Returns None if no match found.
    """
    # Try exact match first
    for cat in CLASSIFICATION_CATEGORIES:
        if cat.lower() == cleaned_response:
            return cat
    
    # Try substring match
    for cat in CLASSIFICATION_CATEGORIES:
        if cat.lower() in cleaned_response:
            return cat
    
    # Try partial keyword matching for common variations
    keyword_map = {
        "financial": "Financial Report (Annual/10-K/10-Q)",
        "resume": "Resume/CV",
        "cv": "Resume/CV",
        "code": "Python Source Code",
        "contract": "Contract/Agreement",
        "agreement": "Contract/Agreement",
        "academic": "Scientific/Academic Paper",
        "paper": "Scientific/Academic Paper",
        "research": "Scientific/Academic Paper",
        "terms of service": "Terms of Service (ToS)",
        "privacy": "Privacy Policy"
    }
    
    for keyword, category in keyword_map.items():
        if keyword in cleaned_response:
            return category
    
    return None

def build_analyst_prompt(text_to_summarize, classification, metadata=None):
    """
    Constructs the detailed prompt for the Analyst Agent with few-shot examples.
    This prompt enforces the "Thinking Workbench" format (::TAGS::) followed by the Markdown report.
    
    Args:
        text_to_summarize (str): The document content
        classification (str): Document type classification
        metadata (dict): Optional document metadata
    """
    mandate = get_mandate(classification)
    
    constraint_bullets = "\n".join([f"    - {c}" for c in mandate['constraints']])
    
    # Truncate input text to fit context windows
    MAX_CHARS = 100000 
    safe_text = text_to_summarize[:MAX_CHARS]
    
    # Build metadata context if available
    metadata_context = ""
    if metadata:
        metadata_context = "\n**Document Context:**\n"
        if metadata.get('filename'):
            metadata_context += f"- Source: {metadata['filename']}\n"
        if metadata.get('title'):
            metadata_context += f"- Title: {metadata['title']}\n"
        if metadata.get('author'):
            metadata_context += f"- Author: {metadata['author']}\n"
    
    prompt = f"""
    SYSTEM: You are advising a {mandate['role']} who must make a real decision based on this document.
    Document Class: '{classification}'
    {metadata_context}
    DECISION CONTEXT:
    The reader will use your analysis to decide on {mandate['decision']}.

    YOUR OBJECTIVE:
    Optimize the summary for decision quality, not completeness. Be concise, direct, and cynical where necessary.

    EXPERT CONSTRAINTS (MANDATORY):
    {constraint_bullets}
    - Do NOT restate obvious facts or summary tables unless they drive a decision.
    - If evidence is insufficient to make a recommendation, explicitly state the gap.

    --- OUTPUT INSTRUCTIONS (STRICT - YOU MUST FOLLOW THIS EXACT FORMAT) ---

    PHASE 1: LIVE DELIBERATION
    Before writing the final report, you MUST output your internal thinking process using these specific tags. 
    Write each thought on a new line. You must have at least 3-5 distinct thoughts before proceeding to the report.
    
    CRITICAL: Each tag MUST be on its own line, followed by the content. Do NOT combine multiple tags on one line.

    Use EXACTLY these tags (copy them precisely):
    ::HYPOTHESIS:: [What is the strategic implication or hidden risk?]
    ::EVIDENCE:: [Quote specific data/numbers/clauses from the text to support/refute the hypothesis]
    ::DECISION:: [The intermediate judgment call based on evidence]
    ::NOTE:: [Any missing info, ambiguity, or specific risk factor]

    EXAMPLE OF CORRECT FORMAT:
    ::HYPOTHESIS:: The debt-to-equity ratio of 2.3 indicates potentially dangerous leverage that could constrain growth investments
    ::EVIDENCE:: "Total liabilities: $450M, Total equity: $195M" (from Balance Sheet, page 12). Industry median D/E ratio is 1.5
    ::DECISION:: Recommend deeper due diligence on debt maturity schedule and refinancing plans before proceeding with investment
    ::NOTE:: Missing critical information: breakdown of short-term vs long-term debt, debt covenant terms, and interest rate exposure

    ::HYPOTHESIS:: Revenue growth of 23% YoY appears strong but may be unsustainable given market saturation signals
    ::EVIDENCE:: "Q4 revenue: $127M vs $103M prior year" but customer acquisition cost increased 45% and churn rate rose to 8%
    ::DECISION:: Growth is concerning rather than impressive - unit economics are deteriorating
    ::NOTE:: Need to verify if high CAC is due to market expansion or competitive pressure

    ::HYPOTHESIS:: The IP portfolio creates meaningful competitive moat in the mid-market segment
    ::EVIDENCE:: Company holds 12 patents in core technology area, 3 direct competitors hold only 2-4 patents each
    ::DECISION:: IP position is a genuine differentiator worth 15-20% premium in valuation
    ::NOTE:: Verify patent expiration dates and ongoing litigation risks

    PHASE 2: THE EXECUTIVE BRIEF
    Once you have completed your deliberation with at least 3-5 thinking cycles, output exactly "### REPORT START" on a new line.
    Then, provide the final brief in clean Markdown format.

    Structure of the Brief (USE EXACTLY THESE HEADERS):
    1. **Executive Summary (BLUF)**: The single most important takeaway in 2-3 sentences
    2. **Key Findings**: Bullet points with bolded metrics and specific data
    3. **Risk Analysis**: Specific downsides and red flags
    4. **Recommendations**: Concrete next steps with clear owners/timelines where possible

    EXAMPLE STRUCTURE:
    ### REPORT START
    
    **Executive Summary (BLUF)**: XYZ Corp shows 23% revenue growth but deteriorating unit economics and dangerous leverage (D/E 2.3x). Do not proceed without renegotiating valuation down 30% and securing debt restructuring commitment.

    **Key Findings**:
    - **Revenue**: $450M (+23% YoY) but driven by unsustainable customer acquisition spend
    - **Profitability**: EBITDA margin compressed to 12% from 18% due to CAC inflation
    - **Leverage**: Debt-to-equity of 2.3x vs industry median 1.5x
    - **Market Position**: Strong IP portfolio (12 patents) creates defensible moat in mid-market

    **Risk Analysis**:
    - **Growth Trap**: CAC increased 45% while customer LTV declined 12% - unit economics broken
    - **Debt Overhang**: $450M in liabilities with unclear maturity profile could force dilutive refinancing
    - **Churn Acceleration**: Customer churn rose to 8% from 5%, suggesting product-market fit issues

    **Recommendations**:
    1. **Immediate**: Request complete debt schedule with covenants and maturity dates
    2. **Valuation**: Reduce offer by 30% to account for deteriorating economics and leverage risk
    3. **Due Diligence**: Deep dive on customer cohort analysis to validate retention assumptions
    4. **Deal Structure**: Make investment contingent on debt refinancing or equity infusion to deleverage

    --- END INSTRUCTIONS ---

    **SOURCE DOCUMENT:**
    \"\"\"
    {safe_text}
    \"\"\"
    
    REMINDER: You MUST follow the two-phase structure:
    1. Start with deliberation using ::HYPOTHESIS::, ::EVIDENCE::, ::DECISION::, ::NOTE:: tags
    2. Then output "### REPORT START" 
    3. Then provide the structured Markdown report
    
    Begin your analysis now with Phase 1 deliberation:
    """
    return prompt