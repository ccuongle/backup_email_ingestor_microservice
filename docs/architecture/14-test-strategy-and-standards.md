# 14. Test Strategy and Standards

## 14.1. Testing Philosophy

*   **Approach:** We will adopt a balanced testing approach, emphasizing a "test pyramid" structure. This means a large base of fast, isolated unit tests, a smaller layer of integration tests verifying component interactions, and a minimal set of end-to-end tests for critical flows.
*   **Coverage Goals:** Aim for high unit test coverage (>90% line coverage) for core business logic and utilities. Integration tests will focus on covering all critical interaction paths between components and external services.
*   **Test Pyramid:**
    *   **Unit Tests:** Fast, isolated, cover individual functions/methods.
    *   **Integration Tests:** Verify interactions between components and with external dependencies (mocked or real isolated instances).
    *   **End-to-End Tests:** Minimal, cover critical user journeys through the entire system.

## 14.2. Test Types and Organization

### 14.2.1. Unit Tests

*   **Framework:** `pytest`
*   **File Convention:** `test_*.py`
*   **Location:** `tests/unit/` directory, mirroring the source code structure (e.g., `tests/unit/core/test_batch_processor.py`).
*   **Mocking Library:** Python's built-in `unittest.mock` (e.g., `MagicMock`, `patch`).
*   **Coverage Requirement:** Aim for >90% line coverage for core logic modules.
*   **AI Agent Requirements:**
    *   Generate tests for all public methods and functions.
    *   Cover edge cases, boundary conditions, and expected error scenarios.
    *   Follow the AAA (Arrange, Act, Assert) pattern for clarity.
    *   Mock all external dependencies (e.g., Redis, external APIs, file system) to ensure isolation.

### 14.2.2. Integration Tests

*   **Scope:** Verify interactions between internal components (e.g., `Batch Processor` with Redis queues) and with external dependencies (e.g., `MS4 Batch Sender` with MS4 API, `Polling Service` with Microsoft Graph API).
*   **Location:** `tests/integration/` directory.
*   **Test Infrastructure:**
    *   **Redis:** Use a dedicated, isolated Redis instance for integration tests (e.g., via `docker-compose` or `pytest-redis` fixtures).
    *   **External APIs (MS Graph, MS4):** Use mocking libraries (`httpx.mock`, `responses`) or dedicated test doubles (e.g., `WireMock` for more complex scenarios) to simulate external API behavior.

### 14.2.3. End-to-End Tests

*   **Scope:** Focus on critical end-to-end flows, such as a complete email ingestion cycle from MS Graph notification to successful persistence in MS4.
*   **Environment:** A dedicated, isolated test environment (e.g., a local `docker-compose` setup that spins up all components and mock external services).
*   **Test Data:** Use realistic, anonymized test data that covers various scenarios.

## 14.3. Test Data Management

*   **Strategy:** Prioritize programmatic generation of test data. Use `pytest` fixtures for setting up common test data and environment states.
*   **Fixtures:** Leverage `pytest` fixtures for reusable setup and teardown logic.
*   **Factories:** Consider using factory patterns for generating complex test data objects.
*   **Cleanup:** Ensure all test data and resources are cleaned up after each test run to maintain test isolation and prevent side effects.

## 14.4. Continuous Testing

*   **CI Integration:** All unit and integration tests will be integrated into the CI/CD pipeline and must pass for code merges.
*   **Performance Tests:** The existing `test_unitvsbatch_performnace.py` will be enhanced to cover the new batching logic and run regularly in CI to track performance against NFR1 (10,000 invoices/session).
*   **Security Tests:** Static Application Security Testing (SAST) tools will be integrated into the CI pipeline to scan for common vulnerabilities.

---
