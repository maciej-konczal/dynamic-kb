"""Observability module with Langfuse integration for LLM tracing."""

import os
import functools
from contextlib import contextmanager
from typing import Optional, Any, Callable
from datetime import datetime, timezone

from app.core.logging import get_logger

logger = get_logger("observability")

# Langfuse client singleton
_langfuse_client = None
_langfuse_enabled = False


def init_langfuse() -> bool:
    """Initialize Langfuse client from environment variables.

    Required env vars:
        LANGFUSE_PUBLIC_KEY: Langfuse public key
        LANGFUSE_SECRET_KEY: Langfuse secret key

    Optional env vars:
        LANGFUSE_HOST: Langfuse host URL (default: https://cloud.langfuse.com)
        LANGFUSE_ENABLED: Set to "false" to disable (default: true if keys present)

    Returns:
        True if Langfuse was initialized successfully, False otherwise.
    """
    global _langfuse_client, _langfuse_enabled

    # Check if explicitly disabled
    if os.getenv("LANGFUSE_ENABLED", "true").lower() == "false":
        logger.info("Langfuse disabled via LANGFUSE_ENABLED=false")
        _langfuse_enabled = False
        return False

    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")

    if not public_key or not secret_key:
        logger.info("Langfuse not configured (missing LANGFUSE_PUBLIC_KEY or LANGFUSE_SECRET_KEY)")
        _langfuse_enabled = False
        return False

    try:
        from langfuse import Langfuse

        host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
        _langfuse_client = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
        )
        _langfuse_enabled = True
        logger.info(f"Langfuse initialized (host: {host})")
        return True
    except Exception as e:
        logger.warning(f"Failed to initialize Langfuse: {e}")
        _langfuse_enabled = False
        return False


def get_langfuse():
    """Get the Langfuse client instance.

    Returns:
        Langfuse client or None if not initialized.
    """
    global _langfuse_client
    return _langfuse_client


def is_langfuse_enabled() -> bool:
    """Check if Langfuse is enabled and initialized."""
    return _langfuse_enabled


def flush_langfuse():
    """Flush any pending Langfuse events."""
    if _langfuse_client:
        try:
            _langfuse_client.flush()
        except Exception as e:
            logger.warning(f"Failed to flush Langfuse: {e}")


def shutdown_langfuse():
    """Shutdown Langfuse client gracefully."""
    global _langfuse_client, _langfuse_enabled
    if _langfuse_client:
        try:
            _langfuse_client.shutdown()
            logger.info("Langfuse shutdown complete")
        except Exception as e:
            logger.warning(f"Error during Langfuse shutdown: {e}")
        finally:
            _langfuse_client = None
            _langfuse_enabled = False


