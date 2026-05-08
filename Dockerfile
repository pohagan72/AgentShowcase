FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY ./requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir --upgrade \
        "pip>=24.0" "setuptools>=78.1.1" "wheel>=0.46.2" && \
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