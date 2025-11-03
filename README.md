# MS1 Email Ingestor

## 1. Overview

`ms1_email_ingestor` is a critical microservice responsible for ingesting invoice-related emails from Microsoft Outlook. It uses a queue-centric architecture with Redis to manage high-volume email ingestion from two sources: a periodic polling service and a real-time webhook. Emails are processed in parallel batches, with invoice metadata being forwarded to the MS4 Persistence service.

This service has been enhanced for high-throughput and resilience, incorporating standardized `httpx` for all HTTP communications, batch processing for MS4 integration, proactive rate limiting, and robust error handling with exponential backoff.

## 2. Documentation

For a comprehensive understanding of the system's architecture, design patterns, technical stack, and detailed component descriptions, please refer to the [Brownfield Architecture Document](docs/brownfield-architecture.md).

## 3. Prerequisites

*   **Python 3.10+**
*   **Redis**: A running Redis instance.
*   **Microsoft Azure AD Application**: A registered application in Azure Active Directory with the following permissions granted:
    *   `Mail.ReadWrite`
    *   `Mail.Send`
    *   `User.Read`
*   **ngrok**: For exposing the local webhook endpoint to the internet during development.

## 3. Setup

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd ms1_email_ingestor
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python -m venv email_env
    source email_env/bin/activate  # On Windows, use `email_env\Scripts\activate`
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Create a `.env` file:**
    Create a `.env` file in the root of the project and add the following environment variables. These are obtained from your Azure AD Application.

    ```
    CLIENT_ID="<your-azure-app-client-id>"
    CLIENT_SECRET="<your-azure-app-client-secret>"

    # Optional: Override default ports and service URLs
    # API_PORT=8000
    # WEBHOOK_PORT=8100
    # REDIS_HOST="localhost"
    # REDIS_PORT=6379
    # MS4_PERSISTENCE_BASE_URL="http://localhost:8002"
    ```

5.  **Perform the first-time login:**
    Run the `get_access_token.py` script to perform the initial OAuth2 authorization flow. This will open a browser window for you to log in and consent to the permissions.

    ```bash
    python core/get_access_token.py
    ```
    Follow the prompts, and paste the callback URL from your browser back into the terminal. This will save a refresh token to your Redis instance, allowing the application to run unattended in the future.

## 4. Running the Service

To run the main application, which includes the API, the polling service, and the webhook service (with ngrok tunneling), execute the `main_orchestrator.py` script:

```bash
python main_orchestrator.py
```

The orchestrator will start all necessary components in the correct order.

## 5. Running Tests

The project includes unit and integration tests. While a specific framework is not enforced, using `pytest` is recommended.

1.  **Install pytest:**
    ```bash
    pip install pytest
    ```

2.  **Run the tests:**
    From the root directory, run:
    ```bash
    pytest
    ```
