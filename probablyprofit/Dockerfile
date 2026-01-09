FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Copy requirements/setup files
# Note: We assume the user has poly16z installed as a package or requirements.txt
# Since we are in the repo, we copy the current dir.
COPY . /app

# Install the package
RUN pip install --no-cache-dir -e .
RUN pip install --no-cache-dir python-dotenv loguru openai google-generativeai py-clob-client anthropic

# Create necessary directories
RUN mkdir -p /app/data

# Entrypoint
# Users should mount their .env file: -v $(pwd)/.env:/app/.env
CMD ["python", "main.py"]
