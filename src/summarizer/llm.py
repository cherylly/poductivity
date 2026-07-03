"""LLM-powered content summarization."""

from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI

from src.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a professional content summarization assistant. Your job is to produce structured summaries that capture the essence of content efficiently.

Rules:
1. Be concise but preserve key insights
2. For interview/conversation content, attribute points to speakers when identifiable
3. For timestamped content, include relevant timestamps
4. Output valid JSON only, no markdown wrapping
5. Write in the same language as the source content"""

SUMMARIZE_PROMPT_TEMPLATE = """Summarize the following {content_type} content.

Title: {title}
Source: {source_name}

Content:
{text}

---

Generate a structured summary in JSON format:
{{
  "thesis": "Core argument or main message in 1-2 sentences",
  "key_points": [
    {{
      "speaker": "Speaker name if identifiable, otherwise null",
      "text": "Key insight or argument",
      "timestamp": "MM:SS if available, otherwise null"
    }}
  ],
  "conclusion": "One sentence takeaway or action item for the reader",
  "tags": ["topic1", "topic2", "topic3"]
}}

Requirements:
- Extract 3-5 key points maximum
- Each key point should be a complete, standalone insight
- Tags should be 2-4 topic keywords
- Keep thesis under 50 words
- Keep each key point under 40 words"""


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

    prompt = SUMMARIZE_PROMPT_TEMPLATE.format(
        content_type=content_type,
        title=title,
        source_name=source_name,
        text=text,
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
