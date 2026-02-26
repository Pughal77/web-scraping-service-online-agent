# Use a slim Python base to slash size immediately
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install minimal system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
# Ensure requirements.txt uses 'crawl4ai' and not 'crawl4ai[all]' to avoid heavy ML models
RUN pip install --no-cache-dir -r requirements.txt

# Manually download only the small NLTK data required for chunking
RUN python -m nltk.downloader punkt_tab averaged_perceptron_tagger_eng

COPY . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]