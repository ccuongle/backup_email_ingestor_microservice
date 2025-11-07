"""
utils/config.py
Configuration thống nhất cho toàn bộ microservice
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ============= Paths =============
BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "storage"
ATTACH_DIR = STORAGE_DIR / "attachments"
LOG_DIR = STORAGE_DIR / "logs"

# Tạo thư mục nếu chưa có
for directory in [STORAGE_DIR, ATTACH_DIR, LOG_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# Convert to string for backward compatibility
ATTACH_DIR = str(ATTACH_DIR)
LOG_DIR = str(LOG_DIR)

# ============= Microsoft Graph API =============
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

SCOPES = [
    "Mail.ReadWrite",
    "Mail.Send",
    "User.Read"
]

if not CLIENT_ID or not CLIENT_SECRET:
    raise ValueError(
        "Missing CLIENT_ID or CLIENT_SECRET. "
        "Please set them in .env file"
    )

# ============= Graph API Rate Limiting (NEW - Story 2.1) =============
GRAPH_API_RATE_LIMIT_THRESHOLD = int(os.getenv("GRAPH_API_RATE_LIMIT_THRESHOLD", "100"))
GRAPH_API_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("GRAPH_API_RATE_LIMIT_WINDOW_SECONDS", "60"))
GRAPH_API_RATE_LIMIT_RETRY_DELAY_SECONDS = int(os.getenv("GRAPH_API_RATE_LIMIT_RETRY_DELAY_SECONDS", "30"))

# ============= Graph API Retry Strategy (NEW - Story 2.2) =============
GRAPH_API_MAX_RETRIES = int(os.getenv("GRAPH_API_MAX_RETRIES", "5"))
GRAPH_API_INITIAL_BACKOFF_SECONDS = float(os.getenv("GRAPH_API_INITIAL_BACKOFF_SECONDS", "1"))
GRAPH_API_BACKOFF_FACTOR = float(os.getenv("GRAPH_API_BACKOFF_FACTOR", "2"))

# ============= Downstream Services =============
MS3_PERSISTENCE_BASE_URL = os.getenv(
    "MS3_PERSISTENCE_BASE_URL",
    "http://localhost:8002"
)

MS3_BATCH_SIZE = int(os.getenv("MS3_BATCH_SIZE", "50"))

# ============= RabbitMQ Settings =============
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USERNAME = os.getenv("RABBITMQ_USERNAME", "guest")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "guest")
RABBITMQ_VIRTUAL_HOST = os.getenv("RABBITMQ_VIRTUAL_HOST", "/")
RABBITMQ_QUEUE_NAME = os.getenv("RABBITMQ_QUEUE_NAME", "ms1_email_ingestor_queue")

# ============= Service Ports =============
API_PORT = int(os.getenv("API_PORT", "8000"))
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "8100"))

# ============= Polling Settings =============
DEFAULT_POLLING_INTERVAL = int(os.getenv("POLLING_INTERVAL", "300"))  # 5 phút
MAX_POLLING_ERRORS = int(os.getenv("MAX_POLLING_ERRORS", "3"))
MAX_POLL_PAGES = int(os.getenv("MAX_POLL_PAGES", "10"))

# ============= Webhook Settings =============
WEBHOOK_SUBSCRIPTION_EXPIRY_DAYS = int(os.getenv("WEBHOOK_EXPIRY_DAYS", "3"))
WEBHOOK_RENEWAL_THRESHOLD_HOURS = int(os.getenv("WEBHOOK_RENEWAL_HOURS", "1"))
MAX_WEBHOOK_ERRORS = int(os.getenv("MAX_WEBHOOK_ERRORS", "5"))

# ============= Spam Patterns =============
# Load from environment variable as a comma-separated string, then split into a list.
# This allows updating spam patterns without changing the code.
SPAM_PATTERNS_STR = os.getenv("SPAM_PATTERNS", (
    "accountprotection.microsoft.com,"
    "security-noreply@,"
    "account-security-noreply@accountprotection.microsoft.com,"
    "noreply@email.microsoft.com"
))
SPAM_PATTERNS = [pattern.strip() for pattern in SPAM_PATTERNS_STR.split(',') if pattern.strip()]

# ============= Logging Settings =============
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ============= Graph API Endpoints =============
GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
GRAPH_MESSAGES_URL = f"{GRAPH_BASE_URL}/me/messages"
GRAPH_SUBSCRIPTIONS_URL = f"{GRAPH_BASE_URL}/subscriptions"

# ============= Feature Flags =============
ENABLE_ATTACHMENT_SAVE = os.getenv("ENABLE_ATTACHMENT_SAVE", "true").lower() == "true"
ENABLE_MS4_FORWARD = os.getenv("ENABLE_MS4_FORWARD", "true").lower() == "true"
ENABLE_SPAM_FILTER = os.getenv("ENABLE_SPAM_FILTER", "true").lower() == "true"


# RabbitMQ Connection Configuration
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST')
RABBITMQ_PORT = int(os.getenv('RABBITMQ_PORT', 5672))
RABBITMQ_USERNAME = os.getenv('RABBITMQ_USERNAME')
RABBITMQ_PASSWORD = os.getenv('RABBITMQ_PASSWORD')
RABBITMQ_VIRTUAL_HOST = os.getenv('RABBITMQ_VIRTUAL_HOST', '/')

# MS1 Queue Topology (Producer)
RABBITMQ_EXCHANGE = os.getenv('RABBITMQ_EXCHANGE', 'email_exchange')
RABBITMQ_ROUTING_KEY = os.getenv('RABBITMQ_ROUTING_KEY', 'email.to.extractor')
RABBITMQ_QUEUE_NAME = os.getenv('RABBITMQ_QUEUE_NAME', 'queue.for_extraction')

# Service Settings
SERVICE_NAME = os.getenv('SERVICE_NAME', 'ms1_email_ingestor')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# ============= Validation =============
def validate_config():
    """Validate configuration"""
    errors = []
    
    if not CLIENT_ID:
        errors.append("CLIENT_ID is required")
    
    if not CLIENT_SECRET:
        errors.append("CLIENT_SECRET is required")

    if not RABBITMQ_HOST:
        errors.append("RABBITMQ_HOST is required")
    
    if not RABBITMQ_USERNAME:
        errors.append("RABBITMQ_USERNAME is required")
        
    if not RABBITMQ_PASSWORD:
        errors.append("RABBITMQ_PASSWORD is required")

    
    if API_PORT == WEBHOOK_PORT:
        errors.append(f"API_PORT ({API_PORT}) and WEBHOOK_PORT ({WEBHOOK_PORT}) must be different")
    
    # Validate rate limit configuration
    if GRAPH_API_RATE_LIMIT_THRESHOLD <= 0:
        errors.append(f"GRAPH_API_RATE_LIMIT_THRESHOLD must be positive (got {GRAPH_API_RATE_LIMIT_THRESHOLD})")
    
    if GRAPH_API_RATE_LIMIT_WINDOW_SECONDS <= 0:
        errors.append(f"GRAPH_API_RATE_LIMIT_WINDOW_SECONDS must be positive (got {GRAPH_API_RATE_LIMIT_WINDOW_SECONDS})")
    
    if GRAPH_API_RATE_LIMIT_RETRY_DELAY_SECONDS < 0:
        errors.append(f"GRAPH_API_RATE_LIMIT_RETRY_DELAY_SECONDS must be non-negative (got {GRAPH_API_RATE_LIMIT_RETRY_DELAY_SECONDS})")
    
    if errors:
        raise ValueError("Configuration errors:\n" + "\n".join(f"  - {e}" for e in errors))

# Validate on import
if __name__ == "__main__":
    validate_config()