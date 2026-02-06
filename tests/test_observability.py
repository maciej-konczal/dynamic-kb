"""Tests for the observability module."""

import os
from unittest.mock import MagicMock, patch

import pytest

from app.core.observability import (
    init_langfuse,
    is_langfuse_enabled,
    get_langfuse,
    LangfuseTrace,
    LangfuseSpan,
    LangfuseGeneration,
)


class TestInitLangfuse:
    """Test Langfuse initialization."""

    def test_disabled_when_env_var_false(self):
        """Langfuse should be disabled when LANGFUSE_ENABLED=false."""
        with patch.dict(os.environ, {"LANGFUSE_ENABLED": "false"}, clear=True):
            result = init_langfuse()
            assert result is False
            assert is_langfuse_enabled() is False

    def test_disabled_when_keys_missing(self):
        """Langfuse should be disabled when API keys are missing."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("LANGFUSE_PUBLIC_KEY", None)
            os.environ.pop("LANGFUSE_SECRET_KEY", None)
            result = init_langfuse()
            assert result is False

    def test_enabled_when_keys_present(self):
        """Langfuse should be enabled when API keys are present."""
        mock_langfuse = MagicMock()
        mock_langfuse_class = MagicMock(return_value=mock_langfuse)

        with patch.dict(
            os.environ,
            {
                "LANGFUSE_PUBLIC_KEY": "pk-test",
                "LANGFUSE_SECRET_KEY": "sk-test",
            },
        ):
            with patch.dict("sys.modules", {"langfuse": MagicMock(Langfuse=mock_langfuse_class)}):
                result = init_langfuse()
                assert result is True
                assert is_langfuse_enabled() is True
                assert get_langfuse() is mock_langfuse


class TestLangfuseTrace:
    """Test LangfuseTrace context manager."""

    def test_trace_without_langfuse(self):
        """Trace should work gracefully when Langfuse is disabled."""
        with patch("app.core.observability._langfuse_enabled", False):
            with LangfuseTrace(name="test_trace") as trace:
                assert trace.trace is None

    def test_trace_creates_langfuse_trace(self):
        """Trace should create Langfuse trace when enabled."""
        mock_client = MagicMock()
        mock_trace = MagicMock()
        mock_client.trace.return_value = mock_trace

        with patch("app.core.observability._langfuse_enabled", True):
            with patch("app.core.observability._langfuse_client", mock_client):
                with LangfuseTrace(
                    name="test_trace",
                    user_id="user123",
                    session_id="session456",
                    metadata={"key": "value"},
                    tags=["test"],
                ) as trace:
                    assert trace.trace is mock_trace
                    mock_client.trace.assert_called_once()

    def test_trace_handles_exception(self):
        """Trace should update metadata on exception."""
        mock_client = MagicMock()
        mock_trace = MagicMock()
        mock_client.trace.return_value = mock_trace

        with patch("app.core.observability._langfuse_enabled", True):
            with patch("app.core.observability._langfuse_client", mock_client):
                with pytest.raises(ValueError):
                    with LangfuseTrace(name="test_trace") as trace:
                        raise ValueError("Test error")

                # Should have called update with error info
                mock_trace.update.assert_called_once()
                call_kwargs = mock_trace.update.call_args.kwargs
                assert "error" in call_kwargs["metadata"]


class TestLangfuseSpan:
    """Test LangfuseSpan context manager."""

    def test_span_without_trace(self):
        """Span should work gracefully when trace is None."""
        with LangfuseSpan(trace=None, name="test_span") as span:
            assert span.span is None

    def test_span_creates_langfuse_span(self):
        """Span should create Langfuse span when trace exists."""
        mock_trace = MagicMock()
        mock_span = MagicMock()
        mock_trace.span.return_value = mock_span

        with LangfuseSpan(
            trace=mock_trace,
            name="test_span",
            input="test input",
            metadata={"key": "value"},
        ) as span:
            assert span.span is mock_span
            mock_trace.span.assert_called_once()

    def test_span_set_output(self):
        """Span should allow setting output."""
        mock_trace = MagicMock()
        mock_span = MagicMock()
        mock_trace.span.return_value = mock_span

        with LangfuseSpan(trace=mock_trace, name="test_span") as span:
            span.set_output("test output")
            mock_span.update.assert_called_with(output="test output")


class TestLangfuseGeneration:
    """Test LangfuseGeneration context manager."""

    def test_generation_without_trace(self):
        """Generation should work gracefully when trace is None."""
        with LangfuseGeneration(
            trace=None, name="test_gen", model="test-model"
        ) as gen:
            assert gen.generation is None

    def test_generation_creates_langfuse_generation(self):
        """Generation should create Langfuse generation when trace exists."""
        mock_trace = MagicMock()
        mock_generation = MagicMock()
        mock_trace.generation.return_value = mock_generation

        with LangfuseGeneration(
            trace=mock_trace,
            name="test_gen",
            model="gemini-2.5-flash",
            input="test prompt",
            metadata={"key": "value"},
        ) as gen:
            assert gen.generation is mock_generation
            mock_trace.generation.assert_called_once()

    def test_generation_set_output_with_usage(self):
        """Generation should allow setting output with usage."""
        mock_trace = MagicMock()
        mock_generation = MagicMock()
        mock_trace.generation.return_value = mock_generation

        with LangfuseGeneration(
            trace=mock_trace, name="test_gen", model="test-model"
        ) as gen:
            gen.set_output(
                "test completion",
                usage={"prompt_tokens": 10, "completion_tokens": 20},
            )
            mock_generation.update.assert_called_with(
                output="test completion",
                usage={"prompt_tokens": 10, "completion_tokens": 20},
            )

    def test_generation_set_output_without_usage(self):
        """Generation should allow setting output without usage."""
        mock_trace = MagicMock()
        mock_generation = MagicMock()
        mock_trace.generation.return_value = mock_generation

        with LangfuseGeneration(
            trace=mock_trace, name="test_gen", model="test-model"
        ) as gen:
            gen.set_output("test completion")
            mock_generation.update.assert_called_with(output="test completion")
