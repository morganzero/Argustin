# Use the specified base image
FROM ghcr.io/linuxserver/baseimage-alpine:3.20-d6fdb4e3-ls8

# Set the working directory
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install Python 3, venv, and OpenSSH client
RUN apk add --no-cache python3 py3-pip openssh redis && \
    python3 -m venv /app/venv && \
    /app/venv/bin/pip install --no-cache-dir -r /app/requirements.txt

# Ensure the virtual environment is used for all subsequent commands
ENV PATH="/app/venv/bin:$PATH"

# Expose Flask-SocketIO port and Redis port
EXPOSE 5000 6379

# Start Redis server and Flask app
CMD ["sh", "-c", "redis-server & python /app/Argus.py"]
