# 8. REST API Spec

```yaml
openapi: 3.0.0
info:
  title: MS1 Email Ingestor Control API
  version: 1.0.0
  description: API for managing and monitoring the MS1 Email Ingestor service.
servers:
  - url: http://localhost:8000
    description: Local development server
paths:
  /session/start:
    post:
      summary: Start a new ingestion session
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                polling_mode:
                  type: string
                  enum: [scheduled, manual]
                  default: scheduled
                  description: Mode for polling service.
                polling_interval:
                  type: integer
                  default: 300
                  description: Interval in seconds for scheduled polling.
                enable_webhook:
                  type: boolean
                  default: true
                  description: Enable or disable webhook service.
      responses:
        '200':
          description: Session started successfully
          content:
            application/json:
              schema:
                type: object
                properties:
                  message:
                    type: string
                    example: Session started.
                  session_id:
                    type: string
                    example: abc-123
  /session/stop:
    post:
      summary: Stop the current ingestion session
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                reason:
                  type: string
                  description: Reason for stopping the session.
                  example: user_requested
      responses:
        '200':
          description: Session stopped successfully
          content:
            application/json:
              schema:
                type: object
                properties:
                  message:
                    type: string
                    example: Session stopped.
  /session/status:
    get:
      summary: Get the status of the current ingestion session
      responses:
        '200':
          description: Current session status
          content:
            application/json:
              schema:
                type: object
                properties:
                  session_id:
                    type: string
                    example: abc-123
                  status:
                    type: string
                    example: running
                  emails_processed:
                    type: integer
                    example: 150
                  queue_depth:
                    type: integer
                    example: 25
  /polling/trigger:
    post:
      summary: Manually trigger a one-time poll for unread emails
      responses:
        '200':
          description: Polling triggered
          content:
            application/json:
              schema:
                type: object
                properties:
                  message:
                    type: string
                    example: Manual polling triggered.
  /metrics:
    get:
      summary: Get high-level metrics about the current session
      responses:
        '200':
          description: Session metrics
          content:
            application/json:
              schema:
                type: object
                properties:
                  emails_processed_total:
                    type: integer
                    example: 150
                  emails_failed_total:
                    type: integer
                    example: 2
                  current_queue_size:
                    type: integer
                    example: 25
```

---
