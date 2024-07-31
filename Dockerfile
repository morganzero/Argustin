# Stage 1: Build React app
FROM node:18-alpine as build

WORKDIR /app

# Copy package.json and install dependencies
COPY frontend/package.json frontend/package-lock.json ./
RUN npm install

# Copy the rest of the application and build it
COPY frontend/ ./
RUN npm run build

# Stage 2: Build the final image
FROM ghcr.io/linuxserver/baseimage-alpine:3.20-d6fdb4e3-ls8

# Install Python, OpenSSH, Nginx, and Redis
RUN apk add --no-cache python3 py3-pip openssh redis nginx && \
    python3 -m venv /app/venv && \
    /app/venv/bin/pip install --no-cache-dir -r /app/requirements.txt

# Set up working directory
WORKDIR /app

# Copy the Flask application
COPY backend/ ./

# Copy the React build from the previous stage
COPY --from=build /app/build /usr/share/nginx/html

# Copy the Nginx configuration
COPY nginx/nginx.conf /etc/nginx/nginx.conf

# Ensure the virtual environment is used for all subsequent commands
ENV PATH="/app/venv/bin:$PATH"

# Expose Flask-SocketIO port, Redis port, and Nginx port
EXPOSE 5000 6379 80

# Start Redis, Nginx, and Flask
CMD ["sh", "-c", "redis-server & nginx && python /app/Argus.py"]
