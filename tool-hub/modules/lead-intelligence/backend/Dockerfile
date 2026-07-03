FROM python:3.12-slim

WORKDIR /app

COPY modules/lead-intelligence/backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY modules/lead-intelligence/backend/ ./backend/
WORKDIR /app/backend

EXPOSE 8003
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003"]
