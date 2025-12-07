# 1. Use Python 3.10 Slim (Good choice)
FROM python:3.10-slim-bullseye

# 2. Set env variables
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# 3. Workdir
WORKDIR /app

# 4. Install BASIC system tools only (build-essential is often needed for python libs)
# We removed the huge list of libs because Playwright installs them later.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 5. Copy requirements first (Layer Caching)
COPY ./requirements.txt /app/requirements.txt

# 6. Install Python dependencies
# Increased timeout helps with slow network speeds on large files
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --default-timeout=100 -r requirements.txt

# 7. Download Spacy Model
RUN python -m spacy download en_core_web_lg

# 8. Install Playwright + System Dependencies
# We use --with-deps so it installs the linux libraries (libnss3, etc) automatically
RUN playwright install chromium --with-deps

# 9. Copy application code
COPY . /app/

# 10. Expose port (Optional on Railway, but good practice)
EXPOSE 8080

# 11. Run
CMD ["python", "run.py"]