
# ms1_email_ingestor Brownfield Architecture Document

## Introduction

This document captures the CURRENT STATE of the `ms1_email_ingestor` codebase, including its architecture, technical debt, and real-world patterns. It serves as a reference for AI agents and development teams working on enhancements, with a particular focus on improving performance to handle over 10,000 invoices per session.

### Document Scope

This is a comprehensive documentation of the entire system, with a special focus on areas relevant to performance enhancement, caching improvements, and system optimization.

### Change Log

| Date       | Version | Description                 | Author  |
|------------|---------|-----------------------------|---------|
| 2025-10-30 | 1.0     | Initial brownfield analysis | Winston |

## Quick Reference - Key Files and Entry Points

### Critical Files for Understanding the System

- **Main Entry**: `main_orchestrator.py` (Coordinates all services)
- **Configuration**: `utils/config.py` (Centralized configuration)
- **Core Business Logic**:
    - `core/unified_email_processor.py` (Single email processing logic)
    - `core/batch_processor.py` (Parallel processing engine)
- **API Definitions**:
    - `api/webhook_app.py` (FastAPI app for MS Graph webhooks)
- **Queue Management**: `core/queue_manager.py` (Redis-backed email queue)
- **Session Management**: `core/session_manager.py` (Manages ingestion sessions)
- **Authentication**: `core/token_manager.py` (Handles MS Graph API tokens)

## High Level Architecture

The system is an email ingestion microservice designed to fetch invoice emails from Microsoft Outlook, process them, and forward metadata to downstream services. It employs a robust, queue-centric architecture to decouple ingestion from processing, allowing for high throughput and resilience.

**Ingestion Sources:**
1.  **Polling**: A scheduled service (`core/polling_service.py`) periodically fetches unread emails.
2.  **Webhook**: A real-time service (`core/webhook_service.py`) listens for new email notifications from Microsoft Graph.

**Processing Pipeline:**
1.  Emails from both sources are placed into a Redis-backed queue (`core/queue_manager.py`).
2.  A `ThreadPool`-based batch processor (`core/batch_processor.py`) pulls emails from the queue in batches.
3.  Each email is processed by the `core/unified_email_processor.py`, which involves:
    - Spam filtering.
    - Saving attachments.
    - Forwarding metadata to the MS4 Persistence service.

### Actual Tech Stack

| Category      | Technology   | Version/Details                                 | Notes                                                                 |
|---------------|--------------|-------------------------------------------------|-----------------------------------------------------------------------|
| Language      | Python       | 3.x                                             |                                                                       |
| Framework     | FastAPI      | For the webhook endpoint (`api/webhook_app.py`) | Runs as a separate process.                                           |
| Async Server  | Uvicorn      | Standard ASGI server                            |                                                                       |
| Data Store    | Redis        | For queuing and session management              | Critical component for state management and buffering.                |
| HTTP Client   | httpx, requests| For communicating with MS Graph and other services | `requests` is used in some places, `httpx` in others.          |
| Authentication| MSAL         | `msal` library for Microsoft identity           | Acquires tokens for Graph API access.                                 |
| Other         | pyngrok      | To expose the local webhook endpoint            | A key component for the webhook service.                              |

### Repository Structure Reality Check

- **Type**: Monorepo (single repository for the microservice).
- **Package Manager**: `pip` with `requirements.txt`.
- **Notable**: The project is well-structured, with a clear separation of concerns between `api`, `core`, and `utils`. The use of a `concurrent_storage` directory suggests a custom abstraction over Redis.

## Source Tree and Module Organization

### Project Structure (Actual)

```text
project-root/
├── api/                  # FastAPI application for webhooks
│   ├── webhook_app.py    # The webhook endpoint logic
├── core/                 # Core business logic
│   ├── batch_processor.py  # Parallel email processing engine
│   ├── polling_service.py  # Scheduled email fetching
│   ├── queue_manager.py    # Redis-backed queue
│   ├── session_manager.py  # Manages the ingestion session state
│   ├── token_manager.py    # MSAL token handling
│   ├── unified_email_processor.py # Logic for processing a single email
│   └── webhook_service.py  # Manages MS Graph webhook subscriptions
├── utils/                # Utility functions and configuration
│   └── config.py         # Centralized configuration
├── tests/                # Integration and performance tests
├── main_orchestrator.py  # Main application entry point
└── requirements.txt      # Project dependencies
```

