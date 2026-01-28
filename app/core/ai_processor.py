"""AI content processing module using Google Gemini."""

import re
import base64
from typing import Optional

from google import genai
from google.genai import types


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

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
        link_extraction_prompt: Optional[str] = None,
        content_cleaning_prompt: Optional[str] = None,
    ):
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.link_extraction_prompt = link_extraction_prompt or self.DEFAULT_LINK_EXTRACTION_PROMPT
        self.content_cleaning_prompt = content_cleaning_prompt or self.DEFAULT_CONTENT_CLEANING_PROMPT

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

        try:
            response = self.client.models.generate_content(
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

            return list(set(links))
        except Exception as e:
            print(f"[AIProcessor] Error extracting links: {e}")
            return []

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
            for b64_img in screenshots[:3]:
                try:
                    contents.append(
                        types.Part.from_bytes(
                            data=base64.b64decode(b64_img),
                            mime_type="image/webp",
                        )
                    )
                except Exception as e:
                    print(f"[AIProcessor] Error processing screenshot: {e}")

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
            )
            return response.text if response.text else "Failed to clean content."
        except Exception as e:
            print(f"[AIProcessor] Error cleaning content: {e}")
            return content[:50000]  # Return truncated raw content as fallback
