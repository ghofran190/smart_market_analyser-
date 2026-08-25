"""
=================
Centralized management of all external API clients used in the project.

This module provides:
- LLM client via OpenRouter (DSPy + OpenAI compatible)
- Tavily search client
- Firecrawl web scraping client (optional)
"""

import os
import time
import threading
from typing import Optional, Protocol
from dataclasses import dataclass

# Third-party imports
import dspy
from tavily import TavilyClient
from openai import OpenAI

from config import TavilyConfig, FirecrawlConfig, OpenRouterConfig, DSPyConfig
from utils.logger import get_logger

logger = get_logger(__name__)

_dspy_configured = False
_dspy_lock = threading.Lock()


# ============================================================================
# LOGGING HELPERS
# ============================================================================

def _mask_secret(value: Optional[str], visible: int = 4) -> str:
    """
    Mask a secret value for safe logging (never log raw API keys).

    Example: "sk-or-v1-abcdef123456" -> "sk-o****3456"
    """
    if not value:
        return "<empty>"
    if len(value) <= visible * 2:
        return "*" * len(value)
    return f"{value[:visible]}{'*' * 4}{value[-visible:]}"


# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class ClientConfig:
    """
    Configuration class for all API clients.
    Loads from environment variables with sensible defaults.
    """

    OPENROUTER_API_KEY: str = OpenRouterConfig.api_key
    OPENROUTER_BASE_URL: str = OpenRouterConfig.base_url
    DEFAULT_MODEL: str = OpenRouterConfig.default_model
    DEFAULT_TEMPERATURE: float = OpenRouterConfig.default_temperature
    DEFAULT_MAX_TOKENS: int = OpenRouterConfig.default_max_tokens

    TAVILY_API_KEY: str = TavilyConfig.api_key
    TAVILY_SEARCH_DEPTH: str = TavilyConfig.search_depth
    TAVILY_MAX_RESULTS: int = TavilyConfig.max_results

    FIRECRAWL_API_KEY: str = FirecrawlConfig.api_key
    FIRECRAWL_TIMEOUT: int = FirecrawlConfig.timeout
    FIRECRAWL_MAX_PAGE: int = FirecrawlConfig.max_pages

    DSPY_MODEL: str = DSPyConfig.model

    @classmethod
    def validate(cls) -> None:
        """
        Validate that all required configuration values are present.
        Raises ValueError if any required key is missing.
        """
        required_checks = [
            ("OPENROUTER_API_KEY", cls.OPENROUTER_API_KEY),
            ("TAVILY_API_KEY", cls.TAVILY_API_KEY),
            ("FIRECRAWL_API_KEY", cls.FIRECRAWL_API_KEY),
            ("DSPY_MODEL", cls.DSPY_MODEL),
        ]

        missing = [name for name, value in required_checks if not value]
        if missing:
            # %s lazy formatting: no string built unless the log level is active
            logger.error(
                "Missing required environment variables: %s",
                ", ".join(missing),
                extra={"missing_vars": missing},
            )
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}\n"
                "Please set them in your .env file or environment."
            )

        logger.info(
            "All required API keys are present (openrouter=%s, tavily=%s, firecrawl=%s)",
            _mask_secret(cls.OPENROUTER_API_KEY),
            _mask_secret(cls.TAVILY_API_KEY),
            _mask_secret(cls.FIRECRAWL_API_KEY),
        )


# ============================================================================
# LLM CLIENT INTERFACE
# ============================================================================

class LLMClient(Protocol):
    """Protocol defining the minimal interface required for LLM clients."""

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> str:
        ...


# ============================================================================
# OPENROUTER LLM IMPLEMENTATION
# ============================================================================

class OpenRouterLLMClient:
    """Implementation of LLMClient using OpenRouter API (OpenAI-compatible)."""

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.model = model or ClientConfig.DEFAULT_MODEL
        api_key = api_key or ClientConfig.OPENROUTER_API_KEY
        base_url = base_url or ClientConfig.OPENROUTER_BASE_URL

        if not api_key:
            logger.error("OpenRouter API key is missing (OPENROUTER_API_KEY not set)")
            raise ValueError(
                "OpenRouter API key required. Set OPENROUTER_API_KEY environment "
                "variable or pass api_key explicitly."
            )

        logger.debug(
            "Initializing OpenRouter client (model=%s, base_url=%s, api_key=%s)",
            self.model, base_url, _mask_secret(api_key),
        )

        start = time.perf_counter()
        try:
            self._client = OpenAI(api_key=api_key, base_url=base_url)
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "OpenRouter client initialized (model=%s) in %.1fms",
                self.model, elapsed_ms,
            )
        except Exception:
            # logger.exception automatically captures the stack trace (exc_info=True)
            logger.exception("Failed to initialize OpenRouter client (model=%s)", self.model)
            raise

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = ClientConfig.DEFAULT_TEMPERATURE,
        max_tokens: int = ClientConfig.DEFAULT_MAX_TOKENS,
    ) -> str:
        logger.debug(
            "LLM generate() call (model=%s, temperature=%.2f, max_tokens=%d, "
            "system_prompt_len=%d, user_prompt_len=%d)",
            self.model, temperature, max_tokens, len(system_prompt), len(user_prompt),
        )

        start = time.perf_counter()
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )

            content = (response.choices[0].message.content or "").strip()
            elapsed_ms = (time.perf_counter() - start) * 1000

            usage = getattr(response, "usage", None)
            logger.info(
                "LLM generation succeeded (model=%s, elapsed=%.1fms, "
                "prompt_tokens=%s, completion_tokens=%s, output_len=%d)",
                self.model,
                elapsed_ms,
                getattr(usage, "prompt_tokens", "n/a"),
                getattr(usage, "completion_tokens", "n/a"),
                len(content),
            )
            return content

        except Exception:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.exception(
                "LLM generation failed (model=%s, elapsed=%.1fms)",
                self.model, elapsed_ms,
            )
            raise RuntimeError(f"LLM generation failed for model {self.model}") from None


