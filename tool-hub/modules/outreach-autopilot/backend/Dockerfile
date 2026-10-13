FROM python:3.12-slim

WORKDIR /app

COPY modules/outreach-autopilot/backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY modules/outreach-autopilot/backend/ ./backend/
WORKDIR /app/backend

EXPOSE 8006
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8006"]
