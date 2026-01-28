from crawlee.crawlers import PlaywrightCrawlingContext
from crawlee.router import Router
from .process_data import process_data

router = Router[PlaywrightCrawlingContext]()

# Define the default request handler, which will be called for every request.
@router.default_handler
async def default_handler(context: PlaywrightCrawlingContext) -> None:
    """Default request handler."""
    context.log.info(f'Processing {context.request.url} ...')
    title = await context.page.query_selector('title')
    await context.push_data(
        {
            'url': context.request.loaded_url,
            'title': await title.inner_text() if title else None,
            'content': (await process_data(await context.page.content())),
        }
    )
J
    await context.enqueue_links()





