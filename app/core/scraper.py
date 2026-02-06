"""Web scraping module using crawl4ai."""

import re
import time
from typing import Optional
from dataclasses import dataclass

from crawl4ai import AsyncWebCrawler

from app.core.logging import get_logger
from app.core.exceptions import ScraperError
from app.core.metrics import (
    SCRAPE_PAGES_TOTAL,
    SCRAPE_DURATION_SECONDS,
    SCRAPE_REQUESTS_TOTAL,
)

logger = get_logger("scraper")


@dataclass
class CrawlResult:
    """Result from crawling a single URL."""

    url: str
    markdown: str
    screenshot: Optional[str] = None
    success: bool = True
    error: Optional[str] = None


class Scraper:
    """Web scraper using crawl4ai with configurable options."""

    def __init__(
        self,
        max_depth: int = 1,
        max_pages: int = 5,
        url_pattern: Optional[str] = None,
        capture_screenshots: bool = True,
        timeout: float = 30.0,
        source_name: Optional[str] = None,
    ):
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.url_pattern = url_pattern
        self.capture_screenshots = capture_screenshots
        self.timeout = timeout
        self.source_name = source_name or "unknown"
        self._compiled_pattern = re.compile(url_pattern) if url_pattern else None

    def matches_pattern(self, url: str) -> bool:
        """Check if URL matches the configured pattern."""
        if not self._compiled_pattern:
            return True
        return bool(self._compiled_pattern.match(url))

    async def crawl_url(self, url: str) -> CrawlResult:
        """Crawl a single URL and return markdown content with optional screenshot."""
        logger.info(f"Crawling URL: {url}")
        start_time = time.time()

        async with AsyncWebCrawler() as crawler:
            try:
                result = await crawler.arun(
                    url=url,
                    screenshot=self.capture_screenshots,
                    page_timeout=int(self.timeout * 1000),
                )
                logger.info(f"Successfully crawled: {url}")

                # Record success metric
                SCRAPE_PAGES_TOTAL.labels(source_name=self.source_name, status="success").inc()

                return CrawlResult(
                    url=url,
                    markdown=result.markdown if result.markdown else "",
                    screenshot=result.screenshot if self.capture_screenshots else None,
                    success=True,
                )
            except Exception as e:
                logger.error(f"Failed to crawl {url}: {e}")

                # Record failure metric
                SCRAPE_PAGES_TOTAL.labels(source_name=self.source_name, status="error").inc()

                return CrawlResult(
                    url=url,
                    markdown="",
                    screenshot=None,
                    success=False,
                    error=str(e),
                )

    async def crawl_with_subpages(
        self,
        start_url: str,
        subpage_urls: list[str],
    ) -> list[CrawlResult]:
        """Crawl a start URL and its subpages, respecting max_pages limit."""
        start_time = time.time()
        results = []

        # Crawl the initial page
        initial_result = await self.crawl_url(start_url)
        results.append(initial_result)

        if not initial_result.success:
            # Record failed scrape request
            duration = time.time() - start_time
            SCRAPE_REQUESTS_TOTAL.labels(source_name=self.source_name, status="error").inc()
            SCRAPE_DURATION_SECONDS.labels(source_name=self.source_name).observe(duration)
            raise ScraperError(f"Failed to crawl initial page: {initial_result.error}")

        # Filter subpages by pattern and limit
        valid_subpages = [
            url for url in subpage_urls
            if url != start_url and self.matches_pattern(url)
        ]

        # Limit to max_pages - 1 (since we already have the initial page)
        subpages_to_crawl = valid_subpages[: self.max_pages - 1]
        logger.info(f"Crawling {len(subpages_to_crawl)} subpages (max: {self.max_pages - 1})")

        # Crawl subpages
        for url in subpages_to_crawl:
            result = await self.crawl_url(url)
            results.append(result)

        successful = sum(1 for r in results if r.success)
        logger.info(f"Crawl complete: {successful}/{len(results)} pages successful")

        # Record overall scrape metrics
        duration = time.time() - start_time
        status = "success" if successful == len(results) else "partial"
        SCRAPE_REQUESTS_TOTAL.labels(source_name=self.source_name, status=status).inc()
        SCRAPE_DURATION_SECONDS.labels(source_name=self.source_name).observe(duration)

        return results

    def combine_results(self, results: list[CrawlResult]) -> tuple[str, list[str]]:
        """Combine crawl results into a single markdown string and screenshot list."""
        combined_markdown = ""
        screenshots = []

        for result in results:
            if result.success and result.markdown:
                combined_markdown += f"## Source: {result.url}\n\n{result.markdown}\n\n"
                if result.screenshot:
                    screenshots.append(result.screenshot)

        return combined_markdown, screenshots
