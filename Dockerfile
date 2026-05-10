FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ ./backend/
COPY prime-os.html .

EXPOSE 7474

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "7474"]
