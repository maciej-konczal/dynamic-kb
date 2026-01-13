import asyncio
import os
import re
from urllib.parse import urlparse
from crawl4ai import AsyncWebCrawler
from dotenv import load_dotenv
from google import genai

# Load environment variables
load_dotenv()

def extract_domain(url: str) -> str:
    """Extract domain from URL."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"

async def get_links_from_gemini(markdown_content: str, start_url: str, base_domain: str) -> list[str]:
    """Use Gemini to extract sub-pages of the starting URL that should be crawled."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in .env file")
    
    client = genai.Client(api_key=api_key)
    
    prompt = f"""Analyze the following markdown content and extract ONLY URLs/links that are sub-pages of {start_url}.

Requirements:
- ONLY include links that start with {start_url} (sub-pages of this specific path)
- These should be direct child pages or deeper pages under {start_url}
- Focus on content pages (not navigation, footer, or utility links)
- Pages with substantial information
- Avoid: social media links, external sites, image URLs, CSS/JS files, anchor links (#), tel: or mailto: links
- If a URL is relative (starts with /), convert it to absolute by prepending {base_domain}
- Only include URLs that are clearly sub-pages of {start_url}

Return ONLY a list of URLs, one per line, with no additional text or formatting.
Each URL must start with {start_url}

Here's the markdown:
""" + markdown_content
    
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )
    links_text = response.text.strip()
    
    # Log Gemini response
    print("\n" + "=" * 80)
    print("GEMINI RAW RESPONSE:")
    print("=" * 80)
    print(links_text)
    print("=" * 80 + "\n")
    
    # Extract URLs from the response
    urls = []
    for line in links_text.split('\n'):
        line = line.strip()
        if not line:
            continue
        
        # Remove markdown link formatting if present
        match = re.search(r'https?://[^\s\)\]]+', line)
        if match:
            url = match.group(0).rstrip(')').rstrip(']').rstrip('.')
            urls.append(url)
        elif line.startswith('http'):
            urls.append(line.rstrip('.'))
        elif line.startswith('/'):
            urls.append(f"{base_domain}{line}")
    
    # Log extracted URLs before filtering
    print(f"Extracted {len(urls)} URLs from Gemini response (before filtering):")
    for url in urls[:20]:  # Show first 20
        print(f"  - {url}")
    if len(urls) > 20:
        print(f"  ... and {len(urls) - 20} more")
    print()
    
    # Filter to only sub-pages of start_url and remove duplicates
    unique_urls = []
    seen = set()
    for url in urls:
        # Only include URLs that are sub-pages of start_url
        if not url.startswith(start_url):
            continue
        
        # Skip unwanted URLs
        if any(skip in url.lower() for skip in ['facebook', 'instagram', 'youtube', '.jpg', '.png', '.webp', '.svg', '.css', '.js', 'tel:', 'mailto:', '#']):
            continue
        
        # Remove fragments
        url = url.split('#')[0]
        
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)
    
    print(f"After filtering (sub-pages of {start_url} + cleanup): {len(unique_urls)} unique URLs\n")
    
    return unique_urls

async def crawl_url(url: str) -> str:
    """Crawl a single URL and return its markdown content."""
    async with AsyncWebCrawler() as crawler:
        try:
            print(f"Crawling: {url}")
            result = await crawler.arun(url=url)
            return result.markdown if result.markdown else ""
        except Exception as e:
            print(f"Error crawling {url}: {e}")
            return ""

async def crawl_urls(urls: list[str]) -> list[tuple[str, str]]:
    """Crawl multiple URLs and return their markdown content with URLs."""
    results = []
    async with AsyncWebCrawler() as crawler:
        for url in urls:
            try:
                print(f"Crawling: {url}")
                result = await crawler.arun(url=url)
                if result.markdown:
                    results.append((url, result.markdown))
            except Exception as e:
                print(f"Error crawling {url}: {e}")
                continue
    return results

async def clean_content_with_gemini(content: str, start_url: str) -> str:
    """Use Gemini to clean up content, remove repetitive stuff, and extract only necessary info."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in .env file")
    
    client = genai.Client(api_key=api_key)
    
    # Use a larger limit for Gemini 2.5 Flash (can handle ~1M tokens)
    # But be conservative and use ~200k characters to be safe
    content_limit = 200000
    content_to_clean = content[:content_limit] if len(content) > content_limit else content
    
    if len(content) > content_limit:
        print(f"Warning: Content is {len(content)} characters, using first {content_limit} for cleaning")
    
    prompt = f"""Analyze the following crawled content from {start_url} and its sub-pages. Clean it up by:

