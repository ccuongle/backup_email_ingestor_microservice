# 10. Source Tree

```plaintext
ms1_email_ingestor/
├── api/
│   ├── __init__.py
│   ├── ms1_apiHanlder.py       # Control API endpoints (e.g., /session/start, /metrics)
│   └── webhook_app.py          # Webhook Service endpoint for MS Graph notifications
├── concurrent_storage/
│   ├── redis_manager.py        # Centralized Redis interaction logic (queues, session, rate limiting)
│   └── session_manager.py      # Manages ingestion session state (uses redis_manager)
├── core/
│   ├── __init__.py
│   ├── batch_processor.py      # Consumes from Inbound Queue, processes emails, enqueues to MS4 Outbound Queue
│   ├── get_access_token.py     # (Existing)
│   ├── polling_service.py      # Periodically fetches emails from MS Graph
│   ├── queue_manager.py        # (Existing - to be refactored/consolidated with redis_manager)
│   ├── session_manager.py      # (Existing - to be refactored/consolidated with concurrent_storage/session_manager)
│   ├── token_manager.py        # (Existing)
│   ├── unified_email_processor.py # Core logic for processing a single email, prepares MS4 payload
│   ├── webhook_service.py      # Manages MS Graph webhook subscriptions
│   └── ms4_batch_sender.py     # NEW: Consumes from MS4 Outbound Queue, sends batched payloads to MS4
├── docs/
│   ├── prd.md                  # Product Requirements Document
│   ├── architecture.md         # This Architecture Document
│   ├── brownfield-architecture.md # Existing brownfield analysis
│   └── ms4_api_contract.md     # NEW: Details of MS4 batch API (output of PRD Story 3.1)
├── utils/
│   ├── __init__.py
│   ├── config.py               # Centralized application configuration
│   └── token_manager.py        # (Existing - to be refactored/consolidated)
├── main_orchestrator.py        # Main application entry point, orchestrates services
├── requirements.txt            # Project dependencies
├── tests/                      # Unit and integration tests
│   ├── __init__.py
│   ├── intergration_test.py
│   ├── test_unitvsbatch_performnace.py
│   └── test_ms4_batch_sender.py # NEW: Tests specifically for the MS4 Batch Sender component
├── .gitignore                  # Git ignore rules
├── .bmad-core/                 # BMAD Core configuration
├── .gemini/                    # Gemini CLI configuration
├── .git/                       # Git repository data
├── attachments/                # Placeholder for email attachments
├── email_env/                  # Python virtual environment
├── pdfs/                       # Placeholder for generated PDFs
├── storage/                    # General storage (e.g., logs, attachments)
│   ├── attachments/
│   └── logs/
└── web-bundles/                # (Existing - purpose unclear, assumed not directly relevant to this project)
```

---
