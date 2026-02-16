import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
import logging
import uvicorn
from redis import asyncio as  aioredis
import aio_pika
import os
import json

logger = logging.getLogger("uvicorn")

# --- LOGIC CONFIG ---
QUEUE_IN = "url_queue" # recieved from search engine service
QUEUE_OUT = "text_queue" # going to embedding model

# Connection strings
redis_host = os.getenv("REDIS_HOST", "localhost")
rmq_host = os.getenv("RABBITMQ_HOST", "localhost")
redis_url = f"redis://{redis_host}:6379"
rmq_url = f"amqp://admin:password123@{rmq_host}:5672/"

async def process_message(message: aio_pika.IncomingMessage, app: FastAPI, channel: aio_pika.Channel):
    '''
        Format of message coming from url_queue:
        {
            "id": "unique_request_id",
            "url": "https://example.com"
        }

        Format of message going to text_queue:
        {
            "id": "unique_request_id",
            "text": "markdown content here"
        }

    '''
    async with message.process():
        logger.info(f"[*] Received message in Service 2")
        data = json.loads(message.body)
        request_id = data['id']
        request_url = data['url']
        
        # do actual web crawling here
        crawler = app.state.crawler
    
        run_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS # cache not enable by default
        )
        
        result = await crawler.arun(url=request_url, config=run_config)
        
        if not result.success:
            raise HTTPException(status_code=400, detail=result.error_message)
        
        data_out = {
            "id": request_id,
            "text": result.markdown
        }
        
        logger.info(f"[*] Going to write to text_queue: {request_id}")
        await channel.default_exchange.publish(
            aio_pika.Message(body=json.dumps(data_out).encode()),
            routing_key=QUEUE_OUT
        )
        
        logger.info(f"[x] Web scraper service finished: {request_id}")


async def run_consumer(app: FastAPI):
    logger.info("[*] Starting Web Scraper Service consumer...")

    # Set up RabbitMQ channel
    
    channel = await app.state.rabbitmq_connection.channel()

    await channel.set_qos(prefetch_count=10)

    # declare in-queue and out-queue
    queue_in = await channel.declare_queue(QUEUE_IN)
    await channel.declare_queue(QUEUE_OUT)
    
    async with queue_in.iterator() as queue_iter:
        async for message in queue_iter:
            await process_message(message, app, channel)


# 1. Define the Lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the RabbitMQ consumer as a background task
    task = asyncio.create_task(run_consumer(app))
    logger.info("[*] Web Scraper service is running...")
    # Startup: Initialize the crawler
    logger.info("[*] Starting the crawler...")
    browser_config = BrowserConfig(headless=True, verbose=False)
    app.state.crawler = AsyncWebCrawler(config=browser_config)
    await app.state.crawler.start()
    
    yield  # The application runs while this is suspended
    
    # Shutdown: Clean up resources
    await app.state.crawler.close()
    task.cancel()
    await app.state.redis.close()
    await app.state.rabbitmq_connection.close()

# 2. Initialize FastAPI with the lifespan handler
app = FastAPI(title="Crawl4AI Modern Service", lifespan=lifespan)

class ScrapeRequest(BaseModel):
    url: str
    bypass_cache: bool = True

@app.get("/")
async def read_root():
    return {"message": "Welcome to the Crawl4AI Web Scraping Service!"}

@app.post("/scrape")
async def scrape_url(request: ScrapeRequest):
    # This is a test endpoint not really used in the online agent project, but it demonstrates how to use the crawler directly from an API endpoint.

    # Access the crawler from the app state
    crawler = app.state.crawler
    
    run_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS if request.bypass_cache else CacheMode.ENABLED
    )
    
    result = await crawler.arun(url=request.url, config=run_config)
    
    if result.success:
        return {
            "url": result.url,
            "markdown": result.markdown,
            "status": "success"
        }
    else:
        raise HTTPException(status_code=400, detail=result.error_message)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)