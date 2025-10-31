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

