FROM python:3.13-slim

WORKDIR /app

# Install dependencies first so they cache independently of source changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code (run from /app so `src` resolves as a package).
COPY src ./src

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
