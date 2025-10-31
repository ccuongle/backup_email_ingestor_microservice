# 3. Tech Stack

## 3.1. Cloud Infrastructure

*   **Provider:** AWS
*   **Key Services:**
    *   **Current Local:** Redis (for queuing, caching, session management)
    *   **Future AWS Equivalent:** AWS ElastiCache for Redis (for managed, scalable Redis service)
*   **Deployment Regions:** N/A for local development. For future AWS deployment, standard regions (e.g., `us-east-1`, `eu-west-1`) would be considered based on latency and compliance needs.

## 3.2. Technology Stack Table

| Category | Technology | Version | Purpose | Rationale |
| :--- | :--- | :--- | :--- | :--- |
| **Language** | Python | 3.x (Latest stable) | Primary development language | Existing codebase, strong ecosystem for data processing, team familiarity. |
| **Web Framework** | FastAPI | (Latest stable) | API endpoints for webhooks and control | Existing codebase, high performance, async-native, robust API development. |
| **HTTP Client** | `httpx` | (Latest stable) | All outbound HTTP requests | Standardized client (as per PRD NFR2), async support, connection pooling (as per PRD NFR3). |
| **Queue/Cache** | Redis | (Latest stable) | Inbound/Outbound queues, session management, rate limiting | Existing codebase, high performance, versatile data structures, critical for resilience and throughput. |
| **Auth Library** | `MSAL` | (Latest stable) | Microsoft Graph API authentication | Existing codebase, robust Microsoft identity integration. |
| **Deployment** | Direct Python Execution | N/A | Application execution | Existing deployment method, with codebase structured for future containerization (e.g., Docker) and deployment to AWS services (e.g., EC2, ECS, Lambda). |

---
