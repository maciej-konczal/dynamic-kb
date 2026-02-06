"""LLM-based content quality assessment module."""

import asyncio
import json
from dataclasses import dataclass, field
from typing import Literal, Optional

from google import genai

from app.core.logging import get_logger
from app.core.exceptions import AIProcessorError
from app.core.observability import LangfuseTrace, is_langfuse_enabled, flush_langfuse
from app.core.metrics import (
    AI_REQUESTS_TOTAL,
    AI_DURATION_SECONDS,
    record_ai_retry,
    record_ai_tokens,
)

logger = get_logger("quality_assessor")


@dataclass
class QualityResult:
    """Result of content quality assessment."""

    score: int  # 0-100 integer
    issues: list[str] = field(default_factory=list)
    recommendation: Literal["approve", "review", "reject"] = "review"
    details: dict = field(default_factory=dict)

    def to_json(self) -> str:
        """Serialize to JSON string for storage."""
        return json.dumps({
            "score": self.score,
            "issues": self.issues,
            "recommendation": self.recommendation,
            "details": self.details,
        })

    @classmethod
    def from_json(cls, json_str: str) -> "QualityResult":
        """Deserialize from JSON string."""
        data = json.loads(json_str)
        return cls(
            score=data.get("score", 0),
            issues=data.get("issues", []),
            recommendation=data.get("recommendation", "review"),
            details=data.get("details", {}),
        )


