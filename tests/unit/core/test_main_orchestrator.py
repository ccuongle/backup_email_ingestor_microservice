"""
tests/unit/core/test_main_orchestrator.py - Updated for Story 1.6
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from main_orchestrator import EmailIngestionOrchestrator
from core.session_manager import SessionState

@pytest.fixture
def mock_session_manager():
    with patch('main_orchestrator.session_manager', autospec=True) as mock_sm:
        mock_sm.get_session_status.return_value = {"state": SessionState.TERMINATED.value}
        mock_sm.start_session.return_value = True
        mock_sm.terminate_session = MagicMock()
        mock_sm.recover_from_error.return_value = True  # ✅ NEW: Add recovery mock
        mock_sm.complete_initial_polling.return_value = True
        yield mock_sm

@pytest.fixture
def mock_polling_service():
    with patch('main_orchestrator.polling_service', autospec=True) as mock_ps:
        mock_ps.poll_once = AsyncMock(return_value={"status": "success", "emails_found": 0, "enqueued": 0})
        mock_ps.active = False
        mock_ps.stop = MagicMock()
        yield mock_ps

@pytest.fixture
def mock_webhook_service():
    with patch('main_orchestrator.webhook_service', autospec=True) as mock_ws:
        mock_ws.start = AsyncMock(return_value=True)
        mock_ws.stop = AsyncMock()
        mock_ws.active = False
        yield mock_ws

@pytest.fixture
def mock_batch_processor():
    with patch('main_orchestrator.get_batch_processor', autospec=True) as mock_gbp:
        mock_bp_instance = MagicMock()
        mock_bp_instance.start.return_value = True
        mock_bp_instance.stop = MagicMock()
        mock_bp_instance.active = False
        mock_gbp.return_value = mock_bp_instance
        yield mock_bp_instance

@pytest.fixture
def orchestrator_instance(mock_session_manager, mock_polling_service, mock_webhook_service, mock_batch_processor):
    orchestrator = EmailIngestionOrchestrator()
    return orchestrator

# ✅ UPDATED TEST: FAILED_TO_START triggers recovery, not terminate
@pytest.mark.asyncio
async def test_start_session_with_failed_to_start_state(orchestrator_instance, mock_session_manager):
    """Test that FAILED_TO_START state triggers recovery (Story 1.6)"""
    mock_session_manager.get_session_status.return_value = {
        "state": SessionState.FAILED_TO_START.value,
        "failure_reason": "Previous error"
    }
    
    await orchestrator_instance.start_session()
    
    # ✅ Should call recover_from_error, NOT terminate_session
    mock_session_manager.recover_from_error.assert_called_once_with(reason="orchestrator_startup_recovery")
    mock_session_manager.terminate_session.assert_not_called()  # Should NOT terminate
    mock_session_manager.start_session.assert_called_once()
    assert orchestrator_instance.running is True

# ✅ UPDATED TEST: SESSION_ERROR triggers recovery, not terminate
@pytest.mark.asyncio
async def test_start_session_with_session_error_state(orchestrator_instance, mock_session_manager):
    """Test that SESSION_ERROR state triggers recovery (Story 1.6)"""
    mock_session_manager.get_session_status.return_value = {
        "state": SessionState.SESSION_ERROR.value,
        "error_details": "Runtime error"
    }
    
    await orchestrator_instance.start_session()
    
    # ✅ Should call recover_from_error, NOT terminate_session
    mock_session_manager.recover_from_error.assert_called_once_with(reason="orchestrator_startup_recovery")
    mock_session_manager.terminate_session.assert_not_called()  # Should NOT terminate
    mock_session_manager.start_session.assert_called_once()
    assert orchestrator_instance.running is True

@pytest.mark.asyncio
async def test_start_session_with_terminated_state(orchestrator_instance, mock_session_manager):
    """Test that TERMINATED state allows new session without recovery"""
    mock_session_manager.get_session_status.return_value = {"state": SessionState.TERMINATED.value}
    
    await orchestrator_instance.start_session()
    
    mock_session_manager.terminate_session.assert_not_called()  # Already terminated
    mock_session_manager.recover_from_error.assert_not_called()  # No recovery needed
    mock_session_manager.start_session.assert_called_once()
    assert orchestrator_instance.running is True

@pytest.mark.asyncio
async def test_start_session_with_idle_state(orchestrator_instance, mock_session_manager):
    """Test that IDLE state allows new session without any cleanup"""
    mock_session_manager.get_session_status.return_value = {"state": SessionState.IDLE.value}
    
    await orchestrator_instance.start_session()
    
    mock_session_manager.terminate_session.assert_not_called()
    mock_session_manager.recover_from_error.assert_not_called()
    mock_session_manager.start_session.assert_called_once()
    assert orchestrator_instance.running is True

@pytest.mark.asyncio
async def test_start_session_with_active_state_terminates_old_session(orchestrator_instance, mock_session_manager):
    """Test that active state triggers graceful termination (not recovery)"""
    mock_session_manager.get_session_status.return_value = {"state": SessionState.POLLING_ACTIVE.value}
    
    await orchestrator_instance.start_session()
    
    # ✅ Active states should terminate (with cleanup), not recover
    mock_session_manager.terminate_session.assert_called_once_with(reason="previous_session_cleanup")
    mock_session_manager.recover_from_error.assert_not_called()  # No recovery for active
    mock_session_manager.start_session.assert_called_once()
    assert orchestrator_instance.running is True

# ✅ NEW TEST: Test recovery failure handling
@pytest.mark.asyncio
async def test_start_session_fails_when_recovery_fails(orchestrator_instance, mock_session_manager):
    """Test that session start fails if recovery fails"""
    mock_session_manager.get_session_status.return_value = {
        "state": SessionState.FAILED_TO_START.value
    }
    mock_session_manager.recover_from_error.return_value = False  # Recovery fails
    
    result = await orchestrator_instance.start_session()
    
    assert result is False
    mock_session_manager.recover_from_error.assert_called_once()
    mock_session_manager.start_session.assert_not_called()  # Should not start if recovery failed
    assert orchestrator_instance.running is False