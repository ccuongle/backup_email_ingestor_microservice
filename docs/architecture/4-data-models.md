# 4. Data Models

## 4.1. EmailMessage

**Purpose:** Represents an email ingested from Microsoft Graph, containing the raw metadata and essential derived attributes. This is the primary entity processed throughout the system.

**Key Attributes:**
- `id`: `string` - Unique identifier from Microsoft Graph.
- `sender_address`: `string` - Email address of the sender.
- `subject`: `string` - Subject line of the email.
- `received_datetime`: `datetime` - Timestamp when the email was received.
- `raw_json`: `JSON object` - The raw, complete metadata of the incoming email from Microsoft Graph.

**Relationships:**
- An `EmailMessage` is processed by the `Batch Processor`.
- Data for the `MS4 Persistence API` is extracted and transformed from the `raw_json` attribute.

## 4.2. SessionState

**Purpose:** Manages the operational state and metadata of a single email ingestion session.

**Key Attributes:**
- `session_id`: `string` - Unique identifier for the ingestion session.
- `status`: `string` - Current status of the session (e.g., "running", "paused", "completed", "error").
- `start_time`: `datetime` - Timestamp when the session was initiated.
- `end_time`: `datetime` - Timestamp when the session concluded.
- `emails_processed_count`: `integer` - Total number of emails successfully processed within the session.
- `emails_failed_count`: `integer` - Total number of emails that encountered processing failures within the session.

**Relationships:**
- Managed by the `core/session_manager.py` component.
- Persisted in Redis.

## 4.3. WebhookSubscription

**Purpose:** Stores the necessary details for managing the active Microsoft Graph webhook subscription, enabling real-time email notifications.

**Key Attributes:**
- `subscription_id`: `string` - Unique identifier provided by Microsoft Graph for the subscription.
- `resource`: `string` - The Microsoft Graph API resource being monitored (e.g., `/me/mailFolders('Inbox')/messages`).
- `expiration_datetime`: `datetime` - The timestamp when the subscription is scheduled to expire.
- `client_state`: `string` - A secret value provided by our application to Microsoft Graph for subscription validation.

**Relationships:**
- Managed by the `core/webhook_service.py` component.
- Persisted in Redis.

---
