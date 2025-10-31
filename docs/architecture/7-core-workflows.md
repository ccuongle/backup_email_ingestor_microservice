# 7. Core Workflows

## 7.1. Email Ingestion (Polling)

This workflow describes how the Polling Service actively fetches emails from Microsoft Graph and places them into the inbound queue.

```mermaid
sequenceDiagram
    participant PS as Polling Service
    participant MGA as Microsoft Graph API
    participant RIQ as Redis Inbound Queue

    PS->>MGA: 1. Request unread emails (GET /me/mailFolders/{id}/messages)
    MGA-->>PS: 2. Return unread emails (raw_json)
    loop For each email received
        PS->>RIQ: 3. Enqueue raw_json (EmailMessage)
    end
```

## 7.2. Email Ingestion (Webhook)

This workflow illustrates how the Webhook Service passively receives notifications from Microsoft Graph and enqueues them.

```mermaid
sequenceDiagram
    participant MGA as Microsoft Graph API
    participant WS as Webhook Service
    participant RIQ as Redis Inbound Queue

    MGA->>WS: 1. Send email notification (POST /webhook_endpoint)
    WS->>MGA: 2. Acknowledge notification (HTTP 202 Accepted)
    WS->>RIQ: 3. Enqueue raw_json (EmailMessage)
```

## 7.3. Email Processing and MS4 Batch Forwarding

This workflow details the end-to-end processing of an email from the inbound queue, through the batch processor, and finally to the MS4 Persistence API via the new outbound queue and batch sender.

```mermaid
sequenceDiagram
    participant BP as Batch Processor
    participant RIQ as Redis Inbound Queue
    participant RMQ as Redis MS4 Outbound Queue
    participant MS4S as MS4 Batch Sender
    participant MS4A as MS4 Persistence API

    loop Continuously
        BP->>RIQ: 1. Dequeue raw_json (EmailMessage)
        activate BP
        BP->>BP: 2. Process email (extract data, transform to MS4 payload)
        BP->>RMQ: 3. Enqueue prepared MS4 payload
        deactivate BP
    end

    loop Continuously
        MS4S->>RMQ: 4. Dequeue prepared MS4 payloads (batch)
        activate MS4S
        MS4S->>MS4S: 5. Aggregate payloads into MS4 batch format
        MS4S->>MS4A: 6. Send batch to MS4 (POST /batch-metadata)
        MS4A-->>MS4S: 7. Return batch processing status
        MS4S->>MS4S: 8. Handle MS4 response (retries, error logging)
        deactivate MS4S
    end
```

---
