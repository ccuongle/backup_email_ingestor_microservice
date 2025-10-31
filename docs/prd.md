# ms1_email_ingestor Product Requirements Document (PRD)

## 1. Goals and Background Context

### 1.1. Goals

*   **Performance Enhancement:** Scale the system to reliably process over 10,000 invoices per session.
*   **Modernize Architecture:** Retire the legacy MS2 Classifier microservice and remove its integration points.
*   **Improve Resilience:** Implement robust caching and rate-limiting strategies to handle external service limitations and improve throughput.

### 1.2. Background Context

The `ms1_email_ingestor` is a critical microservice responsible for ingesting invoice-related emails from Microsoft Outlook. It uses a queue-centric architecture with Redis to manage high-volume email ingestion from two sources: a periodic polling service and a real-time webhook. Emails are processed in parallel batches, with invoice metadata being forwarded to the MS4 Persistence service. This PRD outlines the requirements to significantly enhance its performance and scalability.

### 1.3. Change Log

| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2025-10-30 | 1.0 | Initial draft and checklist validation | John |

---

## 2. Requirements

### 2.1. Functional

*   **FR1:** The system must remove all code and configuration related to the MS2 Classifier service from the `core/unified_email_processor.py` module and any other relevant files.
*   **FR2:** The system must implement a rate-limiting mechanism, using the existing `redis_manager.py` functionality, to avoid exceeding Microsoft Graph API quotas.
*   **FR3:** The system must gracefully handle `429 (Too Many Requests)` and `503 (Service Unavailable)` errors from the Graph API by implementing an exponential backoff strategy that respects the `Retry-After` header.
*   **FR4:** The `unified_email_processor` shall be refactored to aggregate processed email data and forward it to the MS4 Persistence service in batches, reducing the total number of outbound HTTP requests. (This is dependent on MS4 supporting a batch-receptive endpoint).

### 2.2. Non-Functional

*   **NFR1:** The end-to-end email processing pipeline must support a throughput of at least 10,000 invoices per session.
*   **NFR2:** The codebase shall be standardized to use the `httpx` library for all HTTP client operations, retiring the `requests` library to maintain consistency.
*   **NFR3:** All HTTP clients used for communicating with external services (MS Graph, MS4) must utilize connection pooling to minimize connection overhead.
*   **NFR4:** The application must be scanned for known vulnerabilities using a tool like `pip-audit`, and all critical vulnerabilities must be remediated.

---

## 3. Technical Assumptions

### 3.1. Repository Structure: Monorepo

The project will continue to be maintained in a single repository (monorepo), as this is the existing structure and is suitable for a single, focused microservice.

### 3.2. Service Architecture

The application is a self-contained microservice. While it interacts with other services (MS Graph, MS4), its own architecture is not distributed. We will enhance the existing patterns rather than re-architecting to a different paradigm like serverless or multiple microservices.

### 3.3. Testing Requirements: Unit + Integration

Testing will include both unit tests for individual components and integration tests to verify interactions between the service and its external dependencies (like Redis and the MS4 service). The existing tests in the `tests/` directory will be augmented to cover new functionality.

### 3.4. Additional Technical Assumptions and Requests

*   **Language:** Python 3.x
*   **Primary Framework:** FastAPI will continue to be used for the API endpoints.
*   **Data Store:** Redis remains the primary data store for queuing, session management, and caching.
*   **HTTP Client:** All new and refactored code will use `httpx` for its async support and to standardize the codebase.
*   **Deployment:** The application will continue to be run directly from source via `python main_orchestrator.py`. No containerization or formal build process is in scope for this phase of work.

---

## 4. Epic List

Here is the proposed list of epics to achieve our goals:

*   **Epic 1: Codebase Modernization & Refactoring:**
    *   **Goal:** To improve code health and maintainability by removing dead code (MS2) and standardizing on a single, modern HTTP client (`httpx`). This provides a clean and stable foundation for future work.

