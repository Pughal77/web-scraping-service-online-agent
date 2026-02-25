import asyncio
import json
import logging
import aio_pika
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from redis import asyncio as aioredis

from config import QUEUE_IN, QUEUE_OUT, REDIS_URL, RMQ_URL
from utils import chunk_text

logger = logging.getLogger("uvicorn")

async def process_message(message: aio_pika.IncomingMessage, app: FastAPI, channel: aio_pika.Channel):
    async with message.process():
        try:
            logger.info(f"[*] Received message for background processing")
            data = json.loads(message.body)
            request_id = data['request_id']
            request_url = data['url']
            
            crawler = app.state.crawler
            gentle_filter = PruningContentFilter(threshold=0.2, min_word_threshold=10, threshold_type="fixed")
            md_generator = DefaultMarkdownGenerator(content_filter=gentle_filter)
            run_config = CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                wait_until="domcontentloaded", 
                page_timeout=30000,
                markdown_generator=md_generator
            )
            
            result = await asyncio.wait_for(crawler.arun(url=request_url, config=run_config), timeout=90.0)
            
            if not result.success:
                logger.error(f"Crawling failed for {request_id}: {result.error_message}")
                return

            markdown_text = result.markdown.fit_markdown
            chunks = await chunk_text(markdown_text)
            logger.info(f"Text split into {len(chunks)} chunks for request {request_id}.")
            
            await app.state.redis.incrby(request_id, len(chunks))
            
            for i, chunk in enumerate(chunks):
                data_out = {"request_id": request_id, "text": chunk}
                await channel.default_exchange.publish(
                    aio_pika.Message(body=json.dumps(data_out).encode()),
                    routing_key=QUEUE_OUT
                )
                logger.info(f"[x] Published chunk {i+1}/{len(chunks)} for {request_id}")
                
            await app.state.redis.decr(request_id)
            logger.info(f"[x] Finished background task: {request_id}")

        except asyncio.TimeoutError:
            logger.error(f"Timeout reached for URL: {request_url}")
        except Exception as e:
            logger.error(f"Unexpected error in process_message: {str(e)}")

async def run_consumer(app: FastAPI):
    logger.info("[*] Starting Web Scraper Service consumer...")
    channel = await app.state.rabbitmq_connection.channel()
    await channel.set_qos(prefetch_count=2)
    queue_in = await channel.declare_queue(QUEUE_IN)
    await channel.declare_queue(QUEUE_OUT)
    
    async with queue_in.iterator() as queue_iter:
        async for message in queue_iter:
            await process_message(message, app, channel)

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.rabbitmq_connection = await aio_pika.connect_robust(RMQ_URL)
    
    browser_config = BrowserConfig(
        browser_type="chromium",
        headless=True,
        verbose=True,
        extra_args=["--no-sandbox", "--disable-dev-shm-usage"] 
    )
    app.state.crawler = AsyncWebCrawler(config=browser_config)
    await app.state.crawler.start()
    app.state.redis = await aioredis.from_url(REDIS_URL, decode_responses=True)
    
    task = asyncio.create_task(run_consumer(app))
    yield 
    
    task.cancel()
    await app.state.crawler.close()
    await app.state.redis.close()
    await app.state.rabbitmq_connection.close()

app = FastAPI(title="Crawl4AI Modern Service", lifespan=lifespan)

class ScrapeRequest(BaseModel):
    url: str
    bypass_cache: bool = True

@app.get("/")
async def read_root():
    return {"status": "online"}

@app.post("/scrape")
async def scrape_url(request: ScrapeRequest):
    crawler = app.state.crawler
    run_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS if request.bypass_cache else CacheMode.ENABLED,
        delay_before_return_html=2.0, 
        page_timeout=30000 
    )
    try:
        result = await crawler.arun(url=request.url, config=run_config)
        if result.success:
            return {"url": result.url, "markdown": result.markdown, "status": "success"}
        raise HTTPException(status_code=400, detail=result.error_message)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="The crawler timed out rendering the page.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)