### Key Modules and Their Purpose

- **`main_orchestrator.py`**: The heart of the application. It initializes and coordinates the `polling_service`, `webhook_service`, and `batch_processor`.
- **`core/queue_manager.py`**: Implements a high-performance, Redis-backed queue that supports batching and priority. This is central to the system's ability to handle high volume.
- **`core/batch_processor.py`**: The processing engine. It uses a `ThreadPoolExecutor` to process emails in parallel, maximizing I/O-bound operations.
- **`core/unified_email_processor.py`**: Contains the business logic for what to do with an email. It currently forwards data to MS4.
- **`core/webhook_service.py`**: A clever implementation that uses `pyngrok` to create a public-facing webhook endpoint for real-time email notifications, reducing reliance on polling.

## Data Models and APIs

### Data Models

The primary data model is the email message object from the Microsoft Graph API. This is passed through the system as a dictionary.

### Redis Data Structures

The `concurrent_storage/redis_manager.py` provides a sophisticated abstraction over Redis, using specific data structures for efficiency and concurrency.

| Key Prefix             | Redis Type    | Purpose                                                              |
|------------------------|---------------|----------------------------------------------------------------------|
| `email:processed`      | Set           | Stores IDs of processed emails for O(1) duplicate checks.            |
| `email:pending`        | Sorted Set    | A priority queue for pending emails, with the score being a timestamp. |
| `email:failed`         | List          | A Dead Letter Queue (DLQ) for emails that failed processing.         |
| `session:current`      | Hash          | Stores the state and metadata of the currently active session.       |
| `sessions:history`     | List          | A capped list that stores historical session data for auditing.      |
| `webhook:subscription` | Hash          | Caches the current MS Graph webhook subscription details.            |
| `auth:refresh_token`   | String        | Stores the OAuth refresh token for the MSAL library.                 |
| `lock:*`               | String        | Used for distributed locks to prevent race conditions.               |
| `metrics:*`            | Hash          | Stores daily metrics, like `emails_processed`.                       |
| `ratelimit:*`          | String        | A counter used for implementing rate limiting logic.                 |

### API Specifications

#### Control API (`api/ms1_apiHanlder.py`)

A FastAPI application provides a RESTful control plane for the service, running on port 8000.

-   **`POST /session/start`**: Starts a new ingestion session.
    -   **Body**: `{"polling_mode": "scheduled" | "manual", "polling_interval": 300, "enable_webhook": true}`
-   **`POST /session/stop`**: Stops the current session.
    -   **Body**: `{"reason": "user_requested"}`
-   **`GET /session/status`**: Retrieves the status of the current session, including all services and queue stats.
-   **`POST /polling/trigger`**: Manually triggers a one-time poll for unread emails.
-   **`GET /metrics`**: Provides high-level metrics about the current session.

#### External APIs

-   **Microsoft Graph API**: Heavily used for fetching emails, managing webhooks, and marking emails as read.

-   **MS4 Persistence Service**: `POST` request to `http://localhost:8002/metadata`.

## Technical Debt and Known Issues

### Critical Technical Debt


2.  **Inconsistent HTTP Clients**: The codebase uses both `requests` and `httpx`. Standardizing on `httpx` would be beneficial as it supports async requests, which could be a future performance enhancement.

### Workarounds and Gotchas

-   **`pyngrok` Dependency**: The webhook service is critically dependent on `ngrok`. If `ngrok` is down or blocked, the real-time ingestion will fail, and the system will have to rely on polling.
-   **Redis State**: The application's state is entirely dependent on Redis. The `concurrent_storage/session_manager.py` script provides a CLI for managing this state, which is essential for debugging and manual intervention.

## Integration Points and External Dependencies

### External Services

