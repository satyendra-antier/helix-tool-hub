FROM python:3.12-slim

WORKDIR /app

COPY modules/market-depth-analyzer/backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY modules/market-depth-analyzer/backend/ ./backend/
WORKDIR /app/backend

EXPOSE 8002
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
