FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .

RUN useradd -m -u 10002 botuser && \
    mkdir -p /app/reports && \
    chown -R botuser:botuser /app

USER botuser

EXPOSE 5001

CMD ["uvicorn", "bot:app", "--host", "0.0.0.0", "--port", "5001"]
