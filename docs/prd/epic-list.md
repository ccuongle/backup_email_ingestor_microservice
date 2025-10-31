Here is the proposed list of epics to achieve our goals:

*   **Epic 1: Codebase Modernization & Refactoring:**
    *   **Goal:** To improve code health and maintainability by removing dead code (MS2) and standardizing on a single, modern HTTP client (`httpx`). This provides a clean and stable foundation for future work.

*   **Epic 2: API Resilience & Error Handling:**
    *   **Goal:** To make the application more robust by implementing rate limiting and graceful error handling for the Microsoft Graph API. This will prevent failures and improve the service's reliability under load.

*   **Epic 3: High-Throughput Processing:**
    *   **Goal:** To achieve the target of processing 10,000+ invoices per session by implementing batch forwarding to the MS4 service, significantly reducing network I/O overhead.

