"""LLM-powered content summarization."""

from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI

from src.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert content analyst who produces comprehensive, detailed summaries. Your summaries should capture ALL important ideas, frameworks, examples, and actionable advice from the source material. A reader should be able to understand the full depth of the content from your summary alone.

Rules:
1. Be thorough — extract EVERY meaningful insight, not just the top 3-5
2. For interview/conversation content, attribute points to speakers when identifiable
3. For timestamped content, include relevant timestamps
4. Preserve specific examples, numbers, frameworks, and actionable tactics
5. Output valid JSON only, no markdown wrapping
6. Write in the same language as the source content"""

def _estimate_duration_tier(text: str) -> str:
    """Estimate content length tier from text character count.

    Rough heuristic: ~150 words/min speech, ~5 chars/word EN, ~1.5 chars/word ZH.
    Transcript of 1 min ≈ 600-750 chars.
    """
    length = len(text)
    if length < 1500:        # < ~2 min
        return "very_short"
    elif length < 5000:      # ~2-7 min
        return "short"
    elif length < 20000:     # ~7-30 min
        return "medium"
    elif length < 60000:     # ~30-90 min
        return "long"
    else:                    # 90 min+
        return "very_long"


TIER_GUIDELINES = {
    "very_short": "2-3 key points, 1-2 actionable takeaways, thesis 1-2 sentences, conclusion 1 sentence",
    "short":      "3-5 key points, 2-3 actionable takeaways, thesis 1-2 sentences, conclusion 1-2 sentences",
    "medium":     "5-8 key points, 3-4 actionable takeaways, thesis 2-3 sentences, conclusion 2 sentences",
    "long":       "8-12 key points, 4-5 actionable takeaways, thesis 2-4 sentences, conclusion 2-3 sentences",
    "very_long":  "10-15 key points, 5-7 actionable takeaways, thesis 2-4 sentences, conclusion 2-3 sentences",
}


SUMMARIZE_PROMPT_TEMPLATE = """Produce a summary of the following {content_type} content.
Adjust summary depth to match the content's length — short content deserves a concise summary; long content deserves a thorough one.

Title: {title}
Source: {source_name}
Content length tier: {length_tier}
Guideline for this tier: {tier_guideline}

Content:
{text}

---

Generate a structured summary in JSON format:
{{
  "thesis": "Core argument or main message. Length should match the tier guideline above.",
  "key_points": [
    {{
      "topic": "Short topic label for this point",
      "speaker": "Speaker name if identifiable, otherwise null",
      "text": "Explanation of this insight with specific examples or data if available. 1-3 sentences depending on tier.",
      "timestamp": "MM:SS if available, otherwise null"
    }}
  ],
  "actionable_takeaways": [
    "Specific, concrete action the reader can take immediately"
  ],
  "conclusion": "Synthesis of the overall message. Length should match the tier guideline above.",
  "tags": ["topic1", "topic2", "topic3", "topic4", "topic5"]
}}

Requirements:
- STRICTLY follow the tier guideline for number of key points and takeaways — do NOT over-extract from short content
- Each key point should preserve specific examples, numbers, and frameworks when present
- Tags should be 3-5 topic keywords
- For podcasts/interviews: capture each speaker's unique perspective
- For tutorials/how-to: preserve step-by-step details and specific techniques"""


async def generate_summary(
    text: str,
    title: str,
    content_type: str,
    source_name: str = "",
) -> dict | None:
    """Generate a structured summary using LLM.

    Returns dict with keys: thesis, key_points, conclusion, tags
    Returns None if generation fails.
    """
    if not text or not text.strip():
        logger.warning(f"Empty text for entry: {title}")
        return None

    # Truncate very long texts to stay within context window
    max_chars = 60000  # ~15k tokens for most models
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[... content truncated ...]"

    tier = _estimate_duration_tier(text)
    prompt = SUMMARIZE_PROMPT_TEMPLATE.format(
        content_type=content_type,
        title=title,
        source_name=source_name,
        text=text,
        length_tier=tier,
        tier_guideline=TIER_GUIDELINES[tier],
    )

    client = AsyncOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.anthropic_auth_token,
    )

    try:
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=settings.llm_max_tokens,
            timeout=settings.llm_timeout,
        )

        content = response.choices[0].message.content.strip()

        # Strip markdown code fences if present
        if content.startswith("```"):
            content = content.split("\n", 1)[1]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

        summary = json.loads(content)

        # Validate required fields
        required_fields = ["thesis", "key_points", "conclusion"]
        for field in required_fields:
            if field not in summary:
                logger.error(f"Missing field '{field}' in LLM response for: {title}")
                return None

        if not isinstance(summary["key_points"], list):
            logger.error(f"key_points is not a list for: {title}")
            return None

        summary.setdefault("tags", [])
        return summary

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM JSON response for '{title}': {e}")
        return None
    except Exception as e:
        logger.error(f"LLM summarization failed for '{title}': {e}")
        return None
