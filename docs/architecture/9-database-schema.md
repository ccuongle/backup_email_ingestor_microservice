# 9. Database Schema

Our primary data store is Redis, which will be used for queuing, session management, caching, and rate limiting. The following outlines the key patterns and data structures:

## 9.1. EmailMessage Storage

*   **Key Pattern:** `email:{email_id}`
*   **Type:** Hash
*   **Purpose:** Stores the complete `EmailMessage` object, including its `raw_json` content and derived metadata. This allows for efficient retrieval of individual email details.
*   **Example:** `HSET email:12345 id "12345" sender_address "sender@example.com" subject "Invoice" received_datetime "2025-10-30T10:00:00Z" raw_json "{...}"`

## 9.2. Redis Inbound Queue

*   **Key Pattern:** `queue:inbound`
*   **Type:** List
*   **Purpose:** A FIFO (First-In, First-Out) queue storing `email_id`s of emails awaiting processing. This decouples ingestion from the `Batch Processor`.
*   **Operations:** `LPUSH` (for enqueuing by Polling/Webhook Services), `BRPOP` (for dequeuing by Batch Processor).

## 9.3. Redis MS4 Outbound Queue

*   **Key Pattern:** `queue:ms4_outbound`
*   **Type:** List
*   **Purpose:** A FIFO queue storing prepared MS4 payloads (or `email_id`s referencing `email:{email_id}` hashes) for batch sending to MS4.
*   **Operations:** `LPUSH` (for enqueuing by Batch Processor), `BRPOP` (for dequeuing by MS4 Batch Sender).

## 9.4. SessionState Storage

*   **Key Pattern:** `session:current`
*   **Type:** Hash
*   **Purpose:** Stores the attributes of the active `SessionState` object, providing a centralized location for monitoring and managing the current ingestion session.
*   **Example:** `HSET session:current session_id "abc-123" status "running" emails_processed_count "150" emails_failed_count "2"`

## 9.5. WebhookSubscription Storage

*   **Key Pattern:** `webhook:subscription`
*   **Type:** Hash
*   **Purpose:** Stores the attributes of the active `WebhookSubscription` object, including its ID, resource, and expiration details.
*   **Example:** `HSET webhook:subscription subscription_id "sub-456" resource "/me/messages" expiration_datetime "2025-10-30T11:00:00Z" client_state "mysecret"`

## 9.6. Rate Limiting Counters

*   **Key Pattern:** `ratelimit:{api_key}:{timestamp_window}`
*   **Type:** String (counter) or Sorted Set (for more advanced sliding window implementations)
*   **Purpose:** Used to track the number of API calls made within a specific time window for each external API, enabling proactive rate limiting.

## 9.7. Processed Email Tracking

*   **Key Pattern:** `email:processed`
*   **Type:** Set
*   **Purpose:** Stores `email_id`s of emails that have been successfully processed and forwarded to MS4. This prevents duplicate processing and ensures idempotency.
*   **Operations:** `SADD` (add to set), `SISMEMBER` (check for existence).

## 9.8. Data Lifecycle Management (TTL)

*   **Mechanism:** Redis TTL (Time To Live) will be applied to keys where data has a natural expiration or limited retention requirement.
*   **Purpose:** To automatically remove stale data, manage memory usage, and ensure data freshness.
*   **Application:**
    *   `email:{email_id}` hashes: TTL will be set for a configurable period (e.g., 7 days) after successful processing to retain raw email data for auditing/debugging.
    *   Queue items: While queues are transient, mechanisms will be in place to prevent indefinite retention of unprocessed items (e.g., moving to a DLQ after a certain age, or setting TTLs on individual queue entries if applicable).
    *   `SessionState` and `WebhookSubscription`: TTLs will be considered for these keys if their associated entities have a defined expiration.

---