*   **Epic 2: API Resilience & Error Handling:**
    *   **Goal:** To make the application more robust by implementing rate limiting and graceful error handling for the Microsoft Graph API. This will prevent failures and improve the service's reliability under load.

*   **Epic 3: High-Throughput Processing:**
    *   **Goal:** To achieve the target of processing 10,000+ invoices per session by implementing batch forwarding to the MS4 service, significantly reducing network I/O overhead.

---

## 5. Epic 1: Codebase Modernization & Refactoring

**Goal:** To improve code health and maintainability by removing dead code (MS2) and standardizing on a single, modern HTTP client (`httpx`). This provides a clean and stable foundation for future work.

### Story 1.1: Remove MS2 Classifier Integration

*   **As a** developer,
*   **I want** to remove all code, configuration, and API calls related to the retired MS2 Classifier service,
*   **so that** the codebase is cleaner and no resources are wasted.

**Acceptance Criteria:**
1.  All logic making `POST` requests to the MS2 service in `core/unified_email_processor.py` is removed.
2.  Configuration entries for the MS2 service URL are removed from `utils/config.py`.
3.  The "MS2 Classifier" is removed from all relevant documentation, including `brownfield-architecture.md`.
4.  All existing unit and integration tests pass, confirming that the removal does not negatively impact the email processing workflow.

### Story 1.2: Refactor MS4 Communication to use `httpx`

*   **As a** developer,
*   **I want** to refactor the `core/unified_email_processor.py` to use `httpx` for forwarding data to the MS4 Persistence Service,
*   **so that** this critical communication path is aligned with our modern library standards.

**Acceptance Criteria:**
1.  The `requests` library is no longer used in `core/unified_email_processor.py`.
2.  The API call to the MS4 service is successfully executed using the `httpx` library.
3.  A shared `httpx.Client` instance is used to leverage connection pooling for calls to MS4.
4.  Integration tests are updated to verify that data is still correctly forwarded to and received by the MS4 service.

### Story 1.3: Standardize All HTTP Communication on `httpx`

*   **As a** developer,
*   **I want** to replace all remaining instances of the `requests` library with `httpx` across the entire codebase,
*   **so that** the project's HTTP communication is fully standardized and consistent.

**Acceptance Criteria:**
1.  A project-wide search confirms no active usage of the `requests` library remains.
2.  The `requests` library is removed from the `requirements.txt` file.
3.  All functionality previously relying on `requests` (e.g., in `core/polling_service.py`, `core/webhook_service.py`) operates correctly using `httpx`.
4.  All relevant tests pass, confirming no regressions were introduced.

---

## 6. Epic 2: API Resilience & Error Handling

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

---

## 7. Epic 3: High-Throughput Processing

**Goal:** To achieve the target of processing 10,000+ invoices per session by implementing batch forwarding to the MS4 service, significantly reducing network I/O overhead.

### Story 3.1: Investigate and Define MS4 Batch Endpoint Contract

*   **As a** product manager,
*   **I want** to investigate and document the API contract for a batch submission endpoint in the MS4 Persistence service,
*   **so that** the development team has a clear specification to build against.

**Acceptance Criteria:**
1.  The MS4 service's documentation and/or source code is analyzed to determine if a batch endpoint exists.
2.  If an endpoint exists, its URL, payload structure, and response codes are documented in a new file: `docs/ms4_api_contract.md`.
3.  If no such endpoint exists, this finding is documented, and this story is considered blocked until the MS4 team can provide the endpoint.
4.  The potential performance impact of batch size is considered and a recommended batch size is documented.

### Story 3.2: Adapt Email Processor for Batch Aggregation

*   **As a** developer,
*   **I want** to refactor the `unified_email_processor` so that it returns structured data instead of directly calling the MS4 service,
*   **so that** its output can be aggregated for batch processing.

**Acceptance Criteria:**
1.  The `unified_email_processor` is modified to no longer make a direct `httpx` call to MS4.
2.  The processor's primary function now returns the JSON payload that was previously sent to MS4.
3.  The `batch_processor` is updated to handle this new return value without breaking the existing (non-batch) workflow.
4.  All unit tests for the `unified_email_processor` are updated to reflect the new return signature and behavior.

