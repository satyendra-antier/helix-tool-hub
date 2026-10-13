FROM python:3.12-slim

WORKDIR /app

COPY modules/growth-pillars/backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY modules/growth-pillars/backend/ ./backend/
WORKDIR /app/backend

EXPOSE 8005
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8005"]
