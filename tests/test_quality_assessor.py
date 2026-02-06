"""Tests for the QualityAssessor class."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.quality_assessor import QualityAssessor, QualityResult
from app.core.exceptions import AIProcessorError


class TestQualityResult:
    """Test QualityResult dataclass."""

    def test_default_values(self):
        """QualityResult should have sensible defaults."""
        result = QualityResult(score=75)
        assert result.score == 75
        assert result.issues == []
        assert result.recommendation == "review"
        assert result.details == {}

    def test_to_json(self):
        """QualityResult should serialize to JSON correctly."""
        result = QualityResult(
            score=85,
            issues=["Minor formatting issue"],
            recommendation="approve",
            details={"scores": {"completeness": 18}},
        )
        json_str = result.to_json()
        data = json.loads(json_str)

        assert data["score"] == 85
        assert data["issues"] == ["Minor formatting issue"]
        assert data["recommendation"] == "approve"
        assert data["details"]["scores"]["completeness"] == 18

    def test_from_json(self):
        """QualityResult should deserialize from JSON correctly."""
        json_str = json.dumps({
            "score": 90,
            "issues": ["Test issue"],
            "recommendation": "approve",
            "details": {"test": True},
        })
        result = QualityResult.from_json(json_str)

        assert result.score == 90
        assert result.issues == ["Test issue"]
        assert result.recommendation == "approve"
        assert result.details == {"test": True}

    def test_from_json_with_defaults(self):
        """QualityResult.from_json should handle missing fields."""
        json_str = json.dumps({"score": 50})
        result = QualityResult.from_json(json_str)

        assert result.score == 50
        assert result.issues == []
        assert result.recommendation == "review"
        assert result.details == {}


class TestQualityAssessorInit:
    """Test QualityAssessor initialization."""

    def test_default_values(self):
        """QualityAssessor should have sensible defaults."""
        with patch("app.core.quality_assessor.genai.Client"):
            assessor = QualityAssessor(api_key="test-key")

        assert assessor.model == "gemini-2.5-flash"
        assert assessor.timeout == 60.0
        assert assessor.max_retries == 3

    def test_custom_values(self):
        """QualityAssessor should accept custom values."""
        with patch("app.core.quality_assessor.genai.Client"):
            assessor = QualityAssessor(
                api_key="test-key",
                model="gemini-1.5-pro",
                timeout=120.0,
                max_retries=5,
            )

        assert assessor.model == "gemini-1.5-pro"
        assert assessor.timeout == 120.0
        assert assessor.max_retries == 5


class TestIsRetryableError:
    """Test error classification for retry logic."""

    @pytest.fixture
    def assessor(self):
        """Create an assessor instance for testing."""
        with patch("app.core.quality_assessor.genai.Client"):
            return QualityAssessor(api_key="test-key")

    def test_network_error_is_retryable(self, assessor):
        """Network errors should be retryable."""
        error = Exception("Connection reset by peer")
        assert assessor._is_retryable_error(error) is True

    def test_quota_error_not_retryable(self, assessor):
        """Quota errors should not be retryable."""
        error = Exception("Quota exceeded")
        assert assessor._is_retryable_error(error) is False

    def test_auth_error_not_retryable(self, assessor):
        """Authentication errors should not be retryable."""
        error = Exception("authentication failed - invalid_api_key")
        assert assessor._is_retryable_error(error) is False


class TestParseQualityResponse:
    """Test response parsing logic."""

    @pytest.fixture
    def assessor(self):
        """Create an assessor instance for testing."""
        with patch("app.core.quality_assessor.genai.Client"):
            return QualityAssessor(api_key="test-key")

    def test_parses_valid_json(self, assessor):
        """Should parse valid JSON response correctly."""
        response = json.dumps({
            "scores": {
                "completeness": 18,
                "formatting": 16,
                "information_density": 17,
                "coherence": 19,
                "relevance": 15,
            },
            "total_score": 85,
            "issues": ["Minor formatting issue"],
            "recommendation": "approve",
        })

        result = assessor._parse_quality_response(response)

        assert result.score == 85
        assert result.issues == ["Minor formatting issue"]
        assert result.recommendation == "approve"
        assert "scores" in result.details

    def test_handles_markdown_code_block(self, assessor):
        """Should strip markdown code block formatting."""
        response = """```json
{
    "scores": {
        "completeness": 16,
        "formatting": 16,
        "information_density": 16,
        "coherence": 16,
        "relevance": 16
    },
    "total_score": 80,
    "issues": [],
    "recommendation": "approve"
}
```"""

        result = assessor._parse_quality_response(response)

        assert result.score == 80
        assert result.recommendation == "approve"

    def test_calculates_total_from_scores(self, assessor):
        """Should calculate total if provided total is inconsistent."""
        response = json.dumps({
            "scores": {
                "completeness": 20,
                "formatting": 20,
                "information_density": 20,
                "coherence": 20,
                "relevance": 20,
            },
            "total_score": 50,  # Incorrect total
            "issues": [],
            "recommendation": "approve",
        })

        result = assessor._parse_quality_response(response)

        # Should use calculated total (100) not the incorrect one (50)
        assert result.score == 100

    def test_clamps_score_to_valid_range(self, assessor):
        """Should clamp score to 0-100 range."""
        response = json.dumps({
            "scores": {},
            "total_score": 150,
            "issues": [],
            "recommendation": "approve",
        })

        result = assessor._parse_quality_response(response)

        assert result.score == 100

    def test_validates_recommendation(self, assessor):
        """Should default to 'review' for invalid recommendations."""
        response = json.dumps({
            "scores": {},
            "total_score": 50,
            "issues": [],
            "recommendation": "invalid_value",
        })

        result = assessor._parse_quality_response(response)

        assert result.recommendation == "review"

    def test_handles_invalid_json(self, assessor):
        """Should return default result for invalid JSON."""
        response = "This is not JSON"

        result = assessor._parse_quality_response(response)

        assert result.score == 50
        assert "Failed to parse" in result.issues[0]
        assert result.recommendation == "review"


def _create_mock_response(text: str = "test response"):
    """Helper to create a properly mocked Gemini response."""
    mock_response = MagicMock()
    mock_response.text = text
    mock_response.usage_metadata = None
    return mock_response


class TestAssessQuality:
    """Test quality assessment functionality."""

    @pytest.mark.asyncio
    async def test_returns_quality_result(self):
        """Should return a QualityResult from AI assessment."""
        mock_response = _create_mock_response(json.dumps({
            "scores": {
                "completeness": 18,
                "formatting": 17,
                "information_density": 16,
                "coherence": 19,
                "relevance": 15,
            },
            "total_score": 85,
            "issues": [],
            "recommendation": "approve",
        }))

        mock_client = MagicMock()
        mock_client.models.generate_content = MagicMock(return_value=mock_response)

        with patch("app.core.quality_assessor.genai.Client", return_value=mock_client):
            with patch("app.core.quality_assessor.flush_langfuse"):
                assessor = QualityAssessor(api_key="test-key")
                result = await assessor.assess_quality(
                    content="# Test Content\n\nThis is high quality content.",
                    source_url="https://example.com",
                )

        assert isinstance(result, QualityResult)
        assert result.score == 85
        assert result.recommendation == "approve"

    @pytest.mark.asyncio
    async def test_handles_low_quality_content(self):
        """Should correctly identify low quality content."""
        mock_response = _create_mock_response(json.dumps({
            "scores": {
                "completeness": 5,
                "formatting": 3,
                "information_density": 2,
                "coherence": 8,
                "relevance": 2,
            },
            "total_score": 20,
            "issues": [
                "Content is mostly boilerplate",
                "Missing substantive information",
                "Poor formatting",
            ],
            "recommendation": "reject",
        }))

        mock_client = MagicMock()
        mock_client.models.generate_content = MagicMock(return_value=mock_response)

        with patch("app.core.quality_assessor.genai.Client", return_value=mock_client):
            with patch("app.core.quality_assessor.flush_langfuse"):
                assessor = QualityAssessor(api_key="test-key")
                result = await assessor.assess_quality(
                    content="Just some navigation text",
                    source_url="https://example.com",
                )

        assert result.score == 20
        assert result.recommendation == "reject"
        assert len(result.issues) == 3

    @pytest.mark.asyncio
    async def test_raises_ai_processor_error_on_failure(self):
        """Should raise AIProcessorError on API failure."""
        mock_client = MagicMock()
        mock_client.models.generate_content = MagicMock(
            side_effect=Exception("API Error")
        )

        with patch("app.core.quality_assessor.genai.Client", return_value=mock_client):
            with patch("asyncio.sleep", new=AsyncMock()):
                with patch("app.core.quality_assessor.record_ai_retry"):
                    assessor = QualityAssessor(api_key="test-key", max_retries=1)
                    with pytest.raises(AIProcessorError):
                        await assessor.assess_quality(
                            content="# Content",
                            source_url="https://example.com",
                        )

    @pytest.mark.asyncio
    async def test_truncates_long_content(self):
        """Should truncate very long content for assessment."""
        long_content = "A" * 100000  # 100k chars

        mock_response = _create_mock_response(json.dumps({
            "scores": {},
            "total_score": 50,
            "issues": [],
            "recommendation": "review",
        }))

        mock_client = MagicMock()
        mock_client.models.generate_content = MagicMock(return_value=mock_response)

        with patch("app.core.quality_assessor.genai.Client", return_value=mock_client):
            with patch("app.core.quality_assessor.flush_langfuse"):
                assessor = QualityAssessor(api_key="test-key")
                result = await assessor.assess_quality(
                    content=long_content,
                    source_url="https://example.com",
                )

        # Should succeed without error
        assert isinstance(result, QualityResult)

        # Verify the content was truncated in the prompt
        call_args = mock_client.models.generate_content.call_args
        prompt = call_args[1]["contents"]
        # Content should be truncated to ~50k
        assert len(prompt) < 60000


class TestCallWithRetry:
    """Test the retry mechanism."""

    @pytest.fixture
    def assessor(self):
        """Create an assessor instance for testing."""
        with patch("app.core.quality_assessor.genai.Client"):
            return QualityAssessor(api_key="test-key", timeout=1.0, max_retries=3)

    @pytest.mark.asyncio
    async def test_success_on_first_try(self, assessor):
        """Should succeed without retrying if first call succeeds."""
        def mock_func():
            return "success"

        result = await assessor._call_with_retry(mock_func, "test_operation")
        assert result == "success"

    @pytest.mark.asyncio
    async def test_retries_on_failure(self, assessor):
        """Should retry on transient failures."""
        call_count = 0

        def mock_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Temporary network error")
            return "success after retries"

        with patch("asyncio.sleep", new=AsyncMock()):
            with patch("app.core.quality_assessor.record_ai_retry"):
                result = await assessor._call_with_retry(mock_func, "test_operation")

        assert result == "success after retries"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self, assessor):
        """Should raise AIProcessorError after max retries exceeded."""
        def mock_func():
            raise Exception("Persistent error")

        with patch("asyncio.sleep", new=AsyncMock()):
            with patch("app.core.quality_assessor.record_ai_retry"):
                with pytest.raises(AIProcessorError, match="failed after 3 attempts"):
                    await assessor._call_with_retry(mock_func, "test_operation")

    @pytest.mark.asyncio
    async def test_no_retry_on_auth_error(self, assessor):
        """Should not retry on authentication errors."""
        call_count = 0

        def mock_func():
            nonlocal call_count
            call_count += 1
            raise Exception("Invalid API key - authentication error")

        with pytest.raises(AIProcessorError, match="Quality assessment failed"):
            await assessor._call_with_retry(mock_func, "test_operation")

        assert call_count == 1
