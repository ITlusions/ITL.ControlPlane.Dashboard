FROM python:3.11-alpine AS builder

WORKDIR /build

# Install build dependencies
RUN apk add --no-cache \
    gcc \
    musl-dev

# Copy requirements and install to /build/venv
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --target ./python-packages -r requirements.txt

# ========== Runtime Stage ==========
FROM python:3.11-alpine

WORKDIR /app

# Install only runtime dependencies
RUN apk add --no-cache curl

# Copy installed packages from builder
COPY --from=builder /build/python-packages /usr/local/lib/python3.11/site-packages

# Copy application files
COPY main.py .
COPY src/ src/
COPY templates/ templates/
COPY static/ static/
COPY config/ config/

# Create data directory and aggressive cleanup
RUN mkdir -p data && chmod 777 data && \
    find /usr/local/lib/python3.11/site-packages -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true && \
    find /usr/local/lib/python3.11/site-packages -type f -name "*.pyc" -delete && \
    find /usr/local/lib/python3.11/site-packages -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true && \
    find /usr/local/lib/python3.11/site-packages -type d -name "*docs*" -exec rm -rf {} + 2>/dev/null || true && \
    find /usr/local/lib/python3.11/site-packages -type d -name "*example*" -exec rm -rf {} + 2>/dev/null || true && \
    find /usr/local/lib/python3.11/site-packages -type f -name "*.md" -delete 2>/dev/null || true

# Expose port
EXPOSE 8090

# Run the application
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8090"]
