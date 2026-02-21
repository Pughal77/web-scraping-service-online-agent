FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV HOME=/home/appuser
# FIX: Use a dedicated directory for browsers
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

RUN useradd -m appuser && \
    mkdir -p /home/appuser/.crawl4ai/models /ms-playwright && \
    chown -R appuser:appuser /home/appuser /ms-playwright

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# This will now install binaries into /ms-playwright
RUN playwright install chromium --with-deps
RUN crawl4ai-setup

COPY main.py .
RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]