"""Tests for the AIProcessor class."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.ai_processor import AIProcessor
from app.core.exceptions import AIProcessorError


class TestAIProcessorInit:
    """Test AIProcessor initialization."""

    def test_default_values(self):
        """AIProcessor should have sensible defaults."""
        with patch("app.core.ai_processor.genai.Client"):
            processor = AIProcessor(api_key="test-key")

        assert processor.model == "gemini-2.5-flash"
        assert processor.timeout == 60.0
        assert processor.max_retries == 3

    def test_custom_timeout(self):
        """AIProcessor should accept custom timeout."""
        with patch("app.core.ai_processor.genai.Client"):
            processor = AIProcessor(api_key="test-key", timeout=120.0)

        assert processor.timeout == 120.0

    def test_custom_max_retries(self):
        """AIProcessor should accept custom max_retries."""
        with patch("app.core.ai_processor.genai.Client"):
            processor = AIProcessor(api_key="test-key", max_retries=5)

        assert processor.max_retries == 5

    def test_custom_prompts(self):
        """AIProcessor should accept custom prompts."""
        custom_link_prompt = "Extract links: {start_url} {content}"
        custom_clean_prompt = "Clean this: {start_url} {content}"

        with patch("app.core.ai_processor.genai.Client"):
            processor = AIProcessor(
                api_key="test-key",
                link_extraction_prompt=custom_link_prompt,
                content_cleaning_prompt=custom_clean_prompt,
            )

        assert processor.link_extraction_prompt == custom_link_prompt
        assert processor.content_cleaning_prompt == custom_clean_prompt


class TestIsRetryableError:
    """Test error classification for retry logic."""

    @pytest.fixture
    def processor(self):
        """Create a processor instance for testing."""
        with patch("app.core.ai_processor.genai.Client"):
            return AIProcessor(api_key="test-key")

    def test_network_error_is_retryable(self, processor):
        """Network errors should be retryable."""
        error = Exception("Connection reset by peer")
        assert processor._is_retryable_error(error) is True

    def test_timeout_error_is_retryable(self, processor):
        """Timeout errors should be retryable."""
        error = Exception("Request timeout")
        assert processor._is_retryable_error(error) is True

    def test_quota_error_not_retryable(self, processor):
        """Quota errors should not be retryable."""
        error = Exception("Quota exceeded")
        assert processor._is_retryable_error(error) is False

    def test_auth_error_not_retryable(self, processor):
        """Authentication errors should not be retryable."""
        error = Exception("Invalid API key - authentication failed")
        assert processor._is_retryable_error(error) is False

    def test_401_error_not_retryable(self, processor):
        """401 errors should not be retryable."""
        error = Exception("HTTP 401 Unauthorized")
        assert processor._is_retryable_error(error) is False

    def test_403_error_not_retryable(self, processor):
        """403 errors should not be retryable."""
        error = Exception("HTTP 403 Forbidden")
        assert processor._is_retryable_error(error) is False

    def test_500_error_is_retryable(self, processor):
        """500 server errors should be retryable."""
        error = Exception("HTTP 500 Internal Server Error")
        assert processor._is_retryable_error(error) is True


class TestCallWithRetry:
    """Test the retry mechanism."""

    @pytest.fixture
    def processor(self):
        """Create a processor instance for testing."""
        with patch("app.core.ai_processor.genai.Client"):
            return AIProcessor(api_key="test-key", timeout=1.0, max_retries=3)

    @pytest.mark.asyncio
    async def test_success_on_first_try(self, processor):
        """Should succeed without retrying if first call succeeds."""
        def mock_func():
            return "success"

        result = await processor._call_with_retry(mock_func, "test_operation")
        assert result == "success"

    @pytest.mark.asyncio
    async def test_retries_on_failure(self, processor):
        """Should retry on transient failures."""
        call_count = 0

        def mock_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Temporary network error")
            return "success after retries"

        # Mock sleep and metrics to speed up test
        with patch("asyncio.sleep", new=AsyncMock()):
            with patch("app.core.ai_processor.record_ai_retry"):
                result = await processor._call_with_retry(mock_func, "test_operation")

        assert result == "success after retries"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self, processor):
        """Should raise AIProcessorError after max retries exceeded."""
        def mock_func():
            raise Exception("Persistent error")

        with patch("asyncio.sleep", new=AsyncMock()):
            with patch("app.core.ai_processor.record_ai_retry"):
                with pytest.raises(AIProcessorError, match="failed after 3 attempts"):
                    await processor._call_with_retry(mock_func, "test_operation")

    @pytest.mark.asyncio
    async def test_no_retry_on_auth_error(self, processor):
        """Should not retry on authentication errors."""
        call_count = 0

        def mock_func():
            nonlocal call_count
            call_count += 1
            raise Exception("Invalid API key - authentication error")

        with pytest.raises(AIProcessorError, match="AI processing failed"):
            await processor._call_with_retry(mock_func, "test_operation")

        # Should only be called once (no retries)
        assert call_count == 1


def _create_mock_response(text: str = "test response"):
    """Helper to create a properly mocked Gemini response."""
    mock_response = MagicMock()
    mock_response.text = text
    # Mock usage_metadata to avoid issues with metrics
    mock_response.usage_metadata = None
    return mock_response


class TestExtractLinks:
    """Test link extraction functionality."""

    @pytest.mark.asyncio
    async def test_extracts_links_from_response(self):
        """Should extract valid URLs from AI response."""
        mock_response = _create_mock_response("""
        Here are the sub-pages:
        https://example.com/page1
        https://example.com/page2
        https://other.com/page (should be filtered)
        """)

        mock_client = MagicMock()
        mock_client.models.generate_content = MagicMock(return_value=mock_response)

        with patch("app.core.ai_processor.genai.Client", return_value=mock_client):
            with patch("app.core.ai_processor.flush_langfuse"):
                processor = AIProcessor(api_key="test-key")
                links = await processor.extract_links(
                    markdown="# Test content",
                    start_url="https://example.com",
                )

        assert "https://example.com/page1" in links
        assert "https://example.com/page2" in links
        assert "https://other.com/page" not in links

    @pytest.mark.asyncio
    async def test_deduplicates_links(self):
        """Should return unique links only."""
        mock_response = _create_mock_response("""
        https://example.com/page1
        https://example.com/page1
        https://example.com/page2
        """)

        mock_client = MagicMock()
        mock_client.models.generate_content = MagicMock(return_value=mock_response)

        with patch("app.core.ai_processor.genai.Client", return_value=mock_client):
            with patch("app.core.ai_processor.flush_langfuse"):
                processor = AIProcessor(api_key="test-key")
                links = await processor.extract_links(
                    markdown="# Test",
                    start_url="https://example.com",
                )

        # Should have 2 unique links
        assert len(links) == 2

    @pytest.mark.asyncio
    async def test_excludes_start_url(self):
        """Should exclude the start URL from extracted links."""
        mock_response = _create_mock_response("""
        https://example.com
        https://example.com/page1
        """)

        mock_client = MagicMock()
        mock_client.models.generate_content = MagicMock(return_value=mock_response)

        with patch("app.core.ai_processor.genai.Client", return_value=mock_client):
            with patch("app.core.ai_processor.flush_langfuse"):
                processor = AIProcessor(api_key="test-key")
                links = await processor.extract_links(
                    markdown="# Test",
                    start_url="https://example.com",
                )

        assert "https://example.com" not in links
        assert "https://example.com/page1" in links


class TestCleanContent:
    """Test content cleaning functionality."""

    @pytest.mark.asyncio
    async def test_returns_cleaned_content(self):
        """Should return cleaned content from AI."""
        mock_response = _create_mock_response("# Cleaned Content\n\nThis is the cleaned version.")

        mock_client = MagicMock()
        mock_client.models.generate_content = MagicMock(return_value=mock_response)

        with patch("app.core.ai_processor.genai.Client", return_value=mock_client):
            with patch("app.core.ai_processor.flush_langfuse"):
                processor = AIProcessor(api_key="test-key")
                result = await processor.clean_content(
                    content="# Messy content with nav etc",
                    start_url="https://example.com",
                )

        assert result == "# Cleaned Content\n\nThis is the cleaned version."

    @pytest.mark.asyncio
    async def test_handles_empty_response(self):
        """Should handle empty AI response."""
        mock_response = _create_mock_response(None)
        mock_response.text = None

        mock_client = MagicMock()
        mock_client.models.generate_content = MagicMock(return_value=mock_response)

        with patch("app.core.ai_processor.genai.Client", return_value=mock_client):
            with patch("app.core.ai_processor.flush_langfuse"):
                processor = AIProcessor(api_key="test-key")
                result = await processor.clean_content(
                    content="# Content",
                    start_url="https://example.com",
                )

        assert result == "Failed to clean content."

    @pytest.mark.asyncio
    async def test_raises_ai_processor_error_on_failure(self):
        """Should raise AIProcessorError on API failure."""
        mock_client = MagicMock()
        mock_client.models.generate_content = MagicMock(
            side_effect=Exception("API Error")
        )

        with patch("app.core.ai_processor.genai.Client", return_value=mock_client):
            with patch("asyncio.sleep", new=AsyncMock()):
                with patch("app.core.ai_processor.record_ai_retry"):
                    processor = AIProcessor(api_key="test-key", max_retries=1)
                    with pytest.raises(AIProcessorError):
                        await processor.clean_content(
                            content="# Content",
                            start_url="https://example.com",
                        )
