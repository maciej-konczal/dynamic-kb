"""Tests for the Prometheus metrics module."""

import pytest

from app.core.metrics import (
    get_metrics,
    get_metrics_content_type,
    record_ai_retry,
    record_ai_tokens,
    record_elevenlabs_request,
    record_elevenlabs_retry,
    record_kb_document_created,
    record_kb_document_deleted,
    record_draft_created,
    record_draft_approved,
    record_draft_rejected,
    set_pending_drafts,
    record_health_check,
    AI_REQUESTS_TOTAL,
    AI_RETRIES_TOTAL,
    AI_TOKENS_TOTAL,
    ELEVENLABS_REQUESTS_TOTAL,
    ELEVENLABS_RETRIES_TOTAL,
    KB_DOCUMENTS_CREATED_TOTAL,
    KB_DOCUMENTS_DELETED_TOTAL,
    DRAFTS_CREATED_TOTAL,
    DRAFTS_APPROVED_TOTAL,
    DRAFTS_REJECTED_TOTAL,
    DRAFTS_PENDING,
    HEALTH_CHECK_STATUS,
)


class TestMetricsOutput:
    """Test metrics output generation."""

    def test_get_metrics_returns_bytes(self):
        """get_metrics should return bytes."""
        metrics = get_metrics()
        assert isinstance(metrics, bytes)

    def test_get_metrics_contains_app_info(self):
        """get_metrics should contain app info."""
        metrics = get_metrics().decode("utf-8")
        assert "dynamic_kb" in metrics

    def test_get_metrics_content_type(self):
        """get_metrics_content_type should return correct content type."""
        content_type = get_metrics_content_type()
        assert "text/plain" in content_type or "text/openmetrics" in content_type


class TestAIMetrics:
    """Test AI-related metrics recording."""

    def test_record_ai_retry(self):
        """record_ai_retry should increment retry counter."""
        initial = AI_RETRIES_TOTAL.labels(
            operation="test_op", model="test_model"
        )._value.get()

        record_ai_retry(operation="test_op", model="test_model")

        new_value = AI_RETRIES_TOTAL.labels(
            operation="test_op", model="test_model"
        )._value.get()
        assert new_value == initial + 1

    def test_record_ai_tokens_prompt(self):
        """record_ai_tokens should record prompt tokens."""
        initial = AI_TOKENS_TOTAL.labels(
            operation="test_op", model="test_model", token_type="prompt"
        )._value.get()

        record_ai_tokens(
            operation="test_op", model="test_model", prompt_tokens=100
        )

        new_value = AI_TOKENS_TOTAL.labels(
            operation="test_op", model="test_model", token_type="prompt"
        )._value.get()
        assert new_value == initial + 100

    def test_record_ai_tokens_completion(self):
        """record_ai_tokens should record completion tokens."""
        initial = AI_TOKENS_TOTAL.labels(
            operation="test_op", model="test_model", token_type="completion"
        )._value.get()

        record_ai_tokens(
            operation="test_op", model="test_model", completion_tokens=50
        )

        new_value = AI_TOKENS_TOTAL.labels(
            operation="test_op", model="test_model", token_type="completion"
        )._value.get()
        assert new_value == initial + 50


class TestElevenLabsMetrics:
    """Test ElevenLabs-related metrics recording."""

    def test_record_elevenlabs_request(self):
        """record_elevenlabs_request should record request metrics."""
        initial = ELEVENLABS_REQUESTS_TOTAL.labels(
            endpoint="test_endpoint", method="GET", status="success"
        )._value.get()

        record_elevenlabs_request(
            endpoint="test_endpoint",
            method="GET",
            status="success",
            duration=0.5,
        )

        new_value = ELEVENLABS_REQUESTS_TOTAL.labels(
            endpoint="test_endpoint", method="GET", status="success"
        )._value.get()
        assert new_value == initial + 1

    def test_record_elevenlabs_retry(self):
        """record_elevenlabs_retry should increment retry counter."""
        initial = ELEVENLABS_RETRIES_TOTAL.labels(
            endpoint="test_endpoint", method="POST"
        )._value.get()

        record_elevenlabs_retry(endpoint="test_endpoint", method="POST")

        new_value = ELEVENLABS_RETRIES_TOTAL.labels(
            endpoint="test_endpoint", method="POST"
        )._value.get()
        assert new_value == initial + 1


class TestKBMetrics:
    """Test knowledge base metrics recording."""

    def test_record_kb_document_created(self):
        """record_kb_document_created should increment created counter."""
        initial = KB_DOCUMENTS_CREATED_TOTAL.labels(
            source_name="test_source"
        )._value.get()

        record_kb_document_created(source_name="test_source", content_size=1000)

        new_value = KB_DOCUMENTS_CREATED_TOTAL.labels(
            source_name="test_source"
        )._value.get()
        assert new_value == initial + 1

    def test_record_kb_document_deleted(self):
        """record_kb_document_deleted should increment deleted counter."""
        initial = KB_DOCUMENTS_DELETED_TOTAL.labels(
            source_name="test_source"
        )._value.get()

        record_kb_document_deleted(source_name="test_source")

        new_value = KB_DOCUMENTS_DELETED_TOTAL.labels(
            source_name="test_source"
        )._value.get()
        assert new_value == initial + 1


class TestDraftMetrics:
    """Test draft-related metrics recording."""

    def test_record_draft_created(self):
        """record_draft_created should increment created counter."""
        initial = DRAFTS_CREATED_TOTAL.labels(
            source_name="test_source"
        )._value.get()

        record_draft_created(source_name="test_source")

        new_value = DRAFTS_CREATED_TOTAL.labels(
            source_name="test_source"
        )._value.get()
        assert new_value == initial + 1

    def test_record_draft_approved(self):
        """record_draft_approved should increment approved counter."""
        initial = DRAFTS_APPROVED_TOTAL.labels(
            source_name="test_source"
        )._value.get()

        record_draft_approved(source_name="test_source")

        new_value = DRAFTS_APPROVED_TOTAL.labels(
            source_name="test_source"
        )._value.get()
        assert new_value == initial + 1

    def test_record_draft_rejected(self):
        """record_draft_rejected should increment rejected counter."""
        initial = DRAFTS_REJECTED_TOTAL.labels(
            source_name="test_source"
        )._value.get()

        record_draft_rejected(source_name="test_source")

        new_value = DRAFTS_REJECTED_TOTAL.labels(
            source_name="test_source"
        )._value.get()
        assert new_value == initial + 1

    def test_set_pending_drafts(self):
        """set_pending_drafts should set the gauge value."""
        set_pending_drafts(source_name="test_source", count=5)

        value = DRAFTS_PENDING.labels(source_name="test_source")._value.get()
        assert value == 5

        # Update to new value
        set_pending_drafts(source_name="test_source", count=3)

        value = DRAFTS_PENDING.labels(source_name="test_source")._value.get()
        assert value == 3


class TestHealthCheckMetrics:
    """Test health check metrics recording."""

    def test_record_health_check_healthy(self):
        """record_health_check should set status to 1 when healthy."""
        record_health_check(component="test_component", healthy=True, duration=0.1)

        value = HEALTH_CHECK_STATUS.labels(component="test_component")._value.get()
        assert value == 1

    def test_record_health_check_unhealthy(self):
        """record_health_check should set status to 0 when unhealthy."""
        record_health_check(component="test_component_2", healthy=False, duration=0.5)

        value = HEALTH_CHECK_STATUS.labels(component="test_component_2")._value.get()
        assert value == 0
