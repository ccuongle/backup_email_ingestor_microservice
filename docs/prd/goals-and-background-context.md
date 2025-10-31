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

