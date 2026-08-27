#!/usr/bin/env bash
# Build and deploy to Cloud Run.
#
#   ./scripts/deploy_cloudrun.sh              # deploy with current gcloud project
#   PROJECT_ID=other-project ./scripts/deploy_cloudrun.sh
#
# Cloud Run holds websockets open for the request timeout, so that is set high;
# min-instances=0 keeps an idle demo free, at the cost of a cold start.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-europe-west3}"          # Frankfurt: EU data residency matters here
SERVICE="${SERVICE:-sikia-lab}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${SERVICE}/${SERVICE}:$(git rev-parse --short HEAD)"

if [[ -z "${PROJECT_ID}" ]]; then
  echo "No GCP project set. Run: gcloud config set project <id>" >&2
  exit 1
fi

echo "==> project=${PROJECT_ID} region=${REGION} service=${SERVICE}"

echo "==> enabling APIs (no-op if already enabled)"
gcloud services enable run.googleapis.com artifactregistry.googleapis.com \
  cloudbuild.googleapis.com --project "${PROJECT_ID}"

if ! gcloud artifacts repositories describe "${SERVICE}" \
     --location "${REGION}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
  echo "==> creating Artifact Registry repo"
  gcloud artifacts repositories create "${SERVICE}" \
    --repository-format=docker --location="${REGION}" --project "${PROJECT_ID}"
fi

echo "==> building ${IMAGE}"
gcloud builds submit --tag "${IMAGE}" --project "${PROJECT_ID}"

echo "==> deploying"
gcloud run deploy "${SERVICE}" \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --project "${PROJECT_ID}" \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --memory 512Mi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 3 \
  --timeout 3600 \
  --set-env-vars "SIKIA_PROVIDER_MODE=fake"

URL="$(gcloud run services describe "${SERVICE}" --region "${REGION}" \
       --project "${PROJECT_ID}" --format 'value(status.url)')"

echo
echo "==> live at ${URL}"
echo "    health:    curl ${URL}/healthz | jq"
echo "    websocket: ${URL/https:/wss:}/ws/transcribe"
