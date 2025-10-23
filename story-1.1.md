# Story 1.1: Refactor Ingestion Service to be Asynchronous

## User Story

**As a** System Architect,
**I want** to replace all synchronous `requests` calls in the `WebhookService` with an asynchronous `httpx` client,
**so that** the service can handle a high volume of concurrent notifications without blocking the event loop, improving I/O performance and overall system scalability.

## Technical Implementation Details

*   **Target File**: `core/webhook_service.py`
*   **Primary Change**: Replace the `requests` library with `httpx`.
*   **Refactoring Approach**:
    *   Convert all methods that perform HTTP I/O into `async def` functions. This includes:
        *   `_fetch_email_detail`
        *   `_create_subscription`
        *   `_delete_subscription`
        *   `_renew_subscription`
        *   The logic within the `_start_renewal_watcher` thread.
    *   Use `httpx.AsyncClient` for all API calls to the Microsoft Graph API.
    *   Ensure that `async` methods are properly `await`ed by their callers.
    *   The `handle_notification` method, which is called by the FastAPI endpoint, must be `async`.
    *   The background renewal watcher thread will need to be adapted to run an async loop using `asyncio.run()` or a similar mechanism.

## Acceptance Criteria

1.  [ ] The `requests` library is no longer imported or used in `core/webhook_service.py`.
2.  [ ] The `httpx` library is added as a dependency and used for all external HTTP calls within the `WebhookService`.
3.  [ ] The methods `_fetch_email_detail`, `_create_subscription`, `_delete_subscription`, and `_renew_subscription` are converted to `async def` and function correctly.
4.  [ ] The `handle_notification` method is `async` and successfully processes incoming webhook notifications by `await`ing the `_fetch_email_detail` call.
5.  [ ] The subscription renewal background task (`_start_renewal_watcher`) correctly runs the asynchronous renewal logic in its loop.
6.  [ ] The application successfully starts, creates a webhook subscription, processes an incoming email notification, and renews its subscription using the new asynchronous implementation.
7.  [ ] The existing error handling and fallback mechanisms remain fully functional.

## Definition of Done

*   [ ] All acceptance criteria are met.
*   [ ] Code is reviewed and approved by the QA agent or a peer.
*   [ ] All existing tests pass, and new tests for async functionality are added if applicable.
*   [ ] The story is merged into the main development branch.
