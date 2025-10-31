# 13. Coding Standards

## 13.1. Core Standards

*   **Languages & Runtimes:** Python 3.x (latest stable version).
*   **Style & Linting:** Adherence to **PEP 8** for code style. We will use `flake8` for linting and `black` for automated code formatting to ensure consistency.
*   **Test Organization:** Test files must reside in the `tests/` directory, mirroring the source code structure (e.g., `tests/unit/core/test_batch_processor.py`).

## 13.2. Naming Conventions

*   We will strictly adhere to **PEP 8 naming conventions**:
    *   `snake_case` for functions, variables, and module names.
    *   `PascalCase` for class names.
    *   `UPPER_SNAKE_CASE` for constants.

## 13.3. Critical Rules

*   **Logging:** Always use the configured Python `logging` module for all output. Direct `print()` statements are forbidden in production code.
*   **Configuration:** All configurable parameters (e.g., API keys, URLs, thresholds) must be loaded from `utils/config.py` or environment variables; hardcoding values is strictly prohibited.
*   **Redis Access:** All interactions with Redis must be encapsulated within and routed through `concurrent_storage/redis_manager.py` to ensure consistent data access patterns and proper error handling.
*   **External API Calls:** All outbound HTTP calls to external APIs (Microsoft Graph, MS4) must use the `httpx` library and be wrapped with the defined retry and circuit breaker policies.
*   **Secrets Management:** Never hardcode secrets or sensitive information. Access them securely via environment variables or a dedicated secrets management solution.
*   **Idempotency:** When designing interactions with external systems (especially MS4), ensure that operations are idempotent where possible.

## 13.4. Language-Specific Guidelines

### 13.4.1. Python Specifics

*   **Type Hinting:** Use Python type hints for all function signatures, class attributes, and complex data structures to improve code clarity, enable static analysis, and enhance maintainability.
*   **Asynchronous Code:** Prefer `asyncio` and the `async`/`await` syntax for all I/O-bound operations, particularly within FastAPI endpoints and when making external API calls, to maximize concurrency and performance.

---
