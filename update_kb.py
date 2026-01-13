import asyncio
import os
import re
import json
import base64
from datetime import datetime
from typing import List, Optional, Tuple
from urllib.parse import urlparse

import httpx
from crawl4ai import AsyncWebCrawler
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load environment variables
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ELEVEN_LABS_API_KEY = os.getenv("ELEVEN_LABS_API_KEY")

if not GEMINI_API_KEY:
    print("Error: GEMINI_API_KEY not found in .env")
if not ELEVEN_LABS_API_KEY:
    print("Error: ELEVEN_LABS_API_KEY not found in .env")

# --- Crawling Logic (reused from main.py) ---

async def _crawl_single_url(url: str) -> Tuple[str, Optional[str]]:
    """Helper to crawl a single URL and return markdown + screenshot."""
    async with AsyncWebCrawler() as crawler:
        try:
            print(f"  [Crawler] Fetching: {url}")
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
    for i, b64_img in enumerate(screenshots[:3]):
        contents.append(
            types.Part.from_bytes(
                data=base64.b64decode(b64_img),
                mime_type="image/webp"
            )
        )
    try:
        response = client.models.generate_content(model="gemini-2.5-flash", contents=contents)
        return response.text if response.text else "Failed to clean content."
    except Exception as e:
        print(f"  [Tool] Error in cleaning: {e}")
        return content[:50000]

async def process_url_to_kb(start_url: str) -> str:
    """Crawls and cleans content from a URL."""
    print(f"\n[Process] Starting KB build for: {start_url}")
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    initial_md, initial_ss = await _crawl_single_url(start_url)
    if not initial_md:
        raise Exception("Failed to crawl the starting URL.")

    links = await _extract_links_via_gemini(client, initial_md, start_url)
    print(f"[Process] Found {len(links)} sub-pages to crawl.")

    all_raw_content = f"## Source: {start_url}\n\n{initial_md}\n\n"
    screenshots = [initial_ss] if initial_ss else []
        
    for link in links[:3]:  # Limiting to 3 for speed
        sub_md, sub_ss = await _crawl_single_url(link)
        if sub_md:
            all_raw_content += f"## Source: {link}\n\n{sub_md}\n\n"
            if sub_ss:
                screenshots.append(sub_ss)

    clean_kb = await _clean_content_via_gemini(client, all_raw_content, start_url, screenshots)
    return clean_kb

# --- ElevenLabs API Logic ---

class ElevenLabsClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.elevenlabs.io/v1/convai"
        self.headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json"
        }

    async def create_kb_text(self, name: str, text: str) -> str:
        """Uploads text to ElevenLabs KB and returns documentation_id."""
        url = f"{self.base_url}/knowledge-base/text"
        payload = {
            "text": text,
            "name": name
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=self.headers, json=payload, timeout=60.0)
            response.raise_for_status()
            data = response.json()
            return data["id"]

    async def trigger_rag_index(self, documentation_id: str):
        """Triggers RAG indexing for a document."""
        url = f"{self.base_url}/knowledge-base/{documentation_id}/rag-index"
        payload = {"model": "e5_mistral_7b_instruct"}
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=self.headers, json=payload, timeout=60.0)
            response.raise_for_status()
            return response.json()

    async def get_agent(self, agent_id: str):
        """Fetches agent configuration."""
        url = f"{self.base_url}/agents/{agent_id}"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()

    async def patch_agent(self, agent_id: str, payload: dict):
        """Updates agent configuration."""
        url = f"{self.base_url}/agents/{agent_id}"
        async with httpx.AsyncClient() as client:
            response = await client.patch(url, headers=self.headers, json=payload)
            response.raise_for_status()
            return response.json()

    async def delete_documentation(self, documentation_id: str):
        """Deletes a documentation from the knowledge base."""
        url = f"{self.base_url}/knowledge-base/{documentation_id}"
        async with httpx.AsyncClient() as client:
            response = await client.delete(url, headers=self.headers)
            response.raise_for_status()
            # If response is empty, don't try to parse JSON
            if response.status_code == 200 and not response.content:
                return {"status": "success"}
            return response.json()

