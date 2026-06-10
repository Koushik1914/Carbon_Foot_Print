# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /build

# Install compilation prerequisites
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install dependencies to a user-level directory
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Slim Runtime
FROM python:3.11-slim AS runner

WORKDIR /app

# Configure environmental PATH for user-installed pip packages
ENV PATH=/home/ecoquest/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# Create non-privileged system user
RUN useradd -u 10001 -m ecoquest
USER ecoquest

# Copy dependencies from builder
COPY --from=builder --chown=ecoquest:ecoquest /root/.local /home/ecoquest/.local

# Copy app code
COPY --chown=ecoquest:ecoquest app/ /app/app/

EXPOSE 8080

# Run FastAPI app with Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
