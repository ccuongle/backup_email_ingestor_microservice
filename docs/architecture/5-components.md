# 5. Components

## 5.1. Component List

## 5.1.1. Polling Service

**Responsibility:** Periodically fetches unread emails from the Microsoft Graph API, applies initial filtering, and enqueues the raw email metadata into the Redis Inbound Queue.

**Key Interfaces:**
- Outbound: Microsoft Graph API (HTTPS)
- Outbound: Redis Inbound Queue (Redis commands via `redis_manager`)

**Dependencies:** `httpx`, `MSAL`, `redis_manager`, `utils/config`.

**Technology Stack:** Python, `httpx`, `MSAL`.

## 5.1.2. Webhook Service

**Responsibility:** Receives real-time email notifications from Microsoft Graph via a webhook endpoint, validates them, and enqueues the raw email metadata into the Redis Inbound Queue. It also manages the lifecycle of Microsoft Graph webhook subscriptions.

**Key Interfaces:**
- Inbound: Microsoft Graph Webhook (HTTPS)
- Outbound: Redis Inbound Queue (Redis commands via `redis_manager`)
- Outbound: Microsoft Graph API (for subscription management, HTTPS)

**Dependencies:** FastAPI, `httpx`, `MSAL`, `redis_manager`, `utils/config`.

**Technology Stack:** Python, FastAPI, `httpx`, `MSAL`.

## 5.1.3. Redis Inbound Queue

**Responsibility:** Acts as a high-performance, resilient buffer for raw email metadata received from the Polling and Webhook Services. It decouples the ingestion process from the email processing logic.

**Key Interfaces:**
- Inbound: `redis_manager` (for enqueuing by Polling/Webhook Services)
- Outbound: `redis_manager` (for dequeuing by Batch Processor)

**Dependencies:** Redis server.

**Technology Stack:** Redis.

## 5.1.4. Batch Processor

**Responsibility:** Consumes raw email metadata from the Redis Inbound Queue, processes each email (e.g., extracts relevant data, applies business logic, transforms data into MS4-compatible format), and places the prepared MS4 payload onto the Redis MS4 Outbound Queue.

**Key Interfaces:**
- Inbound: Redis Inbound Queue (Redis commands via `redis_manager`)
- Outbound: Redis MS4 Outbound Queue (Redis commands via `redis_manager`)

**Dependencies:** `redis_manager`, `core/unified_email_processor` (for email-specific logic), `utils/config`.

**Technology Stack:** Python.

## 5.1.5. Redis MS4 Outbound Queue

**Responsibility:** Buffers prepared MS4 payloads, decoupling the `Batch Processor` from the `MS4 Batch Sender`. This provides additional resilience against MS4 unavailability and allows for optimized batching to MS4.

**Key Interfaces:**
- Inbound: `redis_manager` (for enqueuing by Batch Processor)
- Outbound: `redis_manager` (for dequeuing by MS4 Batch Sender)

**Dependencies:** Redis server.

**Technology Stack:** Redis.

## 5.1.6. MS4 Batch Sender

**Responsibility:** Consumes prepared MS4 payloads from the Redis MS4 Outbound Queue, aggregates them into optimal batches, and sends these batches to the MS4 Persistence API. It incorporates retry logic, rate limiting, and error handling specific to MS4 communication.

**Key Interfaces:**
- Inbound: Redis MS4 Outbound Queue (Redis commands via `redis_manager`)
- Outbound: MS4 Persistence API (HTTPS)

**Dependencies:** `httpx`, `redis_manager`, `utils/config`.

**Technology Stack:** Python, `httpx`.

## 5.1.7. Control API

**Responsibility:** Provides a RESTful interface for external systems or administrators to manage the `ms1_email_ingestor` service, including starting/stopping sessions, triggering manual polls, and retrieving service metrics.

**Key Interfaces:**
- Inbound: REST API (HTTPS)

**Dependencies:** FastAPI, `core/session_manager`, `core/queue_manager`, `utils/config`.

**Technology Stack:** Python, FastAPI.

## 5.2. Component Diagrams

```mermaid
C4Container
    title System Context for ms1_email_ingestor
    Container(ms1_email_ingestor, "MS1 Email Ingestor", "Python Microservice", "Ingests, processes, and forwards invoice emails.")

    System_Ext(ms_graph, "Microsoft Graph API", "External System", "Provides email access and webhook notifications.")
    System_Ext(ms4_persistence, "MS4 Persistence Service", "External System", "Receives processed invoice metadata.")

    Rel(ms_graph, ms1_email_ingestor, "Sends email notifications to", "HTTPS")
    Rel(ms1_email_ingestor, ms_graph, "Fetches emails from", "HTTPS")
    Rel(ms1_email_ingestor, ms4_persistence, "Sends processed metadata to", "HTTPS")

    Container_Boundary(ms1_email_ingestor_boundary, "MS1 Email Ingestor") {
        Container(polling_service, "Polling Service", "Python Component", "Periodically fetches emails from MS Graph.")
        Container(webhook_service, "Webhook Service", "Python Component", "Receives real-time notifications from MS Graph.")
        Container(redis_inbound_queue, "Redis Inbound Queue", "Redis", "Buffers raw email metadata.")
        Container(batch_processor, "Batch Processor", "Python Component", "Consumes from Inbound Queue, processes emails.")
        Container(redis_ms4_outbound_queue, "Redis MS4 Outbound Queue", "Redis", "Buffers prepared MS4 payloads.")
        Container(ms4_batch_sender, "MS4 Batch Sender", "Python Component", "Sends batched payloads to MS4.")
        Container(control_api, "Control API", "Python FastAPI", "Provides RESTful management interface.")

        Rel(polling_service, redis_inbound_queue, "Enqueues raw email metadata", "Redis commands")
        Rel(webhook_service, redis_inbound_queue, "Enqueues raw email metadata", "Redis commands")
        Rel(redis_inbound_queue, batch_processor, "Consumes raw email metadata", "Redis commands")
        Rel(batch_processor, redis_ms4_outbound_queue, "Enqueues prepared MS4 payloads", "Redis commands")
        Rel(redis_ms4_outbound_queue, ms4_batch_sender, "Consumes prepared MS4 payloads", "Redis commands")
        Rel(ms4_batch_sender, ms4_persistence, "Sends batched payloads", "HTTPS")
        Rel(control_api, polling_service, "Triggers polls, manages state", "Internal API")
        Rel(control_api, webhook_service, "Manages subscriptions", "Internal API")
        Rel(control_api, redis_inbound_queue, "Monitors queue", "Redis commands")
        Rel(control_api, redis_ms4_outbound_queue, "Monitors queue", "Redis commands")
    }
```

---
