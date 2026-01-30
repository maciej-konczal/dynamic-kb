"""AI content processing module using Google Gemini."""

import asyncio
import re
import base64
from typing import Optional

from google import genai
from google.genai import types

from app.core.logging import get_logger
from app.core.exceptions import AIProcessorError

logger = get_logger("ai_processor")


class AIProcessor:
    """AI processor for link extraction and content cleaning using Gemini."""

    DEFAULT_LINK_EXTRACTION_PROMPT = """Analyze the markdown and extract ONLY URLs that are sub-pages of {start_url}.
Requirements:
- Return ONLY absolute URLs, one per line.
- No markdown formatting (no backticks, no brackets).
- No extra text or explanations.
- The URLs must start with {start_url}

Markdown:
{content}
"""

    DEFAULT_CONTENT_CLEANING_PROMPT = """Clean and synthesize the following crawled content from {start_url}.

CRITICAL INSTRUCTIONS:
1. If you see images/screenshots provided, extract ANY information, text, or data present in those images that isn't in the markdown.
2. Remove navigation, footers, and repetitive boilerplate.
3. Merge duplicate information.
4. Organize logically by topic.
5. Keep only substantive, unique information.
6. Format the output as clean, readable markdown suitable for a voice assistant knowledge base.

Markdown Content:
{content}
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
        "429",  # Rate limit - could retry but with longer backoff
    )

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
        link_extraction_prompt: Optional[str] = None,
        content_cleaning_prompt: Optional[str] = None,
        timeout: float = 60.0,
        max_retries: int = 3,
    ):
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.link_extraction_prompt = link_extraction_prompt or self.DEFAULT_LINK_EXTRACTION_PROMPT
        self.content_cleaning_prompt = content_cleaning_prompt or self.DEFAULT_CONTENT_CLEANING_PROMPT
        self.timeout = timeout
        self.max_retries = max_retries

    def _is_retryable_error(self, error: Exception) -> bool:
        """Check if an error should be retried."""
        error_str = str(error).lower()
        for non_retryable in self.NON_RETRYABLE_ERRORS:
            if non_retryable in error_str:
                return False
        return True

    async def _call_with_retry(self, func, *args, **kwargs):
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
            except Exception as e:
                last_error = e
                if not self._is_retryable_error(e):
                    logger.error(f"Non-retryable error: {e}")
                    raise AIProcessorError(f"AI processing failed: {e}") from e
                logger.warning(f"Attempt {attempt + 1}/{self.max_retries} failed: {e}")

            if attempt < self.max_retries - 1:
                backoff = 2 ** attempt  # 1s, 2s, 4s
                logger.info(f"Retrying in {backoff}s...")
                await asyncio.sleep(backoff)

        raise AIProcessorError(f"AI processing failed after {self.max_retries} attempts: {last_error}")

    async def extract_links(
        self,
        markdown: str,
        start_url: str,
        custom_prompt: Optional[str] = None,
    ) -> list[str]:
        """Extract sub-page URLs from markdown content using AI."""
        prompt_template = custom_prompt or self.link_extraction_prompt
        prompt = prompt_template.format(
            start_url=start_url,
            content=markdown[:50000],  # Limit content size
        )

        logger.info(f"Extracting links from content for {start_url}")

        try:
            response = await self._call_with_retry(
                self.client.models.generate_content,
                model=self.model,
                contents=prompt,
            )

            links = []
            if response.text:
                # Extract domain from start_url for filtering
                from urllib.parse import urlparse
                parsed = urlparse(start_url)
                domain_base = f"{parsed.scheme}://{parsed.netloc}"

                # Robustly extract URLs from response
                found_urls = re.findall(r'https?://[^\s\)\]`"]+', response.text)
                for url in found_urls:
                    url = url.strip().strip('*').strip('-').strip().rstrip('.')
                    # Accept any URL from the same domain
                    if url.startswith(domain_base) and url != start_url:
                        links.append(url)

            unique_links = list(set(links))
            logger.info(f"Extracted {len(unique_links)} unique links")
            return unique_links
        except AIProcessorError:
            raise
        except Exception as e:
            logger.error(f"Error extracting links: {e}")
            raise AIProcessorError(f"Failed to extract links: {e}") from e

    async def clean_content(
        self,
        content: str,
        start_url: str,
        screenshots: Optional[list[str]] = None,
        custom_prompt: Optional[str] = None,
    ) -> str:
        """Clean and deduplicate content using AI with optional multimodal vision."""
        prompt_template = custom_prompt or self.content_cleaning_prompt
        prompt = prompt_template.format(
            start_url=start_url,
            content=content[:100000],  # Limit content size
        )

        # Build multimodal content
        contents: list = [prompt]

        # Add screenshots if available (limit to 3 for token management)
        if screenshots:
            logger.info(f"Including {min(len(screenshots), 3)} screenshots in content cleaning")
            for b64_img in screenshots[:3]:
                try:
                    contents.append(
                        types.Part.from_bytes(
                            data=base64.b64decode(b64_img),
                            mime_type="image/webp",
                        )
                    )
                except Exception as e:
                    logger.warning(f"Error processing screenshot: {e}")

        logger.info(f"Cleaning content for {start_url}")

        try:
            response = await self._call_with_retry(
                self.client.models.generate_content,
                model=self.model,
                contents=contents,
            )
            result = response.text if response.text else "Failed to clean content."
            logger.info(f"Content cleaned successfully ({len(result)} chars)")
            return result
        except AIProcessorError:
            raise
        except Exception as e:
            logger.error(f"Error cleaning content: {e}")
            raise AIProcessorError(f"Failed to clean content: {e}") from e
