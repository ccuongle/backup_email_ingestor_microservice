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

