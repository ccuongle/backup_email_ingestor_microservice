# 6. External APIs

## 6.1. Microsoft Graph API

*   **Purpose:** Provides access to user mailboxes for email ingestion (polling) and real-time notifications (webhooks).
*   **Documentation:** `https://learn.microsoft.com/en-us/graph/api/overview?view=graph-rest-1.0`
*   **Base URL(s):** `https://graph.microsoft.com/v1.0`
*   **Authentication:** OAuth 2.0 (Client Credentials Flow), managed by the `MSAL` library.
*   **Rate Limits:** Varies by endpoint and tenant. Handled by proactive rate limiting and `Retry-After` header processing (Epic 2).

**Key Endpoints Used:**
- `GET /me/mailFolders/{id}/messages` - Fetches messages from a specified mail folder (Polling Service).
- `POST /subscriptions` - Creates new webhook subscriptions (Webhook Service).
- `PATCH /subscriptions/{id}` - Renews existing webhook subscriptions (Webhook Service).
- `DELETE /subscriptions/{id}` - Deletes webhook subscriptions (Webhook Service).
- `POST /me/messages/{id}/markAsRead` - Marks an email message as read after processing (Batch Processor).

**Integration Notes:** Requires `client_id`, `client_secret`, and `tenant_id` for OAuth configuration.

## 6.2. MS4 Persistence API

*   **Purpose:** Receives processed invoice metadata for long-term storage and further processing by downstream systems.
*   **Documentation:** **[TO BE DEFINED - BLOCKER: PRD Epic 3, Story 3.1]**
*   **Base URL(s):** `http://localhost:8002/metadata` (current single-item endpoint). **Future:** `http://localhost:8002/batch-metadata` (batch endpoint, URL and contract to be defined).
*   **Authentication:** **[TO BE DEFINED - Part of PRD Epic 3, Story 3.1 investigation]**
*   **Rate Limits:** **[TO BE DEFINED - Part of PRD Epic 3, Story 3.1 investigation]**

**Key Endpoints Used:**
- `POST /metadata` - (Current) Sends single invoice metadata.
- `POST /batch-metadata` - (Future) Sends aggregated invoice metadata in batches (details to be defined in PRD Epic 3, Story 3.1).

**Integration Notes:** The exact contract for the batch endpoint, including its URL, payload structure, authentication, and rate limits, is a **critical blocker** that needs to be investigated as per PRD Epic 3, Story 3.1.

---
