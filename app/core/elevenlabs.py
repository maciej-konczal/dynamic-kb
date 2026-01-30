"""ElevenLabs ConvAI API client for knowledge base management."""

from typing import Optional
from dataclasses import dataclass

import httpx

from app.core.logging import get_logger
from app.core.exceptions import ElevenLabsError

logger = get_logger("elevenlabs")


@dataclass
class KBDocument:
    """Represents a knowledge base document."""

    id: str
    name: str
    type: str = "text"
    usage_mode: str = "auto"


class ElevenLabsClient:
    """Client for ElevenLabs ConvAI API."""

    def __init__(self, api_key: str, timeout: float = 60.0, max_retries: int = 3):
        self.api_key = api_key
        self.base_url = "https://api.elevenlabs.io/v1/convai"
        self.headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        self.timeout = timeout
        self.max_retries = max_retries

    async def _request(
        self,
        method: str,
        endpoint: str,
        json: Optional[dict] = None,
    ) -> dict:
        """Make an HTTP request with retries."""
        url = f"{self.base_url}/{endpoint}"
        last_error = None

        for attempt in range(self.max_retries):
            try:
                logger.debug(f"Request: {method} {endpoint} (attempt {attempt + 1})")
                async with httpx.AsyncClient() as client:
                    response = await client.request(
                        method=method,
                        url=url,
                        headers=self.headers,
                        json=json,
                        timeout=self.timeout,
                    )
                    response.raise_for_status()

                    # Handle empty responses
                    if not response.content:
                        return {"status": "success"}
                    return response.json()
            except httpx.HTTPStatusError as e:
                last_error = e
                status_code = e.response.status_code
                if status_code >= 500:
                    logger.warning(f"Server error ({status_code}), retrying...")
                    continue  # Retry on server errors
                logger.error(f"HTTP error: {status_code} - {e.response.text}")
                raise ElevenLabsError(f"ElevenLabs API error ({status_code}): {e.response.text}") from e
            except httpx.RequestError as e:
                last_error = e
                logger.warning(f"Request error (attempt {attempt + 1}): {e}")
                if attempt < self.max_retries - 1:
                    continue
                raise ElevenLabsError(f"ElevenLabs request failed: {e}") from e

        raise ElevenLabsError(f"ElevenLabs request failed after {self.max_retries} retries: {last_error}")

    async def create_kb_text(self, name: str, text: str) -> str:
        """Upload text to ElevenLabs KB and return the document ID."""
        logger.info(f"Creating KB document: {name}")
        data = await self._request(
            method="POST",
            endpoint="knowledge-base/text",
            json={"text": text, "name": name},
        )
        doc_id = data["id"]
        logger.info(f"Created KB document: {doc_id}")
        return doc_id

    async def trigger_rag_index(
        self,
        documentation_id: str,
        model: str = "e5_mistral_7b_instruct",
    ) -> dict:
        """Trigger RAG indexing for a document."""
        logger.info(f"Triggering RAG indexing for document: {documentation_id}")
        result = await self._request(
            method="POST",
            endpoint=f"knowledge-base/{documentation_id}/rag-index",
            json={"model": model},
        )
        logger.info(f"RAG indexing triggered for: {documentation_id}")
        return result

    async def get_kb_document(self, documentation_id: str) -> dict:
        """Get details of a knowledge base document."""
        logger.debug(f"Getting KB document: {documentation_id}")
        return await self._request(
            method="GET",
            endpoint=f"knowledge-base/{documentation_id}",
        )

    async def list_kb_documents(self) -> list[dict]:
        """List all knowledge base documents."""
        logger.debug("Listing KB documents")
        data = await self._request(
            method="GET",
            endpoint="knowledge-base",
        )
        return data.get("documents", [])

    async def delete_kb_document(self, documentation_id: str) -> dict:
        """Delete a knowledge base document."""
        logger.info(f"Deleting KB document: {documentation_id}")
        result = await self._request(
            method="DELETE",
            endpoint=f"knowledge-base/{documentation_id}",
        )
        logger.info(f"Deleted KB document: {documentation_id}")
        return result

    async def get_agent(self, agent_id: str) -> dict:
        """Get agent configuration."""
        logger.debug(f"Getting agent: {agent_id}")
        return await self._request(
            method="GET",
            endpoint=f"agents/{agent_id}",
        )

    async def list_agents(self) -> list[dict]:
        """List all agents (lightweight call for API validation)."""
        logger.debug("Listing agents")
        data = await self._request(
            method="GET",
            endpoint="agents",
        )
        return data.get("agents", [])

    async def patch_agent(self, agent_id: str, payload: dict) -> dict:
        """Update agent configuration."""
        logger.info(f"Updating agent: {agent_id}")
        return await self._request(
            method="PATCH",
            endpoint=f"agents/{agent_id}",
            json=payload,
        )

    async def update_agent_kb(
        self,
        agent_id: str,
        new_doc: KBDocument,
        kb_prefix: str,
        remove_old: bool = True,
    ) -> tuple[list[str], bool]:
        """
        Update an agent's knowledge base with a new document.

        Returns:
            Tuple of (list of removed doc IDs, success boolean)
        """
        removed_docs = []

        try:
            agent_data = await self.get_agent(agent_id)
            conv_config = agent_data.get("conversation_config", {})

            # Determine KB location in agent config
            target_kb_path = "root"
            current_kb = []

            if "knowledge_base" in conv_config:
                target_kb_path = "root"
                current_kb = conv_config["knowledge_base"]
            elif (
                "agent" in conv_config
                and "prompt" in conv_config.get("agent", {})
                and "knowledge_base" in conv_config["agent"]["prompt"]
            ):
                target_kb_path = "nested"
                current_kb = conv_config["agent"]["prompt"]["knowledge_base"]

            # Build new KB list
            new_kb = []
            for kb_item in current_kb:
                if remove_old and kb_item.get("name", "").startswith(kb_prefix):
                    removed_docs.append(kb_item["id"])
                    logger.info(f"Removing old KB document: {kb_item['id']}")
                else:
                    new_kb.append(kb_item)

            # Add the new document
            new_kb.append({
                "type": new_doc.type,
                "name": new_doc.name,
                "id": new_doc.id,
                "usage_mode": new_doc.usage_mode,
            })

            # Build patch payload based on KB location
            if target_kb_path == "root":
                patch_payload = {
                    "conversation_config": {
                        "knowledge_base": new_kb,
                    }
                }
            else:
                patch_payload = {
                    "conversation_config": {
                        "agent": {
                            "prompt": {
                                "knowledge_base": new_kb,
                            }
                        }
                    }
                }

            await self.patch_agent(agent_id, patch_payload)
            logger.info(f"Updated agent {agent_id} with new KB document: {new_doc.id}")
            return removed_docs, True

        except ElevenLabsError:
            raise
        except Exception as e:
            logger.error(f"Error updating agent {agent_id}: {e}")
            raise ElevenLabsError(f"Failed to update agent {agent_id}: {e}") from e
