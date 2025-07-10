FROM python:3.11-slim

# Create non-root user and group
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your main script
COPY app/main.py .

# Set ownership and permissions
RUN chown -R appuser:appgroup /app

# Switch to non-root user
USER appuser

# Expose Flask health endpoint
EXPOSE 8050

# Default command to run your app with Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8050", "main:server", "--log-level=info", "--capture-output"]