class QualityAssessor:
    """LLM-based content quality assessment using Gemini."""

    QUALITY_ASSESSMENT_PROMPT = """Analyze the following scraped and cleaned content for quality.

Source URL: {source_url}

Content to assess:
{content}

Evaluate the content on these criteria (each 0-20 points):
1. **Completeness** (0-20): Is the content complete and not truncated? Does it cover the topic adequately?
2. **Formatting** (0-20): Is the markdown well-structured with proper headings, lists, and formatting?
3. **Information Density** (0-20): Does it contain substantive information vs just boilerplate/navigation?
4. **Coherence** (0-20): Is the content readable, logical, and well-organized?
5. **Relevance** (0-20): Is the content relevant to the source URL topic?

Return your assessment as JSON with this exact structure:
{{
    "scores": {{
        "completeness": <0-20>,
        "formatting": <0-20>,
        "information_density": <0-20>,
        "coherence": <0-20>,
        "relevance": <0-20>
    }},
    "total_score": <0-100>,
    "issues": ["list of specific issues found"],
    "recommendation": "approve" | "review" | "reject"
}}

Guidelines for recommendation:
- "approve": Score >= 80 and no critical issues
- "reject": Score <= 30 or has critical issues (empty, garbled, completely off-topic)
- "review": Everything else (needs human review)

Return ONLY the JSON, no other text.
"""

    # Error types that should not be retried
    NON_RETRYABLE_ERRORS = (
        "quota",
        "authentication",
        "unauthorized",
        "api_key",
        "permission",
        "invalid_api_key",
        "403",
        "401",
        "429",
    )

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
        timeout: float = 60.0,
        max_retries: int = 3,
    ):
        """Initialize the quality assessor.

        Args:
            api_key: Google Gemini API key
            model: Gemini model to use
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
        """
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries

    def _is_retryable_error(self, error: Exception) -> bool:
        """Check if an error should be retried."""
        error_str = str(error).lower()
        for non_retryable in self.NON_RETRYABLE_ERRORS:
            if non_retryable in error_str:
                return False
        return True

    def _extract_token_usage(self, response) -> dict:
        """Extract token usage from Gemini response if available."""
        usage = {}
        try:
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                metadata = response.usage_metadata
                if hasattr(metadata, 'prompt_token_count'):
                    usage['prompt_tokens'] = metadata.prompt_token_count
                if hasattr(metadata, 'candidates_token_count'):
                    usage['completion_tokens'] = metadata.candidates_token_count
                if hasattr(metadata, 'total_token_count'):
                    usage['total_tokens'] = metadata.total_token_count
        except Exception as e:
            logger.debug(f"Could not extract token usage: {e}")
        return usage

    async def _call_with_retry(self, func, operation: str, *args, **kwargs):
        """Call a function with retry logic and exponential backoff."""
        last_error = None

        for attempt in range(self.max_retries):
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(func, *args, **kwargs),
                    timeout=self.timeout,
                )
            except asyncio.TimeoutError:
                last_error = AIProcessorError(f"Request timed out after {self.timeout}s")
                logger.warning(f"Attempt {attempt + 1}/{self.max_retries} timed out")
                record_ai_retry(operation=operation, model=self.model)
            except Exception as e:
                last_error = e
                if not self._is_retryable_error(e):
                    logger.error(f"Non-retryable error: {e}")
                    raise AIProcessorError(f"Quality assessment failed: {e}") from e
                logger.warning(f"Attempt {attempt + 1}/{self.max_retries} failed: {e}")
                record_ai_retry(operation=operation, model=self.model)

            if attempt < self.max_retries - 1:
                backoff = 2 ** attempt  # 1s, 2s, 4s
                logger.info(f"Retrying in {backoff}s...")
                await asyncio.sleep(backoff)

        raise AIProcessorError(f"Quality assessment failed after {self.max_retries} attempts: {last_error}")

    def _parse_quality_response(self, response_text: str) -> QualityResult:
        """Parse the LLM response into a QualityResult."""
        try:
            # Try to extract JSON from the response
            text = response_text.strip()

            # Handle markdown code blocks
            if text.startswith("```json"):
                text = text[7:]
            elif text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

            data = json.loads(text)

            scores = data.get("scores", {})
            total_score = data.get("total_score", 0)

            # Validate total score is sum of individual scores
            if scores:
                calculated_total = sum(scores.values())
                if abs(calculated_total - total_score) > 5:  # Allow small discrepancy
                    total_score = calculated_total

            # Clamp score to valid range
            total_score = max(0, min(100, int(total_score)))

            issues = data.get("issues", [])
            recommendation = data.get("recommendation", "review")

            # Validate recommendation
            if recommendation not in ("approve", "review", "reject"):
                recommendation = "review"

            return QualityResult(
                score=total_score,
                issues=issues if isinstance(issues, list) else [],
                recommendation=recommendation,
                details={"scores": scores} if scores else {},
            )

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse quality assessment JSON: {e}")
            # Return a default "needs review" result if parsing fails
            return QualityResult(
                score=50,
                issues=["Failed to parse quality assessment"],
                recommendation="review",
                details={"parse_error": str(e)},
            )

    async def assess_quality(
        self,
        content: str,
        source_url: str,
        session_id: Optional[str] = None,
    ) -> QualityResult:
        """Assess the quality of scraped content.

        Args:
            content: The cleaned content to assess
            source_url: The source URL for context
            session_id: Optional Langfuse session ID

        Returns:
            QualityResult with score, issues, and recommendation
        """
        import time
        start_time = time.time()
        operation = "assess_quality"

        # Limit content size for assessment (use first ~50k chars)
        content_sample = content[:50000]

        prompt = self.QUALITY_ASSESSMENT_PROMPT.format(
            source_url=source_url,
            content=content_sample,
        )

        logger.info(f"Assessing quality for content from {source_url}")

        # Create Langfuse trace for this operation
        with LangfuseTrace(
            name="assess_quality",
            session_id=session_id,
            metadata={"source_url": source_url, "content_length": len(content)},
            tags=["ai", "quality_assessment"],
        ) as trace:
            try:
                with trace.generation(
                    name="gemini_assess_quality",
                    model=self.model,
                    input=prompt[:1000] + "..." if len(prompt) > 1000 else prompt,
                    metadata={"full_prompt_length": len(prompt)},
                ) as gen:
                    response = await self._call_with_retry(
                        self.client.models.generate_content,
                        operation,
                        model=self.model,
                        contents=prompt,
                    )

                    response_text = response.text if response.text else ""

                    # Extract and record token usage
                    usage = self._extract_token_usage(response)
                    if usage:
                        record_ai_tokens(
                            operation=operation,
                            model=self.model,
                            prompt_tokens=usage.get('prompt_tokens', 0),
                            completion_tokens=usage.get('completion_tokens', 0),
                        )
                        gen.set_output(response_text[:500] + "..." if len(response_text) > 500 else response_text, usage=usage)
                    else:
                        gen.set_output(response_text[:500] + "..." if len(response_text) > 500 else response_text)

                # Parse the response
                result = self._parse_quality_response(response_text)

                logger.info(f"Quality assessment complete: score={result.score}, recommendation={result.recommendation}")

                # Record metrics
                duration = time.time() - start_time
                AI_REQUESTS_TOTAL.labels(operation=operation, model=self.model, status="success").inc()
                AI_DURATION_SECONDS.labels(operation=operation, model=self.model).observe(duration)

                # Flush Langfuse to ensure data is sent
                if is_langfuse_enabled():
                    flush_langfuse()

                return result

            except AIProcessorError:
                duration = time.time() - start_time
                AI_REQUESTS_TOTAL.labels(operation=operation, model=self.model, status="error").inc()
                AI_DURATION_SECONDS.labels(operation=operation, model=self.model).observe(duration)
                raise
            except Exception as e:
                duration = time.time() - start_time
                AI_REQUESTS_TOTAL.labels(operation=operation, model=self.model, status="error").inc()
                AI_DURATION_SECONDS.labels(operation=operation, model=self.model).observe(duration)
                logger.error(f"Error assessing quality: {e}")
                raise AIProcessorError(f"Failed to assess quality: {e}") from e
