from .main import main
URL = 'https://crawlee.dev'

async def crawl_page(url: str) -> None:
    await main(url)