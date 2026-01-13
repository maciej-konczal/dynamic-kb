import asyncio
import os
import re
from typing import List, Optional, Tuple
from urllib.parse import urlparse
from dataclasses import dataclass
import base64

from crawl4ai import AsyncWebCrawler
from dotenv import load_dotenv
from google import genai
from google.genai import types  # Import types for multimodal parts
from pydantic_ai import Agent, RunContext

# Load environment variables
load_dotenv()

@dataclass
class CrawlerDeps:
    """Dependencies for the crawler tools."""
    api_key: str
    base_url: Optional[str] = None

# Create the Agent
kb_agent = Agent(
    'google-gla:gemini-2.5-flash',
    deps_type=CrawlerDeps,
    system_prompt=(
        "You are a Knowledge Base Specialist. Your goal is to help users create comprehensive, "
        "clean, and deduplicated knowledge bases from websites. "
        "Use the provided tool to crawl pages and build the KB. "
        "When the tool returns the content, provide a summary of what was collected."
    ),
)

async def _crawl_single_url(url: str) -> Tuple[str, Optional[str]]:
    """Helper to crawl a single URL and return markdown + screenshot."""
    async with AsyncWebCrawler() as crawler:
        try:
            print(f"  [Crawler] Fetching: {url}")
            # Request markdown and a screenshot for visual data extraction
            result = await crawler.arun(url=url, screenshot=True)
            return (result.markdown if result.markdown else "", result.screenshot)
        except Exception as e:
            print(f"  [Crawler] Error fetching {url}: {e}")
            return ("", None)

async def _extract_links_via_gemini(client: genai.Client, markdown: str, start_url: str) -> List[str]:
    """Helper to extract sub-pages using Gemini."""
    prompt = f"""Analyze the markdown and extract ONLY URLs that are sub-pages of {start_url}.
    Requirements:
    - Return ONLY absolute URLs, one per line.
    - No markdown formatting (no backticks, no brackets).
    - No extra text or explanations.
    - The URLs must start with {start_url}
    
    Markdown:
    {markdown[:50000]}
    """
    try:
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        links = []
        if response.text:
            # Robustly extract anything that looks like a URL
            found_urls = re.findall(r'https?://[^\s\)\]`"]+', response.text)
            for url in found_urls:
                url = url.strip().strip('*').strip('-').strip().rstrip('.')
                if url.startswith(start_url) and url != start_url:
                    links.append(url)
        
        return list(set(links))
    except Exception as e:
        print(f"  [Tool] Error extracting links: {e}")
        return []

async def _clean_content_via_gemini(client: genai.Client, content: str, start_url: str, screenshots: List[str]) -> str:
    """Helper to deduplicate and clean content, using vision for screenshots."""
    
    # Construct multimodal parts
    # We add the text prompt first, then any screenshots found
    prompt = f"""Clean and synthesize the following crawled content from {start_url}.
    
    CRITICAL INSTRUCTIONS:
    1. If you see images/screenshots provided, extract ANY information, text, or data present in those images that isn't in the markdown.
    2. Remove navigation, footers, and repetitive boilerplate.
    3. Merge duplicate information.
    4. Organize logically by topic.
    5. Keep only substantive, unique information.
    
    Markdown Content:
    {content[:100000]} 
    """
    
    contents = [prompt]
    
    # Add screenshots as parts if they exist (Gemini 2.5/2.0 can handle multiple images)
    for i, b64_img in enumerate(screenshots[:3]): # Limit to first 3 pages to stay safe with tokens
        contents.append(
            types.Part.from_bytes(
                data=base64.b64decode(b64_img),
                mime_type="image/webp" # crawl4ai typically provides webp
            )
        )

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash", 
            contents=contents
        )
        return response.text if response.text else "Failed to clean content."
    except Exception as e:
        print(f"  [Tool] Error in cleaning: {e}")
        return content[:50000] # Fallback to raw-ish content

@kb_agent.tool
async def build_knowledge_base(ctx: RunContext[CrawlerDeps], start_url: str) -> str:
    """
    Crawls a starting URL, finds its sub-pages, crawls them too, and returns a 
    deduplicated, clean knowledge base in markdown. It uses vision to extract
    data from images and screenshots as well.
    
    Args:
        start_url: The URL to start building the KB from.
    """
    print(f"\n[Tool] Starting Multimodal KB build for: {start_url}")
    client = genai.Client(api_key=ctx.deps.api_key)
    
    # 1. Crawl initial page
    initial_md, initial_ss = await _crawl_single_url(start_url)
    if not initial_md:
        return "Failed to crawl the starting URL."

    # 2. Extract sub-links
    print("[Tool] Extracting sub-links...")
    links = await _extract_links_via_gemini(client, initial_md, start_url)
    print(f"[Tool] Found {len(links)} sub-pages to crawl.")

    # 3. Crawl sub-pages
    all_raw_content = f"## Source: {start_url}\n\n{initial_md}\n\n"
    screenshots = []
    if initial_ss:
        screenshots.append(initial_ss)
        
    for link in links[:3]:  # Limiting to 3 for multimodal speed
        sub_md, sub_ss = await _crawl_single_url(link)
        if sub_md:
            all_raw_content += f"## Source: {link}\n\n{sub_md}\n\n"
            if sub_ss:
                screenshots.append(sub_ss)

    # 4. Final Clean (Multimodal)
    print("[Tool] Cleaning and extracting from images...")
    clean_kb = await _clean_content_via_gemini(client, all_raw_content, start_url, screenshots)
    
    # Save to file
    filename = "agent_kb_output.md"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(clean_kb)
        
    return f"Knowledge base built successfully with {len(links)} sub-pages. Saved to {filename}."

async def main():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not found in .env")
        return

    deps = CrawlerDeps(api_key=api_key)
    
    user_request = "Build a comprehensive knowledge base from https://opn.gov.pl/aktualnosci"
    print(f"User: {user_request}")
    
    try:
        result = await kb_agent.run(user_request, deps=deps)
        # Handle result based on object structure
        if hasattr(result, 'data'):
            print(f"\nAgent: {result.data}")
        else:
            print(f"\nAgent Response: {result}")
    except Exception as e:
        print(f"\nAn error occurred during agent run: {e}")

if __name__ == "__main__":
    asyncio.run(main())
