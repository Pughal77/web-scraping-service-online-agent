from crawlee.crawlers import PlaywrightCrawlingContext
from crawlee.router import Router

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
            'content': (await context.page.content()),
        }
    )

    await context.enqueue_links()



