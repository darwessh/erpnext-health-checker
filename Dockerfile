FROM python:3.12-slim

# Non-root user for security
RUN useradd --create-home appuser
WORKDIR /home/appuser/app

# Install dependencies first (layer-cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Drop privileges
USER appuser

EXPOSE 5000

# Use gunicorn in production; workers=2 is safe for a single-core container
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "app:app"]
