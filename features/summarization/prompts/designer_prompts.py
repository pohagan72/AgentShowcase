# features/summarization/prompts/designer_prompts.py

def get_slide_design_prompt(text, template_style="professional", metadata=None):
    """
    Generates the prompt for the Designer Agent to create structured slides.
    Enhanced with few-shot examples and explicit format enforcement.
    
    Args:
        text (str): The source document content
        template_style (str): Visual template to use (professional/creative/minimalist)
        metadata (dict): Optional document metadata for context
    """
    
    # Build metadata context if available
    metadata_context = ""
    if metadata:
        metadata_context = "\n**SOURCE CONTEXT:**\n"
        if metadata.get('filename'):
            metadata_context += f"- Document: {metadata['filename']}\n"
        if metadata.get('title'):
            metadata_context += f"- Title: {metadata['title']}\n"
        if metadata.get('classification'):
            metadata_context += f"- Type: {metadata['classification']}\n"
    
    # Template-specific guidance
    template_guidance = {
        "professional": "Use conservative business language, focus on metrics and ROI, minimize creative flourishes",
        "creative": "Use engaging narratives, emphasize innovation and vision, include bold statements",
        "minimalist": "Strip to absolute essentials, favor data over prose, use stark contrasts"
    }
    
    style_instruction = template_guidance.get(template_style, template_guidance["professional"])
    
    prompt = f"""
    SYSTEM: You are a world-class Executive Presentation Designer.
    Your task is to convert source material into a compelling, decision-focused 5-slide presentation deck.
    
    DESIGN MANDATE:
    - Template Style: {template_style} ({style_instruction})
    - Audience: C-level executives with 5 minutes to review
    - Goal: Enable a critical business decision, not just inform
    {metadata_context}
    --- CRITICAL OUTPUT FORMAT RULES (YOU MUST FOLLOW EXACTLY) ---
    
    1. **Field Separator**: Use exactly THREE DASHES on a line by themselves to separate slides: ---
    2. **Field Labels**: Use EXACTLY these labels (case-sensitive, with colons):
       - Slide Title:
       - Key Message:
       - Strategic Takeaway:
       - Speaker Notes:
       - Bullets:
    
    3. **No Markdown Code Blocks**: Do NOT wrap output in ```markdown or any code fences
    
    4. **Bullet Format**: Each bullet starts with a dash (-) on a new line under "Bullets:"
    
    5. **Exactly 5 Slides**: You must create exactly 5 slides, no more, no less
    
    --- SLIDE CONTENT REQUIREMENTS ---
    
    SLIDE 1 (Title/Overview):
    - Slide Title: Compelling headline that captures the main decision point
    - Key Message: The single most important takeaway (one sentence)
    - Strategic Takeaway: High-level context or framing for the presentation
    - Bullets: 3-4 bullets outlining what the deck will cover
    - Speaker Notes: Opening remarks and framing for the audience
    
    SLIDES 2-4 (Core Analysis):
    - Slide Title: Specific, actionable headlines (not generic like "Analysis")
    - Key Message: The "so what" for this slide in one sentence
    - Strategic Takeaway: A specific data point, metric, or insight that supports the message
    - Bullets: 3-5 bullets with concrete details (include numbers where possible)
    - Speaker Notes: Additional context, caveats, or talking points
    
    SLIDE 5 (Conclusion/Recommendations):
    - Slide Title: Clear call to action or decision recommendation
    - Key Message: The bottom line recommendation
    - Strategic Takeaway: The most critical risk or opportunity
    - Bullets: 3-4 specific next steps with implied owners/timelines
    - Speaker Notes: Closing remarks and discussion prompts
    
    --- EXAMPLE OUTPUT (FOLLOW THIS EXACT STRUCTURE) ---
    
    Slide Title: Market Entry Decision: Thailand Expansion Requires $12M Investment
    Key Message: Strong market fundamentals support entry, but execution risks demand phased approach
    Strategic Takeaway: Thailand's EdTech market is growing at 34% CAGR, 3x faster than domestic market
    Speaker Notes: This deck presents our analysis of the Thailand market opportunity and recommends a staged investment approach to manage execution risk while capturing upside
    Bullets:
    - Market opportunity: $800M addressable market growing 34% annually
    - Competitive landscape: Top 3 players control only 40% share, fragmented market
    - Investment required: $12M over 18 months for market entry and scaling
    - Risk factors: Regulatory uncertainty, localization complexity, currency volatility
    ---
    Slide Title: Market Fundamentals Are Exceptionally Strong
    Key Message: Demographics, smartphone penetration, and education spending align perfectly with our product
    Strategic Takeaway: 68% of Thailand's 70M population is under age 40, creating massive digital-native audience
    Speaker Notes: Three converging trends create a near-perfect storm of demand for our platform
    Bullets:
    - **Demographics**: 47M people under 40, smartphone penetration at 89% (vs 62% in our home market)
    - **Education Spend**: Households allocate 18% of income to education, highest in Southeast Asia
    - **Digital Adoption**: Online education usage doubled in 2023, now at 12M active learners
    - **Payment Infrastructure**: Mobile payment adoption at 76%, reducing friction for conversion
    ---
    Slide Title: Competition Is Weak But Local Players Have Distribution Advantage
    Key Message: We have superior product but must overcome local brand preference and partnership networks
    Strategic Takeaway: Top competitor (ThaiEdu) has only 15% market share but controls 60% of school partnerships
    Speaker Notes: Market is fragmented with no dominant player, but incumbents have distribution moats we must overcome
    Bullets:
    - **Market Structure**: Top 3 competitors combined = 40% share, remainder split among 20+ small players
    - **Product Gap**: Our NPS (72) is 25 points higher than leading local competitor (47)
    - **Distribution Barrier**: ThaiEdu has 3,000 school partnerships built over 8 years
    - **Brand Challenge**: 78% of users prefer "Thai-built" products, requiring localization not just translation
    ---
    Slide Title: Execution Risks Are Real: Regulation, Localization, Talent
    Key Message: Three critical risks could derail timeline or inflate costs beyond our $12M budget
    Strategic Takeaway: Education tech requires government approval; process takes 6-18 months with 40% rejection rate for foreign companies
    Speaker Notes: These risks are manageable but require active mitigation strategies and contingency planning
    Bullets:
    - **Regulatory Risk**: Education platform approval is unpredictable; need local partner with government relationships
    - **Localization Cost**: Translation is 20% of budget, but cultural adaptation could add another $2M
    - **Talent Scarcity**: Only 200 qualified product managers in Bangkok, all employed; may need to relocate team
    - **Currency Risk**: Thai Baht volatility could add 15% cost overrun in USD terms
    ---
    Slide Title: Recommendation: Staged Entry with $4M Pilot, Scale if Metrics Hit
    Key Message: Launch pilot in Bangkok with clear go/no-go criteria before full $12M commitment
    Strategic Takeaway: Pilot can validate product-market fit and regulatory pathway for 1/3 the cost and risk
    Speaker Notes: A staged approach allows us to validate assumptions and build partnerships before full commitment
    Bullets:
    - **Phase 1 (6 months, $4M)**: Launch in Bangkok, acquire 50K users, secure regulatory approval
    - **Go/No-Go Criteria**: CAC under $15, retention >60% at 90 days, regulatory approval secured
    - **Phase 2 (12 months, $8M)**: Scale nationally if Phase 1 hits metrics, expand to 500K users
    - **Exit Option**: If pilot fails, we limit loss to $4M vs $12M full commitment
    ---
    
    --- YOUR TASK ---
    
    Now create a 5-slide deck following the EXACT format shown above. Use the source document below as input.
    
    CRITICAL REMINDERS:
    - Do NOT use markdown code blocks (no ```)
    - Separate slides with exactly: ---
    - Use field labels exactly as shown (Slide Title:, Key Message:, etc.)
    - Include all 5 required fields for each slide
    - Make every bullet specific and data-driven where possible
    - Ensure bullets start with - and are on separate lines
    
    SOURCE DOCUMENT:
    \"\"\"
    {text}
    \"\"\"
    
    Begin generating the 5-slide deck now, starting with Slide 1:
    """
    return prompt


