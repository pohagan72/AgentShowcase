# 1. Use an official Python runtime as a parent image
FROM python:3.10-slim-bullseye

# 2. Set DEBIAN_FRONTEND to avoid interactive prompts during apt-get
ENV DEBIAN_FRONTEND=noninteractive

# 3. Set the working directory in the container
WORKDIR /app

# 4. Install OS dependencies needed by Playwright/Chromium
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libdbus-1-3 \
    libatspi2.0-0 libx11-6 libx11-xcb1 libxcb1 libxcomposite1 libxcursor1 libxdamage1 \
    libxext6 libxfixes3 libxi6 libxrandr2 libxtst6 libpango-1.0-0 libcairo2 libgbm1 \
    libasound2 libpangocairo-1.0-0 libxshmfence1 \
    fonts-liberation \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 5. Copy ONLY the requirements file first to leverage Docker caching
COPY ./requirements.txt /app/requirements.txt

# 6. Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 7. Download the Spacy model AFTER spacy is installed
RUN python -m spacy download en_core_web_lg

# 8. Install Playwright browser binary (Chromium) AFTER Playwright Python package is installed
RUN playwright install chromium --with-deps

# 9. Copy the rest of your application's code into the container
COPY . /app/

# 10. Make port available (Cloud Run uses $PORT, your run.py listens on it)
EXPOSE 8080

# 11. Define environment variable for the port (Cloud Run will set this)
ENV PORT 8080

# 12. Specify the command to run your application
CMD ["python", "run.py"]