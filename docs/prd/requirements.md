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

