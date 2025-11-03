# MS4 Persistence API Contract

## 1. Summary

This document defines the API contract for the MS4 Persistence service, focusing on the batch submission endpoint required for high-throughput data ingestion from the MS1 Email Ingestor service.

**Finding:** As of the latest investigation, no batch submission endpoint exists in the MS4 Persistence service. The existing endpoint at `/metadata` only supports single-item submission. Therefore, this story is **blocked** until the MS4 team implements the proposed batch endpoint defined below.

## 2. Proposed Batch Endpoint

### 2.1. Endpoint

- **Method:** `POST`
- **URL:** `/batch-metadata`

### 2.2. Payload Structure

The endpoint should accept a JSON array of metadata objects. Each object in the array should conform to the structure expected by the existing `/metadata` endpoint.

**Example Payload:**
```json
[
  {
    "invoice_id": "INV-2025-001",
    "vendor_name": "Vendor A",
    "invoice_date": "2025-11-01",
    "total_amount": 1500.00,
    "currency": "USD",
    "line_items": [
      {
        "description": "Item 1",
        "quantity": 2,
        "unit_price": 500.00
      }
    ]
  },
  {
    "invoice_id": "INV-2025-002",
    "vendor_name": "Vendor B",
    "invoice_date": "2025-11-02",
    "total_amount": 300.50,
    "currency": "USD",
    "line_items": []
  }
]
```

### 2.3. Response Codes

- **`202 Accepted`**: The batch has been successfully received and queued for processing. The response body should be empty.
- **`400 Bad Request`**: The request payload is malformed or invalid. The response body should contain a descriptive error message.
- **`401 Unauthorized`**: The request is unauthorized.
- **`429 Too Many Requests`**: The client has exceeded the rate limit. The response should include a `Retry-After` header.
- **`500 Internal Server Error`**: An unexpected error occurred on the server.



### 2.5. Rate Limiting

- **Limit:** 120 requests per minute.
- **Response:** If the limit is exceeded, the API should return a `429 Too Many Requests` status code with a `Retry-After` header indicating when the client can retry.

## 3. Recommended Batch Size

- **Recommended Size:** 50 invoices per batch.

**Justification:** A batch size of 50 provides a good balance between reducing network overhead and avoiding overly large request payloads that could lead to timeouts or increased memory consumption on the server. This size can be tuned based on performance testing once the endpoint is implemented.
