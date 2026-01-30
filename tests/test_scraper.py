"""Tests for the Scraper class."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.scraper import Scraper, CrawlResult
from app.core.exceptions import ScraperError


class TestScraperInit:
    """Test Scraper initialization."""

    def test_default_values(self):
        """Scraper should have sensible defaults."""
        scraper = Scraper()
        assert scraper.max_depth == 1
        assert scraper.max_pages == 5
        assert scraper.url_pattern is None
        assert scraper.capture_screenshots is True
        assert scraper.timeout == 30.0

    def test_custom_timeout(self):
        """Scraper should accept custom timeout."""
        scraper = Scraper(timeout=60.0)
        assert scraper.timeout == 60.0

    def test_custom_max_pages(self):
        """Scraper should accept custom max_pages."""
        scraper = Scraper(max_pages=10)
        assert scraper.max_pages == 10

    def test_url_pattern_compiled(self):
        """URL pattern should be compiled to regex."""
        scraper = Scraper(url_pattern=r"https://example\.com/.*")
        assert scraper._compiled_pattern is not None


class TestMatchesPattern:
    """Test URL pattern matching."""

    def test_no_pattern_matches_all(self):
        """Without pattern, all URLs should match."""
        scraper = Scraper()
        assert scraper.matches_pattern("https://any-url.com/page")
        assert scraper.matches_pattern("https://another.org/path")

    def test_pattern_filters_urls(self):
        """Pattern should filter non-matching URLs."""
        scraper = Scraper(url_pattern=r"https://example\.com/docs/.*")
        assert scraper.matches_pattern("https://example.com/docs/page1")
        assert not scraper.matches_pattern("https://example.com/blog/post")
        assert not scraper.matches_pattern("https://other.com/docs/page")


class TestCrawlUrl:
    """Test single URL crawling."""

    @pytest.mark.asyncio
    async def test_successful_crawl(self):
        """Successful crawl should return CrawlResult with content."""
        mock_result = MagicMock()
        mock_result.markdown = "# Page Content"
        mock_result.screenshot = "base64screenshot"

        mock_crawler = AsyncMock()
        mock_crawler.arun = AsyncMock(return_value=mock_result)
        mock_crawler.__aenter__ = AsyncMock(return_value=mock_crawler)
        mock_crawler.__aexit__ = AsyncMock(return_value=None)

        with patch("app.core.scraper.AsyncWebCrawler", return_value=mock_crawler):
            scraper = Scraper(timeout=30.0)
            result = await scraper.crawl_url("https://example.com")

        assert result.success is True
        assert result.markdown == "# Page Content"
        assert result.url == "https://example.com"

    @pytest.mark.asyncio
    async def test_crawl_with_timeout_parameter(self):
        """Crawl should pass timeout to crawler."""
        mock_result = MagicMock()
        mock_result.markdown = "Content"
        mock_result.screenshot = None

        mock_crawler = AsyncMock()
        mock_crawler.arun = AsyncMock(return_value=mock_result)
        mock_crawler.__aenter__ = AsyncMock(return_value=mock_crawler)
        mock_crawler.__aexit__ = AsyncMock(return_value=None)

        with patch("app.core.scraper.AsyncWebCrawler", return_value=mock_crawler):
            scraper = Scraper(timeout=45.0, capture_screenshots=False)
            await scraper.crawl_url("https://example.com")

        # Verify timeout was passed as page_timeout in milliseconds
        call_kwargs = mock_crawler.arun.call_args.kwargs
        assert call_kwargs.get("page_timeout") == 45000

    @pytest.mark.asyncio
    async def test_failed_crawl_returns_error_result(self):
        """Failed crawl should return CrawlResult with error."""
        mock_crawler = AsyncMock()
        mock_crawler.arun = AsyncMock(side_effect=Exception("Network error"))
        mock_crawler.__aenter__ = AsyncMock(return_value=mock_crawler)
        mock_crawler.__aexit__ = AsyncMock(return_value=None)

        with patch("app.core.scraper.AsyncWebCrawler", return_value=mock_crawler):
            scraper = Scraper()
            result = await scraper.crawl_url("https://example.com")

        assert result.success is False
        assert result.error == "Network error"
        assert result.markdown == ""


class TestCrawlWithSubpages:
    """Test crawling with subpages."""

    @pytest.mark.asyncio
    async def test_raises_scraper_error_on_initial_failure(self):
        """Should raise ScraperError if initial page fails."""
        mock_crawler = AsyncMock()
        mock_crawler.arun = AsyncMock(side_effect=Exception("Failed"))
        mock_crawler.__aenter__ = AsyncMock(return_value=mock_crawler)
        mock_crawler.__aexit__ = AsyncMock(return_value=None)

        with patch("app.core.scraper.AsyncWebCrawler", return_value=mock_crawler):
            scraper = Scraper()
            with pytest.raises(ScraperError, match="Failed to crawl initial page"):
                await scraper.crawl_with_subpages(
                    "https://example.com",
                    ["https://example.com/page1"],
                )

    @pytest.mark.asyncio
    async def test_respects_max_pages_limit(self):
        """Should only crawl up to max_pages."""
        call_count = 0

        async def mock_arun(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_result = MagicMock()
            mock_result.markdown = f"Content {call_count}"
            mock_result.screenshot = None
            return mock_result

        mock_crawler = AsyncMock()
        mock_crawler.arun = mock_arun
        mock_crawler.__aenter__ = AsyncMock(return_value=mock_crawler)
        mock_crawler.__aexit__ = AsyncMock(return_value=None)

        with patch("app.core.scraper.AsyncWebCrawler", return_value=mock_crawler):
            scraper = Scraper(max_pages=3)
            subpages = [
                "https://example.com/page1",
                "https://example.com/page2",
                "https://example.com/page3",
                "https://example.com/page4",
                "https://example.com/page5",
            ]
            results = await scraper.crawl_with_subpages(
                "https://example.com",
                subpages,
            )

        # max_pages=3 means 1 initial + 2 subpages
        assert len(results) == 3
        assert call_count == 3


class TestCombineResults:
    """Test combining crawl results."""

    def test_combines_successful_results(self):
        """Should combine markdown from successful results."""
        scraper = Scraper()
        results = [
            CrawlResult(url="https://a.com", markdown="# Page A", success=True),
            CrawlResult(url="https://b.com", markdown="# Page B", success=True),
        ]

        combined, screenshots = scraper.combine_results(results)

        assert "## Source: https://a.com" in combined
        assert "# Page A" in combined
        assert "## Source: https://b.com" in combined
        assert "# Page B" in combined

    def test_skips_failed_results(self):
        """Should skip failed results when combining."""
        scraper = Scraper()
        results = [
            CrawlResult(url="https://a.com", markdown="# Page A", success=True),
            CrawlResult(
                url="https://b.com", markdown="", success=False, error="Failed"
            ),
        ]

        combined, screenshots = scraper.combine_results(results)

        assert "# Page A" in combined
        assert "https://b.com" not in combined

    def test_collects_screenshots(self):
        """Should collect screenshots from results."""
        scraper = Scraper()
        results = [
            CrawlResult(
                url="https://a.com",
                markdown="A",
                screenshot="screenshot_a",
                success=True,
            ),
            CrawlResult(
                url="https://b.com",
                markdown="B",
                screenshot="screenshot_b",
                success=True,
            ),
        ]

        combined, screenshots = scraper.combine_results(results)

        assert screenshots == ["screenshot_a", "screenshot_b"]
