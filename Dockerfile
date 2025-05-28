FROM ghcr.io/prefix-dev/pixi:latest

WORKDIR /app

# Copy pixi files
COPY pixi.toml pixi.lock ./

# Install dependencies using pixi
RUN pixi install

# Copy application code
COPY server.py .
COPY redis/ ./redis/

# Expose the streaming API port
EXPOSE 8000

# Run the application using pixi
CMD ["pixi", "run", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]