def validate_slide_structure(slide_data):
    """
    Validates that a parsed slide contains all required fields.
    Used by the parser to filter out malformed slides.
    
    Args:
        slide_data (dict): Parsed slide dictionary
        
    Returns:
        bool: True if slide has minimum required structure
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
    Last resort to ensure user gets *something* rather than total failure.
    
    Args:
        text_chunk (str): Raw text to convert into slide
        slide_number (int): Slide position in deck
        
    Returns:
        dict: Basic slide structure
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
    Useful for logging and monitoring parsing quality.
    
    Args:
        slide_data (dict): Parsed slide dictionary
        
    Returns:
        float: Score from 0.0 to 1.0
    """
    score = 0.0
    
    # Title quality (0.2 points)
    if slide_data.get('title'):
        if len(slide_data['title']) > 20:
            score += 0.2
        else:
            score += 0.1
    
    # Key message (0.2 points)
    if slide_data.get('key_message'):
        if len(slide_data['key_message']) > 30:
            score += 0.2
        else:
            score += 0.1
    
    # Strategic takeaway (0.2 points)
    if slide_data.get('strategic_takeaway'):
        if len(slide_data['strategic_takeaway']) > 20:
            score += 0.2
        else:
            score += 0.1
    
    # Bullets quality (0.3 points)
    bullets = slide_data.get('bullets', [])
    if len(bullets) >= 3:
        score += 0.2
        # Bonus for having good bullet length
        avg_bullet_length = sum(len(b) for b in bullets) / len(bullets)
        if avg_bullet_length > 30:
            score += 0.1
    elif len(bullets) >= 1:
        score += 0.1
    
    # Speaker notes (0.1 points)
    if slide_data.get('notes') and len(slide_data['notes']) > 20:
        score += 0.1
    
    return min(score, 1.0)  # Cap at 1.0