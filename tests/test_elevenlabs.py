"""Tests for the ElevenLabsClient class."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.core.elevenlabs import ElevenLabsClient, KBDocument
from app.core.exceptions import ElevenLabsError


class TestElevenLabsClientInit:
    """Test ElevenLabsClient initialization."""

    def test_default_values(self):
        """Client should have sensible defaults."""
        client = ElevenLabsClient(api_key="test-key")
        assert client.timeout == 60.0
        assert client.max_retries == 3
        assert client.base_url == "https://api.elevenlabs.io/v1/convai"

    def test_custom_timeout(self):
        """Client should accept custom timeout."""
        client = ElevenLabsClient(api_key="test-key", timeout=120.0)
        assert client.timeout == 120.0

    def test_custom_max_retries(self):
        """Client should accept custom max_retries."""
        client = ElevenLabsClient(api_key="test-key", max_retries=5)
        assert client.max_retries == 5

    def test_headers_include_api_key(self):
        """Headers should include the API key."""
        client = ElevenLabsClient(api_key="my-secret-key")
        assert client.headers["xi-api-key"] == "my-secret-key"
        assert client.headers["Content-Type"] == "application/json"


class TestRequest:
    """Test the internal _request method."""

    @pytest.mark.asyncio
    async def test_successful_request(self):
        """Successful request should return JSON response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"id": "doc123"}'
        mock_response.json.return_value = {"id": "doc123"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            client = ElevenLabsClient(api_key="test-key")
            result = await client._request("GET", "knowledge-base")

        assert result == {"id": "doc123"}

    @pytest.mark.asyncio
    async def test_empty_response_returns_success(self):
        """Empty response should return success status."""
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_response.content = b""
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            client = ElevenLabsClient(api_key="test-key")
            result = await client._request("DELETE", "knowledge-base/doc123")

        assert result == {"status": "success"}

    @pytest.mark.asyncio
    async def test_retries_on_server_error(self):
        """Should retry on 5xx server errors."""
        call_count = 0

        async def mock_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                response = MagicMock()
                response.status_code = 500
                response.text = "Internal Server Error"
                error = httpx.HTTPStatusError(
                    "Server Error",
                    request=MagicMock(),
                    response=response,
                )
                error.response = response
                raise error
            response = MagicMock()
            response.content = b'{"status": "ok"}'
            response.json.return_value = {"status": "ok"}
            response.raise_for_status = MagicMock()
            return response

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.request = mock_request
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            client = ElevenLabsClient(api_key="test-key")
            result = await client._request("GET", "test")

        assert result == {"status": "ok"}
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_no_retry_on_client_error(self):
        """Should not retry on 4xx client errors."""
        call_count = 0

        async def mock_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            response = MagicMock()
            response.status_code = 401
            response.text = "Unauthorized"
            error = httpx.HTTPStatusError(
                "Unauthorized",
                request=MagicMock(),
                response=response,
            )
            error.response = response
            raise error

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.request = mock_request
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            client = ElevenLabsClient(api_key="test-key")
            with pytest.raises(ElevenLabsError, match="401"):
                await client._request("GET", "test")

        # Should only be called once (no retries)
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_raises_elevenlabs_error_after_max_retries(self):
        """Should raise ElevenLabsError after exhausting retries."""
        async def mock_request(*args, **kwargs):
            raise httpx.RequestError("Connection failed")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.request = mock_request
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            client = ElevenLabsClient(api_key="test-key", max_retries=2)
            with pytest.raises(ElevenLabsError, match="request failed"):
                await client._request("GET", "test")


class TestCreateKBText:
    """Test knowledge base text creation."""

    @pytest.mark.asyncio
    async def test_creates_kb_document(self):
        """Should create KB document and return ID."""
        client = ElevenLabsClient(api_key="test-key")
        client._request = AsyncMock(return_value={"id": "new-doc-id"})

        doc_id = await client.create_kb_text("Test Doc", "Document content")

        assert doc_id == "new-doc-id"
        client._request.assert_called_once_with(
            method="POST",
            endpoint="knowledge-base/text",
            json={"text": "Document content", "name": "Test Doc"},
        )


class TestTriggerRagIndex:
    """Test RAG indexing trigger."""

    @pytest.mark.asyncio
    async def test_triggers_rag_index(self):
        """Should trigger RAG indexing for document."""
        client = ElevenLabsClient(api_key="test-key")
        client._request = AsyncMock(return_value={"status": "indexing"})

        result = await client.trigger_rag_index("doc123")

        assert result == {"status": "indexing"}
        client._request.assert_called_once_with(
            method="POST",
            endpoint="knowledge-base/doc123/rag-index",
            json={"model": "e5_mistral_7b_instruct"},
        )


class TestListAgents:
    """Test agent listing (used for API validation)."""

    @pytest.mark.asyncio
    async def test_lists_agents(self):
        """Should list agents."""
        client = ElevenLabsClient(api_key="test-key")
        client._request = AsyncMock(
            return_value={"agents": [{"id": "agent1"}, {"id": "agent2"}]}
        )

        agents = await client.list_agents()

        assert len(agents) == 2
        assert agents[0]["id"] == "agent1"


class TestUpdateAgentKB:
    """Test agent knowledge base updates."""

    @pytest.mark.asyncio
    async def test_updates_agent_with_new_document(self):
        """Should add new document to agent KB."""
        client = ElevenLabsClient(api_key="test-key")
        client.get_agent = AsyncMock(
            return_value={
                "conversation_config": {
                    "knowledge_base": [
                        {"id": "old-doc", "name": "prefix_old", "type": "text"}
                    ]
                }
            }
        )
        client.patch_agent = AsyncMock(return_value={})

        new_doc = KBDocument(id="new-doc-id", name="prefix_new")
        removed, success = await client.update_agent_kb(
            agent_id="agent123",
            new_doc=new_doc,
            kb_prefix="prefix_",
            remove_old=True,
        )

        assert success is True
        assert "old-doc" in removed
        client.patch_agent.assert_called_once()

    @pytest.mark.asyncio
    async def test_keeps_old_documents_when_remove_old_false(self):
        """Should keep old documents when remove_old is False."""
        client = ElevenLabsClient(api_key="test-key")
        client.get_agent = AsyncMock(
            return_value={
                "conversation_config": {
                    "knowledge_base": [
                        {"id": "old-doc", "name": "prefix_old", "type": "text"}
                    ]
                }
            }
        )
        client.patch_agent = AsyncMock(return_value={})

        new_doc = KBDocument(id="new-doc-id", name="prefix_new")
        removed, success = await client.update_agent_kb(
            agent_id="agent123",
            new_doc=new_doc,
            kb_prefix="prefix_",
            remove_old=False,
        )

        assert success is True
        assert removed == []

    @pytest.mark.asyncio
    async def test_raises_elevenlabs_error_on_failure(self):
        """Should raise ElevenLabsError on update failure."""
        client = ElevenLabsClient(api_key="test-key")
        client.get_agent = AsyncMock(side_effect=Exception("API Error"))

        new_doc = KBDocument(id="new-doc", name="test")
        with pytest.raises(ElevenLabsError, match="Failed to update agent"):
            await client.update_agent_kb(
                agent_id="agent123",
                new_doc=new_doc,
                kb_prefix="test_",
            )


class TestKBDocument:
    """Test KBDocument dataclass."""

    def test_default_values(self):
        """KBDocument should have sensible defaults."""
        doc = KBDocument(id="doc123", name="Test Doc")
        assert doc.type == "text"
        assert doc.usage_mode == "auto"

    def test_custom_values(self):
        """KBDocument should accept custom values."""
        doc = KBDocument(
            id="doc123",
            name="Test Doc",
            type="file",
            usage_mode="manual",
        )
        assert doc.type == "file"
        assert doc.usage_mode == "manual"
