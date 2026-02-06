import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

# 1. Define the Lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize the crawler
    browser_config = BrowserConfig(headless=True, verbose=False)
    app.state.crawler = AsyncWebCrawler(config=browser_config)
    await app.state.crawler.start()
    
    yield  # The application runs while this is suspended
    
    # Shutdown: Clean up resources
    await app.state.crawler.close()

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