class LangfuseTrace:
    """Context manager for Langfuse tracing."""

    def __init__(
        self,
        name: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[dict] = None,
        tags: Optional[list[str]] = None,
    ):
        self.name = name
        self.user_id = user_id
        self.session_id = session_id
        self.metadata = metadata or {}
        self.tags = tags or []
        self.trace = None
        self.start_time = None

    def __enter__(self):
        self.start_time = datetime.now(timezone.utc)
        if _langfuse_enabled and _langfuse_client:
            try:
                self.trace = _langfuse_client.trace(
                    name=self.name,
                    user_id=self.user_id,
                    session_id=self.session_id,
                    metadata=self.metadata,
                    tags=self.tags,
                )
                logger.debug(f"Started Langfuse trace: {self.name}")
            except Exception as e:
                logger.warning(f"Failed to create Langfuse trace: {e}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.trace:
            try:
                if exc_type:
                    self.trace.update(
                        metadata={
                            **self.metadata,
                            "error": str(exc_val),
                            "error_type": exc_type.__name__,
                        }
                    )
            except Exception as e:
                logger.warning(f"Failed to update Langfuse trace: {e}")
        return False  # Don't suppress exceptions

    def span(
        self,
        name: str,
        input: Optional[Any] = None,
        metadata: Optional[dict] = None,
    ):
        """Create a span within this trace."""
        return LangfuseSpan(
            trace=self.trace,
            name=name,
            input=input,
            metadata=metadata,
        )

    def generation(
        self,
        name: str,
        model: str,
        input: Optional[Any] = None,
        metadata: Optional[dict] = None,
        model_parameters: Optional[dict] = None,
    ):
        """Create a generation (LLM call) within this trace."""
        return LangfuseGeneration(
            trace=self.trace,
            name=name,
            model=model,
            input=input,
            metadata=metadata,
            model_parameters=model_parameters,
        )


class LangfuseSpan:
    """Context manager for a span within a Langfuse trace."""

    def __init__(
        self,
        trace,
        name: str,
        input: Optional[Any] = None,
        metadata: Optional[dict] = None,
    ):
        self.trace = trace
        self.name = name
        self.input = input
        self.metadata = metadata or {}
        self.span = None
        self.start_time = None

    def __enter__(self):
        self.start_time = datetime.now(timezone.utc)
        if self.trace:
            try:
                self.span = self.trace.span(
                    name=self.name,
                    input=self.input,
                    metadata=self.metadata,
                )
            except Exception as e:
                logger.warning(f"Failed to create Langfuse span: {e}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.span:
            try:
                if exc_type:
                    self.span.end(
                        metadata={
                            **self.metadata,
                            "error": str(exc_val),
                            "error_type": exc_type.__name__,
                        }
                    )
                else:
                    self.span.end()
            except Exception as e:
                logger.warning(f"Failed to end Langfuse span: {e}")
        return False

    def set_output(self, output: Any):
        """Set the output of this span."""
        if self.span:
            try:
                self.span.update(output=output)
            except Exception as e:
                logger.warning(f"Failed to update span output: {e}")


class LangfuseGeneration:
    """Context manager for an LLM generation within a Langfuse trace."""

    def __init__(
        self,
        trace,
        name: str,
        model: str,
        input: Optional[Any] = None,
        metadata: Optional[dict] = None,
        model_parameters: Optional[dict] = None,
    ):
        self.trace = trace
        self.name = name
        self.model = model
        self.input = input
        self.metadata = metadata or {}
        self.model_parameters = model_parameters or {}
        self.generation = None
        self.start_time = None

    def __enter__(self):
        self.start_time = datetime.now(timezone.utc)
        if self.trace:
            try:
                self.generation = self.trace.generation(
                    name=self.name,
                    model=self.model,
                    input=self.input,
                    metadata=self.metadata,
                    model_parameters=self.model_parameters,
                )
            except Exception as e:
                logger.warning(f"Failed to create Langfuse generation: {e}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.generation:
            try:
                if exc_type:
                    self.generation.end(
                        metadata={
                            **self.metadata,
                            "error": str(exc_val),
                            "error_type": exc_type.__name__,
                        }
                    )
                else:
                    self.generation.end()
            except Exception as e:
                logger.warning(f"Failed to end Langfuse generation: {e}")
        return False

    def set_output(
        self,
        output: Any,
        usage: Optional[dict] = None,
    ):
        """Set the output and usage of this generation.

        Args:
            output: The model output/completion
            usage: Token usage dict with keys: prompt_tokens, completion_tokens, total_tokens
        """
        if self.generation:
            try:
                update_kwargs = {"output": output}
                if usage:
                    update_kwargs["usage"] = usage
                self.generation.update(**update_kwargs)
            except Exception as e:
                logger.warning(f"Failed to update generation output: {e}")


def trace_llm_call(
    name: str,
    model: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    tags: Optional[list[str]] = None,
):
    """Decorator to trace an LLM call with Langfuse.

    Usage:
        @trace_llm_call(name="extract_links", model="gemini-2.5-flash")
        async def extract_links(self, markdown: str, start_url: str) -> list[str]:
            ...
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            with LangfuseTrace(
                name=f"{name}_trace",
                user_id=user_id,
                session_id=session_id,
                tags=tags or ["llm"],
            ) as trace:
                with trace.generation(
                    name=name,
                    model=model,
                    input={"args": str(args[1:]), "kwargs": str(kwargs)},
                ) as gen:
                    result = await func(*args, **kwargs)
                    gen.set_output(result)
                    return result

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            with LangfuseTrace(
                name=f"{name}_trace",
                user_id=user_id,
                session_id=session_id,
                tags=tags or ["llm"],
            ) as trace:
                with trace.generation(
                    name=name,
                    model=model,
                    input={"args": str(args[1:]), "kwargs": str(kwargs)},
                ) as gen:
                    result = func(*args, **kwargs)
                    gen.set_output(result)
                    return result

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# Initialize Langfuse on module import
init_langfuse()
