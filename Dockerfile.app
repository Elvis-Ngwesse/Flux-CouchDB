# Dockerfile.job
FROM python:3.11-slim

# Create non-root user and group
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy script directly into /app
COPY app/main.py .

# Set ownership and permissions
RUN chown -R appuser:appgroup /app

# Switch to non-root user
USER appuser

# Default command
CMD ["python", "main.py"]




FROM python:3.11-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["python", "app/main.py"]