# ============================================================================
# DSPY INTEGRATION
# ============================================================================

def setup_dspy(
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    temperature: float = ClientConfig.DEFAULT_TEMPERATURE,
    max_tokens: int = ClientConfig.DEFAULT_MAX_TOKENS,
) -> dspy.LM:
    """Setup DSPy with OpenRouter LLM client."""
    global _dspy_configured

    api_key = api_key or ClientConfig.OPENROUTER_API_KEY
    model = model or ClientConfig.DSPY_MODEL

    if not api_key:
        logger.error("OpenRouter API key is missing for DSPy setup")
        raise ValueError(
            "OpenRouter API key required. Set OPENROUTER_API_KEY environment "
            "variable or pass api_key explicitly."
        )

    try:
        lm = dspy.LM(
            model=f"openrouter/{model}",
            api_key=api_key,
            api_base=ClientConfig.OPENROUTER_BASE_URL,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        logger.debug("dspy.LM instance created (model=openrouter/%s)", model)

        with _dspy_lock:
            if not _dspy_configured:
                try:
                    dspy.configure(lm=lm)
                    _dspy_configured = True
                    logger.info("DSPy configured with model '%s' via OpenRouter", model)
                except RuntimeError as exc:
                    if "thread that initially configured it" in str(exc):
                        logger.warning(
                            "DSPy already configured in another thread (thread=%s); "
                            "skipping dspy.configure() and returning LM instance.",
                            threading.current_thread().name,
                        )
                        _dspy_configured = True
                    else:
                        logger.exception("Unexpected RuntimeError while configuring DSPy")
                        raise
            else:
                logger.debug("DSPy already configured; skipping dspy.configure()")

        return lm

    except Exception:
        logger.exception("DSPy configuration failed (model=%s)", model)
        raise RuntimeError(f"DSPy configuration failed for model {model}") from None


# ============================================================================
# TAVILY CLIENT
# ============================================================================

def setup_tavily_client(
    api_key: Optional[str] = None,
    search_depth: Optional[str] = None,
) -> TavilyClient:
    """Configure and return a Tavily client instance."""

    api_key = api_key or ClientConfig.TAVILY_API_KEY
    search_depth = search_depth or ClientConfig.TAVILY_SEARCH_DEPTH

    if not api_key:
        logger.error("Tavily API key is missing (TAVILY_API_KEY not set)")
        raise ValueError(
            "Tavily API key required. Set TAVILY_API_KEY environment "
            "variable or pass api_key explicitly."
        )

    start = time.perf_counter()
    try:
        client = TavilyClient(api_key=api_key)
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "Tavily client initialized (search_depth=%s, max_results=%d) in %.1fms",
            search_depth, ClientConfig.TAVILY_MAX_RESULTS, elapsed_ms,
        )
        return client

    except Exception:
        logger.exception("Tavily client initialization failed")
        raise RuntimeError("Tavily client initialization failed") from None


# ============================================================================
# FIRECRAWL CLIENT (OPTIONAL)
# ============================================================================

def setup_firecrawl_client(api_key: Optional[str] = None):
    """
    Configure and return a Firecrawl client instance.
    Optional: returns None if not configured/installed rather than raising,
    since Firecrawl is a non-critical dependency.
    """

    api_key = api_key or ClientConfig.FIRECRAWL_API_KEY

    if not api_key:
        logger.warning("Firecrawl API key not found (FIRECRAWL_API_KEY unset); client disabled")
        return None

    try:
        from firecrawl import FirecrawlApp

        client = FirecrawlApp(api_key=api_key)
        logger.info(
            "Firecrawl client initialized (timeout=%ds, max_pages=%d)",
            ClientConfig.FIRECRAWL_TIMEOUT, ClientConfig.FIRECRAWL_MAX_PAGE,
        )
        return client

    except ImportError:
        logger.warning(
            "Firecrawl package not installed; client disabled. "
            "Install with: pip install firecrawl-py"
        )
        return None
    except Exception:
        # Non-fatal by design: log full trace but don't crash the app.
        logger.exception("Firecrawl client initialization failed; continuing without it")
        return None


# ============================================================================
# AGGREGATE CLIENT CONTAINER
# ============================================================================

class APIClients:
    """Initializes and holds all external API clients."""

    def __init__(self):
        logger.info("Initializing API clients bundle...")
        start = time.perf_counter()
        try:
            self.tavily_client = setup_tavily_client()
            self.firecrawl_client = setup_firecrawl_client()
            self.dspy_client = setup_dspy()
            self.lm_client = OpenRouterLLMClient()

            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "All API clients initialized successfully in %.1fms "
                "(tavily=ok, firecrawl=%s, dspy=ok, openrouter=ok)",
                elapsed_ms,
                "ok" if self.firecrawl_client else "disabled",
            )

        except Exception:
            logger.exception("Failed to initialize API clients bundle")
            raise