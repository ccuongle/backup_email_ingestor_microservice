"""
api_service.py
HTTP API điều khiển Email Ingestion Microservice
Chạy trên port riêng (8000) - không conflict với webhook (8100)
"""
from fastapi import FastAPI, HTTPException, Response, status
from pydantic import BaseModel
from typing import Optional
from enum import Enum
from main_orchestrator import orchestrator
from core.session_manager import TriggerMode
from concurrent_storage.redis_manager import get_redis_storage

app = FastAPI(
    title="Email Ingestion Control API",
    description="API điều khiển email ingestion microservice",
    version="1.0.0"
)

class PollingModeEnum(str, Enum):
    manual = "manual"
    scheduled = "scheduled"

class StartSessionRequest(BaseModel):
    """Request để start session"""
    polling_mode: PollingModeEnum = PollingModeEnum.scheduled
    polling_interval: int = 300
    enable_webhook: bool = True

class StopSessionRequest(BaseModel):
    """Request để stop session"""
    reason: Optional[str] = "user_requested"

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Email Ingestion Microservice",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health")
async def health_check(response: Response):
    """Health check"""
    redis_manager = get_redis_storage()
    if await redis_manager.check_redis_connection():
        return {"status": "healthy"}
    else:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unhealthy", "dependencies": {"redis": "unhealthy"}}

@app.post("/session/start")
async def start_session(request: StartSessionRequest):
    """
    Khởi động phiên làm việc mới
    """
    try:
        mode = TriggerMode.MANUAL if request.polling_mode == "manual" else TriggerMode.SCHEDULED
        
        success = orchestrator.start_session(
            polling_mode=mode,
            polling_interval=request.polling_interval,
            enable_webhook=request.enable_webhook
        )
        
        if not success:
            raise HTTPException(
                status_code=400,
                detail="Failed to start session. Check if session is already running."
            )
        
        status = orchestrator.get_status()
        return {
            "success": True,
            "message": "Session started successfully",
            "session_id": status["session"]["session_id"],
            "status": status
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/session/stop")
async def stop_session(request: StopSessionRequest):
    """
    Dừng phiên làm việc hiện tại
    """
    try:
        if not orchestrator.running:
            raise HTTPException(status_code=400, detail="No active session")
        
        orchestrator.stop_session(reason=request.reason)
        return {
            "success": True,
            "message": "Session stopped successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/session/status")
async def get_session_status():
    """
    Lấy trạng thái phiên làm việc hiện tại
    """
    try:
        status = orchestrator.get_status()
        return status
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/polling/trigger")
async def trigger_manual_poll():
    """
    Trigger một lần polling thủ công
    """
    try:
        if not orchestrator.running:
            raise HTTPException(
                status_code=400,
                detail="No active session. Start a session first."
            )
        
        result = orchestrator.trigger_manual_poll()
        
        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("error"))
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/metrics")
async def get_metrics():
    """
    Lấy metrics tổng quan
    """
    redis_manager = get_redis_storage()
    processed = await redis_manager.get_total_emails_processed()
    failed = await redis_manager.get_total_emails_failed()
    queue_size = await redis_manager.get_inbound_queue_size()
    return {
        "emails_processed": processed,
        "emails_failed": failed,
        "current_queue_size": queue_size
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)