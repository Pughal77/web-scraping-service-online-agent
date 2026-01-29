from my_crawler import crawl_page

import fastapi
import uvicorn

app = fastapi.FastAPI()

@app.get("/")
def read_root():
    return {"message": "Hello from your uv-managed FastAPI app!"}

@app.post("/crawl")
async def crawl(url: str):
    await crawl_page(url)
    return {"status": "Crawling started"}

if __name__ == "__main__":
    uvicorn.run(app, host="localhost", port=8004)