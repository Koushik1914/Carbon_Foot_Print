import os
import logging
from google.cloud import firestore
import vertexai
from vertexai.generative_models import GenerativeModel

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ecoquest.config")

# Environment Variables with fallbacks
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT") or os.getenv("PROJECT_ID", "ecoquest-499004")
REGION = os.getenv("GCP_REGION") or os.getenv("REGION", "us-central1")

logger.info(f"Initializing EcoQuest config with Project: {PROJECT_ID}, Region: {REGION}")

# Firestore Client Singleton (Asynchronous)
# Note: If running locally without credentials, the environment variable GOOGLE_APPLICATION_CREDENTIALS should be set,
# or we fall back to local emulator/mock modes, but here we write production-ready code.
db = firestore.AsyncClient(project=PROJECT_ID)

# Initialize Vertex AI SDK
try:
    vertexai.init(project=PROJECT_ID, location=REGION)
    logger.info("Vertex AI SDK initialized successfully.")
except Exception as e:
    logger.error(f"Failed to initialize Vertex AI SDK: {e}")

def get_ai_model(system_instruction: str | None = None) -> GenerativeModel:
    """
    Returns a configured Vertex AI GenerativeModel instance for gemini-2.5-flash.
    """
    return GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=system_instruction
    )
