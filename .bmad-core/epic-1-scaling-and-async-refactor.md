# Epic 1: System Scaling and Asynchronous Refactor

## Epic Goal

To refactor the email ingestion pipeline for high-throughput scalability by replacing synchronous operations with a fully asynchronous, queue-based architecture. This will enable the system to handle over 10,000 emails per session and improve overall resilience and performance.

## Epic Description

### Existing System Context

- **Current Functionality**: The system currently ingests emails via a webhook and a polling mechanism. It uses an in-process `ThreadPoolExecutor` to process emails, which creates a performance bottleneck and a single point of failure.
- **Technology Stack**: Python, FastAPI, `requests` for HTTP calls.
- **Integration Points**: The `WebhookService` and `PollingService` both feed into an in-memory queue managed by the `BatchProcessor`.

### Enhancement Details

- **What's being changed**: The synchronous `requests` library in the ingestion services will be replaced with an asynchronous `httpx` client. The in-process `ThreadPoolExecutor` and queue will be replaced by a distributed task queue system (Celery with a RabbitMQ/Redis broker). Attachment handling will be offloaded to a cloud object store like Amazon S3.
- **How it integrates**: The `WebhookService` and `PollingService` will be modified to dispatch tasks to the new distributed queue instead of the local one. A new set of scalable, stateless "Processing Workers" will consume tasks from this queue.
- **Success criteria**: The system can successfully process 10,000+ emails with attachments in a single session without significant performance degradation or errors. The ingestion layer operates fully asynchronously.

## Stories

1.  **Story 1.1: Refactor Ingestion Service to be Asynchronous**: Replace synchronous `requests` calls in `core/webhook_service.py` with an asynchronous `httpx` client to improve I/O performance and prevent blocking.
2.  **Story 1.2: Implement Distributed Task Queue with Celery**: Replace the `BatchProcessor` and its `ThreadPoolExecutor` with a Celery-based distributed task queue. Define a `process_email` task and configure Celery workers.
3.  **Story 1.3: Offload Attachment Storage to Cloud**: Modify the email processing task to stream and save attachments directly to a cloud object store (e.g., Amazon S3) instead of the local filesystem.

## Compatibility Requirements

- [x] Existing APIs for starting/stopping sessions must remain unchanged.
- [x] The core logic of email processing (spam filtering, deduplication) should be preserved within the new task-based structure.
- [ ] The system must remain functional after each story is implemented, allowing for incremental rollout.

## Risk Mitigation

- **Primary Risk**: Introducing instability or data loss during the transition from the in-process queue to the distributed queue.
- **Mitigation**: The transition will be managed story-by-story. We will run the old and new systems in parallel during a testing phase if necessary. Feature flags can be used to switch between the old and new processing logic.
- **Rollback Plan**: Revert the code changes for the specific story. Since the changes are modular (async client, then Celery, then S3), rollbacks are isolated to each stage. For the queue transition, a temporary dual-write strategy could be employed to ensure no messages are lost during the switchover.

## Definition of Done

- [ ] All stories (1.1, 1.2, 1.3) are completed with their acceptance criteria met.
- [ ] The system successfully processes a load test of 10,000 emails with attachments.
- [ ] Existing functionality is verified through regression testing.
- [ ] The new asynchronous and distributed architecture is documented.
- [ ] No performance regressions are observed in existing, untouched parts of the system.