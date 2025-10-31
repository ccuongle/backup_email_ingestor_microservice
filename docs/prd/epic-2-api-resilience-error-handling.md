**Goal:** To make the application more robust by implementing rate limiting and graceful error handling for the Microsoft Graph API. This will prevent failures and improve the service's reliability under load.

### Story 2.1: Activate Proactive Graph API Rate Limiting

*   **As a** developer,
*   **I want** to activate the existing Redis-based rate-limiting utility before making calls to the Microsoft Graph API,
*   **so that** the application proactively avoids `429 (Too Many Requests)` errors.

**Acceptance Criteria:**
1.  The `check_rate_limit` function from `concurrent_storage/redis_manager.py` is integrated into the Graph API calling logic in both `core/polling_service.py` and `core/webhook_service.py`.
2.  The rate limit's threshold and time window are configurable in `utils/config.py`.
3.  When the rate limit is exceeded, the task (poll or webhook process) pauses execution for a configurable duration before retrying, preventing request loss.
4.  Unit tests verify that the rate limiter correctly blocks requests when the configured threshold is surpassed.

### Story 2.2: Implement Graph API Error Backoff Strategy

*   **As a** developer,
*   **I want** to implement a retry mechanism that handles `429 (Too Many Requests)` and `503 (Service Unavailable)` responses from the Graph API,
*   **so that** the application can automatically recover from temporary API throttling or outages.

**Acceptance Criteria:**
1.  A decorator or wrapper is applied to all Graph API calls made with `httpx`.
2.  The wrapper catches `429` and `503` HTTP status codes.
3.  Upon catching a handled error, the wrapper reads the `Retry-After` header from the API response and waits for the specified duration.
4.  If no `Retry-After` header is present, it uses a default exponential backoff strategy.
5.  A configurable maximum number of retries is implemented to avoid infinite loops.
6.  Integration tests are created to simulate `429` and `503` responses and assert that the retry logic is executed correctly.

### Story 2.3: Implement Health Check and Metrics Endpoints

*   **As an** operator,
*   **I want** basic health check and metrics endpoints,
*   **so that** the service's health and performance can be monitored by an external tool.

**Acceptance Criteria:**
1.  A `/health` endpoint is added to the main FastAPI application that returns a `200 OK` status if the service is running and can connect to Redis.
2.  A `/metrics` endpoint is added that exposes key application metrics in a simple JSON format (e.g., `{"emails_processed": 123, "emails_failed": 4, "current_queue_size": 56}`).
3.  The metrics should be sourced from the `RedisStorageManager`'s metrics and counter functions.
4.  The new endpoints are excluded from any authentication requirements.

