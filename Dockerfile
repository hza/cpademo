FROM node:18-alpine AS build
ARG VITE_API
ENV VITE_API=${VITE_API}
WORKDIR /app
COPY frontend/ .
RUN npm install --silent --no-audit --no-fund
RUN npm run build

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install Python dependencies
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy backend Python sources only
# copy the main server and the python package directory
RUN mkdir -p /app/backend
COPY backend/server.py /app/backend/server.py
COPY backend/src/ /app/backend/src/

# Copy frontend build output (if present) into backend webroot
# This allows the backend to serve the frontend static files from /webroot
COPY --from=build /app/dist/ /app/backend/webroot/

# Ensure uploads directory exists and is writable by the app
RUN mkdir -p /app/backend/uploads && chmod -R a+rwx /app/backend/uploads

WORKDIR /app/backend

EXPOSE 8080

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
