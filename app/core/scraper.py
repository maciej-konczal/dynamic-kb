"""Web scraping module using crawl4ai."""

import re
from typing import Optional
from dataclasses import dataclass

from crawl4ai import AsyncWebCrawler


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
    ):
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.url_pattern = url_pattern
        self.capture_screenshots = capture_screenshots
        self._compiled_pattern = re.compile(url_pattern) if url_pattern else None

    def matches_pattern(self, url: str) -> bool:
        """Check if URL matches the configured pattern."""
        if not self._compiled_pattern:
            return True
        return bool(self._compiled_pattern.match(url))

    async def crawl_url(self, url: str) -> CrawlResult:
        """Crawl a single URL and return markdown content with optional screenshot."""
        async with AsyncWebCrawler() as crawler:
            try:
                result = await crawler.arun(
                    url=url,
                    screenshot=self.capture_screenshots,
                )
                return CrawlResult(
                    url=url,
                    markdown=result.markdown if result.markdown else "",
                    screenshot=result.screenshot if self.capture_screenshots else None,
                    success=True,
                )
            except Exception as e:
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
        results = []

        # Crawl the initial page
        initial_result = await self.crawl_url(start_url)
        results.append(initial_result)

        # Filter subpages by pattern and limit
        valid_subpages = [
            url for url in subpage_urls
            if url != start_url and self.matches_pattern(url)
        ]

        # Limit to max_pages - 1 (since we already have the initial page)
        subpages_to_crawl = valid_subpages[: self.max_pages - 1]

        # Crawl subpages
        for url in subpages_to_crawl:
            result = await self.crawl_url(url)
            results.append(result)

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