1. Remove repetitive content (navigation menus, footers, headers that appear on every page)
2. Remove duplicate information that appears across multiple pages
3. Extract only the actual, unique information from each page
4. Keep all substantive content, facts, and information
5. Maintain the structure but remove boilerplate
6. Preserve important details like dates, events, contact info, etc.
7. Remove common website elements like "Przejdź do menu", language switchers, search boxes, etc.
8. Organize content logically by topic/page
9. Remove redundant sections that repeat across pages

Return the cleaned content in markdown format, organized logically by topic/page. Keep all unique and valuable information.

Original content:
""" + content_to_clean
    
    print("\n" + "=" * 80)
    print("CLEANING CONTENT WITH GEMINI...")
    print("=" * 80)
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        
        cleaned_content = response.text.strip()
        
        print(f"Content cleaned. Original length: {len(content)} characters")
        print(f"Cleaned length: {len(cleaned_content)} characters\n")
        
        return cleaned_content
    except Exception as e:
        print(f"Error cleaning content with Gemini: {e}")
        print("Returning original content without cleaning.")
        return content

async def crawl_and_concatenate(start_url: str, output_file: str = "concatenated_output.md"):
    """
    Main method to crawl a URL, extract same-domain links, crawl them, and concatenate results.
    
    Args:
        start_url: The initial URL to crawl (e.g., https://opn.gov.pl/aktualnosci)
        output_file: Name of the output markdown file
    """
    base_domain = extract_domain(start_url)
    print(f"Starting crawl from: {start_url}")
    print(f"Base domain: {base_domain}\n")
    
    # Step 1: Crawl the initial URL
    print("=" * 80)
    print("STEP 1: Crawling initial URL")
    print("=" * 80)
    initial_markdown = await crawl_url(start_url)
    
    if not initial_markdown:
        print("Failed to crawl initial URL. Exiting.")
        return
    
    print(f"Initial crawl completed. Content length: {len(initial_markdown)} characters\n")
    
    # Step 2: Extract links using Gemini
    print("=" * 80)
    print("STEP 2: Extracting sub-pages using Gemini")
    print("=" * 80)
    links = await get_links_from_gemini(initial_markdown, start_url, base_domain)
    
    # Remove the start_url from links if present
    links = [link for link in links if link != start_url]
    
    print(f"Found {len(links)} links to crawl:")
    for link in links[:10]:  # Show first 10
        print(f"  - {link}")
    if len(links) > 10:
        print(f"  ... and {len(links) - 10} more")
    print()
    
    # Step 3: Crawl the extracted links
    print("=" * 80)
    print("STEP 3: Crawling extracted links")
    print("=" * 80)
    crawled_results = await crawl_urls(links)
    print(f"Successfully crawled {len(crawled_results)} additional pages\n")
    
    # Step 4: Concatenate all results
    print("=" * 80)
    print("STEP 4: Concatenating results")
    print("=" * 80)
    
    all_content = f"# Crawled Content from {start_url}\n\n"
    all_content += f"Generated from: {start_url}\n"
    all_content += f"Base domain: {base_domain}\n"
    all_content += f"Total pages crawled: {len(crawled_results) + 1}\n\n"
    all_content += "=" * 80 + "\n\n"
    
    # Add initial content
    all_content += f"## Initial Page: {start_url}\n\n"
    all_content += initial_markdown
    all_content += "\n\n"
    
    # Add crawled content
    if crawled_results:
        all_content += "=" * 80 + "\n"
        all_content += "## Additional Crawled Pages\n"
        all_content += "=" * 80 + "\n\n"
        
        for url, markdown in crawled_results:
            all_content += f"### {url}\n\n"
            all_content += markdown
            all_content += "\n\n" + "-" * 80 + "\n\n"
    
    # Step 5: Clean content with Gemini
    print("=" * 80)
    print("STEP 5: Cleaning content with Gemini")
    print("=" * 80)
    cleaned_content = await clean_content_with_gemini(all_content, start_url)
    
    # Save cleaned result
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(cleaned_content)
    
    print(f"Cleaned output saved to {output_file}")
    print(f"Original length: {len(all_content)} characters")
    print(f"Cleaned length: {len(cleaned_content)} characters")
    print(f"Total pages: {len(crawled_results) + 1}")

async def main():
    # Example usage
    start_url = "https://opn.gov.pl/aktualnosci"
    await crawl_and_concatenate(start_url)

if __name__ == "__main__":
    asyncio.run(main())