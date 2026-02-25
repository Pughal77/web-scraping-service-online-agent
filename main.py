import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
import logging
import aio_pika
import os
import json
import uvicorn
from redis import asyncio as aioredis

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")

# --- LOGIC CONFIG ---
QUEUE_IN = "url_queue"
QUEUE_OUT = "text_queue"

# Connection strings
redis_host = os.getenv("REDIS_HOST", "redis-state-store")
rmq_host = os.getenv("RABBITMQ_HOST", "rabbitmq-broker")
redis_url = f"redis://{redis_host}:6379"
rmq_url = f"amqp://admin:password123@{rmq_host}:5672/"

async def chunk_text(text: str, chunk_size: int = 500):
    """Splits text into chunks of roughly 500 characters (or tokens)."""
    # Simple split by sentences/newlines to keep context
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]

async def process_message(message: aio_pika.IncomingMessage, app: FastAPI, channel: aio_pika.Channel):
    '''
        Format of message coming from url_queue:
        {
            "request_id": "unique_request_id",
            "url": "https://example.com"
        }
        Format of message going to text_queue:
        {
            "request_id": "unique_request_id",
            "text": "markdown content of the page"
        }
    '''
    async with message.process():
        try:
            logger.info(f"[*] Received message for background processing")
            data = json.loads(message.body)
            request_id = data['request_id']
            request_url = data['url']
            crawler = app.state.crawler
            gentle_filter = PruningContentFilter(
                threshold=0.2,           # Lower = more content kept
                min_word_threshold=10,   # Keep smaller snippets of text
                threshold_type="fixed"   # "fixed" is more predictable than "dynamic"
            )
            md_generator = DefaultMarkdownGenerator(content_filter=gentle_filter)
            run_config = CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                # Change "networkidle" to "domcontentloaded"
                wait_until="domcontentloaded", 
                page_timeout=30000,  # Internal browser timeout (30s)
                markdown_generator=md_generator
            )
            # IMPROVEMENT 1: Added a timeout to prevent the worker from hanging forever
            result = await asyncio.wait_for(
                crawler.arun(url=request_url, config=run_config),
                timeout=90.0 
            )
            
            if not result.success:
                logger.error(f"Crawling failed for {request_id}: {result.error_message}")
                # return message.process() handles the ack/nack logic

            # Chunk the markdown content
            markdown_text = result.markdown.fit_markdown
            chunks = await chunk_text(markdown_text)
            logger.info(f"Text split into {len(chunks)} chunks for request {request_id}.")
            
            # Set Redis counter to number of chunks
            await app.state.redis.incrby(request_id, len(chunks))
            logger.info(f"[*] Set Redis counter for {request_id} to {len(chunks)}")
            
            # Publish each chunk as a separate message
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

    # IMPROVEMENT 2: Reduced prefetch_count from 10 to 2
    # This prevents 10 simultaneous JS renders from crashing the 1GB shared memory
    await channel.set_qos(prefetch_count=2)

    queue_in = await channel.declare_queue(QUEUE_IN)
    await channel.declare_queue(QUEUE_OUT)
    
    async with queue_in.iterator() as queue_iter:
        async for message in queue_iter:
            await process_message(message, app, channel)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize connections
    logger.info("[*] Connecting to Rabbitmq...")
    app.state.rabbitmq_connection = await aio_pika.connect_robust(rmq_url)

    # IMPROVEMENT 3: Initialize Crawler BEFORE starting the consumer task
    # This avoids a race condition where a message arrives before the browser is ready
    logger.info("[*] Starting the crawler...")
    browser_config = BrowserConfig(
        browser_type="chromium",
        headless=True,
        verbose=True, # Set to True to see browser-level errors in Docker logs
        extra_args=["--no-sandbox", "--disable-dev-shm-usage"] 
    )
    app.state.crawler = AsyncWebCrawler(config=browser_config)
    await app.state.crawler.start()
    
    # Startup: Connect to Redis
    logger.info("[*] Connecting to Redis...")
    app.state.redis = await aioredis.from_url(redis_url, decode_responses=True)
    
    # Start consumer only after crawler is ready
    task = asyncio.create_task(run_consumer(app))
    logger.info("[*] Web Scraper service is fully initialized...")
    
    yield 
    
    # Shutdown
    logger.info("[*] Shutting down...")
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
        page_timeout=30000  # Internal browser timeout (30s)
    )
    
    try:
        logger.info(f"Received scrape request")
        result = await crawler.arun(url=request.url, config=run_config)
        if result.success:
            return {"url": result.url, "markdown": result.markdown, "status": "success"}
        raise HTTPException(status_code=400, detail=result.error_message)
        
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="The crawler timed out rendering the page.")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)