### Story 3.3: Implement Batch Forwarding to MS4

*   **As a** developer,
*   **I want** to modify the `batch_processor` to collect data from multiple processed emails and send it to MS4 as a single batch,
*   **so that** we dramatically reduce network requests and increase overall throughput.

**Acceptance Criteria:**
1.  The `batch_processor` accumulates the data returned from `unified_email_processor` up to a configurable batch size (e.g., 50).
2.  A single `httpx` POST request is sent to the MS4 batch endpoint with the aggregated payload.
3.  The processor correctly handles success and error responses for the entire batch.
4.  The existing performance test, `tests/test_unitvsbatch_performnace.py`, is updated to measure and assert the throughput improvement against the 10,000 invoice-per-session target.
5.  The system correctly handles partial batches (e.g., when the queue is nearly empty).

---

## 8. Checklist Results Report

### Executive Summary

*   **Overall PRD Completeness:** 90%
*   **MVP Scope Appropriateness:** Just Right
*   **Readiness for Architecture Phase:** Nearly Ready
*   **Most Critical Gaps:** The primary blocker is the unknown status of the MS4 batch endpoint (Story 3.1). Secondary gaps include a lack of explicit security and operational monitoring requirements.

### Category Analysis

| Category | Status | Critical Issues |
| :--- | :--- | :--- |
| 1. Problem Definition & Context | PASS | None |
| 2. MVP Scope Definition | PASS | None |
| 3. User Experience Requirements | N/A | Not applicable for a backend service. |
| 4. Functional Requirements | PASS | None |
| 5. Non-Functional Requirements | PARTIAL | Security & Compliance requirements are not explicitly defined. |
| 6. Epic & Story Structure | PASS | None |
| 7. Technical Guidance | PASS | None |
| 8. Cross-Functional Requirements | PARTIAL | Operational requirements (monitoring, alerting) are not defined. |
| 9. Clarity & Communication | PASS | None |

### Top Issues by Priority

*   **BLOCKER:** The implementation of Epic 3 is entirely dependent on the existence of a batch endpoint in the MS4 service. This must be investigated (Story 3.1) before proceeding with that epic.
*   **HIGH:** The PRD lacks specific non-functional requirements related to security (e.g., dependency scanning, code hardening practices).
*   **MEDIUM:** The PRD lacks requirements for operational monitoring and alerting, which are crucial for a production-grade service.

### Recommendations

1.  **Initiate MS4 API Discovery:** Prioritize Story 3.1 immediately. The architect or a lead developer should engage with the MS4 team to get a definitive answer on the batch endpoint.
2.  **Add Security NFR:** Add a new non-functional requirement (NFR4) stating: "The application must be scanned for known vulnerabilities using a tool like `pip-audit`, and all critical vulnerabilities must be remediated."
3.  **Add Monitoring Story:** Add a new story to Epic 2 (e.g., Story 2.3) to "Implement basic health check and metrics endpoints" that can be consumed by a monitoring service.

### Final Decision: NEEDS REFINEMENT

The PRD is comprehensive but requires the above refinements to be considered fully ready for the architecture and development phases. The blocker on Epic 3 must be resolved.

---

## 9. Next Steps

### UX Expert Prompt

Not applicable for this project.

### Architect Prompt

"Hello, Architect. Please review the Product Requirements Document located at `docs/prd.md`. Your task is to create a technical architecture and implementation plan based on these requirements.

Pay close attention to the following:

1.  **Blocker on Epic 3:** The highest priority is to action Story 3.1 and determine if the MS4 service supports batch ingestion. The entire performance goal hinges on this. Please investigate and report back immediately.
2.  **Technical Stack:** The plan should adhere to the existing technical stack (Python, FastAPI, Redis, httpx) as outlined in the "Technical Assumptions" section.
3.  **Epic 1 & 2:** Your implementation plan should detail the tasks required to execute the stories in the first two epics, which focus on code cleanup and resilience.

I am available to clarify any requirements."