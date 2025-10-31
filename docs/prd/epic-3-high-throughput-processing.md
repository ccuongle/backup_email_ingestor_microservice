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