| Service           | Purpose                               | Integration Type | Key Files                               |
|-------------------|---------------------------------------|------------------|-----------------------------------------|
| Microsoft Graph   | Email fetching and notifications      | REST API         | `polling_service.py`, `webhook_service.py` |

| MS4 Persistence   | Data persistence                      | REST API         | `unified_email_processor.py`            |
| ngrok             | Public URL for webhook                | SDK              | `webhook_service.py`                    |

## Development and Deployment

### Local Development Setup

1.  Install dependencies: `pip install -r requirements.txt`
2.  Set up a `.env` file with the required `CLIENT_ID` and `CLIENT_SECRET`.
3.  Ensure Redis is running and accessible.
4.  Run the main orchestrator: `python main_orchestrator.py`
5.  (Optional) Run the Control API: `uvicorn api.ms1_apiHanlder:app --port 8000`

### Developer Utilities

-   **Session Management CLI**: The `concurrent_storage/session_manager.py` script provides a command-line interface to view, clear, and reset session data in Redis. This is an essential tool for development and debugging.
    ```bash
    # View current session info
    python concurrent_storage/session_manager.py info

    # Clear the current session
    python concurrent_storage/session_manager.py clear
    ```

### Build and Deployment Process

There is no formal build or deployment process documented. The application is run directly from the Python source code.

## Testing Reality

### Current Test Coverage

The `tests/` directory contains `intergration_test.py` and `test_unitvsbatch_performnace.py`, suggesting that there is some level of integration and performance testing. The exact coverage is unknown.

### Running Tests

The method for running tests is not explicitly documented, but it is likely done using `pytest` or `unittest`.

## Enhancement Focus: Performance for 10,000+ Invoices

Based on the goal of enhancing performance, here are key areas for investigation:

### Potential Bottlenecks

1.  **API Rate Limiting**: The application makes numerous calls to the Graph API. At high volume, it is likely to hit rate limits. The code does not appear to have any explicit rate limit handling (e.g., exponential backoff, checking `Retry-After` headers).
2.  **`unified_email_processor` I/O**: This processor performs multiple network requests for each email (to MS4). While the `batch_processor` parallelizes this, it could still be a bottleneck.
3.  **Database Contention (Redis)**: While Redis is very fast, at extreme scale, contention on the queue could become an issue. The use of Lua scripts for atomic operations is a good practice that mitigates this.

### Caching and Performance Improvement Suggestions

1.  **Activate and Use Built-in Rate Limiting**: The `redis_manager.py` includes a `check_rate_limit` function that is not currently used. This should be integrated into the Graph API calls in `polling_service.py` and `webhook_service.py` to prevent hitting API limits.
2.  **Implement Graph API Rate Limit Handling**: Add logic to respectfully handle `429 Too Many Requests` and `503 Service Unavailable` responses from the Graph API, using the `Retry-After` header.
3.  **Batch Forwarding to MS4**: The `unified_email_processor` forwards emails one by one to MS4. If MS4 supports a batch endpoint, modifying the processor to forward emails in batches would significantly reduce network overhead.
4.  **Connection Pooling**: Ensure that the HTTP clients (`requests` and `httpx`) are using connection pooling effectively to avoid the overhead of creating new connections for each request.
5.  **Asynchronous Processing**: While the `batch_processor` uses threads, the core processing logic in `unified_email_processor` is synchronous. A future enhancement could be to refactor this to be fully async using `httpx`, which might offer better performance under high I/O load.

## Appendix - Useful Commands and Scripts

### Starting the Service

```bash
# Run the main orchestrator with default settings (scheduled polling and webhooks)
python main_orchestrator.py

# Run in polling-only mode
python main_orchestrator.py --no-webhook

# Trigger a single poll and exit
python main_orchestrator.py --poll-once
```
### Interacting with the Control API
```bash
# Get session status
curl http://localhost:8000/session/status

# Start a new session
curl -X POST http://localhost:8000/session/start -H "Content-Type: application/json" -d '{}'

# Stop the current session
curl -X POST http://localhost:8000/session/stop -H "Content-Type: application/json" -d '{"reason": "manual_stop"}'
```

