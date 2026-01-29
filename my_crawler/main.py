from crawlee.crawlers import PlaywrightCrawler
from crawlee.http_clients import HttpxHttpClient
from .routes import router

async def main(url: str) -> None:
    """The crawler entry point."""
    crawler = PlaywrightCrawler(
        request_handler=router,
        headless=True,
        max_requests_per_crawl=1,
        http_client=HttpxHttpClient(),
    )
    print("Starting crawler...")

    await crawler.run(
        [
            url,
        ]
    )
