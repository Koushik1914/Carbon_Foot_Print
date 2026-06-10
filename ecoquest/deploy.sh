#!/bin/bash
set -euo pipefail

# Change to the script's directory so relative paths work correctly
cd "$(dirname "$0")"

# 1. Validation of inputs
if [ -z "${PROJECT_ID:-}" ]; then
  echo "ERROR: PROJECT_ID environment variable is missing." >&2
  echo "Usage: PROJECT_ID=my-gcp-project REGION=us-central1 ./deploy.sh" >&2
  exit 1
fi

if [ -z "${REGION:-}" ]; then
  echo "ERROR: REGION environment variable is missing." >&2
  echo "Usage: PROJECT_ID=my-gcp-project REGION=us-central1 ./deploy.sh" >&2
  exit 1
fi

echo "=========================================="
echo " Starting Deploy: EcoQuest Platform"
echo " Project ID : ${PROJECT_ID}"
echo " Region     : ${REGION}"
echo "=========================================="

# 2. Enable GCP APIs
echo "Enabling required Google Cloud APIs..."
gcloud services enable \
  run.googleapis.com \
  firestore.googleapis.com \
  aiplatform.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  --project="${PROJECT_ID}"

# 3. Create Firestore DB in Native mode (idempotent)
echo "Checking Firestore Database status..."
if gcloud firestore databases describe --project="${PROJECT_ID}" --database="(default)" >/dev/null 2>&1; then
  echo "Firestore database '(default)' already exists. Skipping creation."
else
  echo "Firestore database '(default)' not found. Initializing..."
  # Map region to generic multi-region if standard regional Firestore isn't supported, 
  # but gcloud firestore databases create handles location.
  gcloud firestore databases create \
    --project="${PROJECT_ID}" \
    --location="${REGION}" \
    --type=firestore-native \
    --database="(default)" || echo "Firestore creation skipped or failed. It may have been created simultaneously."
fi

# 4. Create Artifact Registry repository (idempotent)
REPO_NAME="ecoquest-repo"
echo "Checking Artifact Registry repository '${REPO_NAME}'..."
if gcloud artifacts repositories describe "${REPO_NAME}" --location="${REGION}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "Artifact Registry repository '${REPO_NAME}' already exists. Skipping creation."
else
  echo "Creating Artifact Registry repository '${REPO_NAME}'..."
  gcloud artifacts repositories create "${REPO_NAME}" \
    --repository-format=docker \
    --location="${REGION}" \
    --description="Docker Repository for EcoQuest Backend" \
    --project="${PROJECT_ID}"
fi

# 5. Submit Cloud Build
IMAGE_TAG="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/backend:latest"
echo "Submitting Cloud Build for image: ${IMAGE_TAG}..."

# We execute the build from the backend folder where Dockerfile resides
# Since deploy.sh is at the root, the path to backend is ./backend
gcloud builds submit \
  --tag "${IMAGE_TAG}" \
  ./backend \
  --project="${PROJECT_ID}"

# 6. Deploy to Cloud Run
echo "Deploying to Cloud Run..."
gcloud run deploy ecoquest-backend \
  --image="${IMAGE_TAG}" \
  --region="${REGION}" \
  --platform=managed \
  --allow-unauthenticated \
  --min-instances=0 \
  --max-instances=10 \
  --memory=512Mi \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GCP_REGION=${REGION}" \
  --project="${PROJECT_ID}"

# 7. Print the service URL
SERVICE_URL=$(gcloud run services describe ecoquest-backend --region="${REGION}" --platform=managed --format="value(status.url)" --project="${PROJECT_ID}")

echo "=========================================="
echo " EcoQuest Backend Deployed Successfully!"
echo " Service URL: ${SERVICE_URL}"
echo "=========================================="