# --- Integration Logic ---

async def run_automation():
    if not os.path.exists("kb_config.json"):
        print("Error: kb_config.json not found")
        return

    with open("kb_config.json", "r") as f:
        config = json.load(f)

    el_client = ElevenLabsClient(ELEVEN_LABS_API_KEY)

    for item in config:
        url = item["url"]
        kb_prefix = item["kb_prefix"]
        local_name = item["local_name"]
        local_extension = item["local_extension"]
        agent_ids = item["agent_ids"]

        print(f"\n--- Processing: {kb_prefix} ---")

        # 1. Process URL
        try:
            content = await process_url_to_kb(url)
        except Exception as e:
            print(f"Error processing URL {url}: {e}")
            continue

        # 2. Save local file
        filename = f"{local_name}.{local_extension}"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Saved local file: {filename}")

        # 3. Upload to ElevenLabs
        kb_name = f"{kb_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        print(f"Uploading to ElevenLabs as: {kb_name}")
        try:
            doc_id = await el_client.create_kb_text(kb_name, content)
            print(f"Created KB document with ID: {doc_id}")

            # 4. Trigger RAG index
            print("Triggering RAG indexing...")
            await el_client.trigger_rag_index(doc_id)
        except Exception as e:
            print(f"Error with ElevenLabs KB API: {e}")
            continue

        # 5. Update Agents and Clean Up Old Documents
        docs_to_delete = set()
        for agent_id in agent_ids:
            print(f"Updating agent: {agent_id}")
            try:
                agent_data = await el_client.get_agent(agent_id)
                conv_config = agent_data.get("conversation_config", {})
                
                # ElevenLabs agents can have KB in different locations depending on configuration
                # 1. Directly in conversation_config
                # 2. In conversation_config -> agent -> prompt -> knowledge_base
                
                target_kb_path = None
                current_kb = []
                
                if "knowledge_base" in conv_config:
                    target_kb_path = "root"
                    current_kb = conv_config["knowledge_base"]
                elif "agent" in conv_config and "prompt" in conv_config["agent"] and "knowledge_base" in conv_config["agent"]["prompt"]:
                    target_kb_path = "nested"
                    current_kb = conv_config["agent"]["prompt"]["knowledge_base"]
                else:
                    # Default to root if not found
                    target_kb_path = "root"
                    current_kb = []

                print(f"  Found KB at {target_kb_path} location for agent {agent_id}")
                
                new_kb = []
                for kb_item in current_kb:
                    if kb_item.get("name", "").startswith(kb_prefix):
                        print(f"  Removing old KB document from agent list: {kb_item['name']} ({kb_item['id']})")
                        docs_to_delete.add(kb_item['id'])
                    else:
                        new_kb.append(kb_item)
                
                # Add the new document
                new_kb.append({
                    "type": "text",
                    "name": kb_name,
                    "id": doc_id,
                    "usage_mode": "auto"
                })

                if target_kb_path == "root":
                    patch_payload = {
                        "conversation_config": {
                            "knowledge_base": new_kb
                        }
                    }
                else:
                    patch_payload = {
                        "conversation_config": {
                            "agent": {
                                "prompt": {
                                    "knowledge_base": new_kb
                                }
                            }
                        }
                    }
                
                await el_client.patch_agent(agent_id, patch_payload)
                print(f"Successfully updated agent {agent_id}")

            except Exception as e:
                print(f"Error updating agent {agent_id}: {e}")

        # 6. Delete old documents from ElevenLabs
        for old_doc_id in docs_to_delete:
            print(f"Deleting old document from KB: {old_doc_id}")
            try:
                await el_client.delete_documentation(old_doc_id)
                print(f"  Successfully deleted document {old_doc_id}")
            except Exception as e:
                print(f"  Error deleting document {old_doc_id}: {e}")

if __name__ == "__main__":
    asyncio.run(run_automation())
