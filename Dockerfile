# start by pulling a newer python image based on Debian slim
FROM python:3.12-slim-bullseye

# --- ADDED: Set DEBIAN_FRONTEND to avoid prompts during apt-get ---
ENV DEBIAN_FRONTEND=noninteractive

# --- ADDED: Install OS dependencies needed by Playwright/Chromium ---
# Update apt cache, install libraries, and clean up apt cache
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    # List essential libraries often needed by Chromium on Debian:
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libdbus-1-3 \
    libatspi2.0-0 libx11-6 libx11-xcb1 libxcb1 libxcomposite1 libxcursor1 libxdamage1 \
    libxext6 libxfixes3 libxi6 libxrandr2 libxtst6 libpango-1.0-0 libcairo2 libgbm1 \
    libasound2 libpangocairo-1.0-0 libxshmfence1 \
    # Add fonts - crucial for rendering pages correctly
    fonts-liberation \
    # Add ca-certificates for secure connections
    ca-certificates \
    # Clean up apt cache to reduce image size
    && rm -rf /var/lib/apt/lists/*

# Remove or comment out the Alpine-specific apk add line (already commented out)
# RUN apk add --no-cache build-base python3-dev

# copy the requirements file into the image
COPY ./requirements.txt /app/requirements.txt

# switch working directory
WORKDIR /app

# install the dependencies and packages in the requirements file
# This step installs the playwright python package itself
RUN pip install --no-cache-dir -r requirements.txt

# --- ADDED: Install Playwright browser binary (Chromium) using RUN ---
# Moved after pip install and uses --with-deps
RUN playwright install chromium --with-deps

# copy every content from the local file to the image
COPY . /app

# configure the container to run in an executed manner
ENTRYPOINT [ "python" ]

# Run the application
CMD ["run.py" ]