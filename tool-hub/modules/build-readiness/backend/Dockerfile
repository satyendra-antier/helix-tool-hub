FROM python:3.12-slim
WORKDIR /app
COPY modules/build-readiness/backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY modules/build-readiness/backend/ ./backend/
WORKDIR /app/backend
EXPOSE 8004
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8004"]
