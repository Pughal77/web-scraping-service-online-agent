This is fastapi server that starts an crawl4ai crawling instance and keeps it running for as long as the fastapi server is running

the /crawl endpoint takes in a json body with the key 'url' whose value is the url that you would like to crawl
a JSON response containing the scraped webpage in a LLM-friendly markdown format is returned

Create virtual environment, activate it (different commands for windows and linux),
Download dependencies
```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

run application, locally hosted on port 8004, `localhost:8004`
```
python main.py
```

test `/crawl` endpoint by scraping `https://github.com/codecrafters-io/build-your-own-x`
```
curl -X POST "http://localhost:8004/scrape" -H "Content-type: application/json" -d '{"url": "https://github.com/codecrafters-io/build-your-own-x"}'
```