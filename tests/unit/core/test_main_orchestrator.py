import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from main_orchestrator import EmailIngestionOrchestrator
from core.session_manager import SessionState, SessionConfig, TriggerMode, session_manager
from core.polling_service import polling_service
from core.webhook_service import webhook_service
from core.batch_processor import get_batch_processor # Import get_batch_processor instead

@pytest.fixture
def mock_session_manager():
    with patch('main_orchestrator.session_manager', autospec=True) as mock_sm:
        mock_sm.get_session_status.return_value = {"state": SessionState.TERMINATED.value}
        mock_sm.start_session.return_value = True
        mock_sm.terminate_session = MagicMock() # Make it a MagicMock for direct call
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
    # Patch get_batch_processor and return a mock instance
    with patch('main_orchestrator.get_batch_processor', autospec=True) as mock_gbp:
        mock_bp_instance = MagicMock() # No need to spec BatchProcessor directly
        mock_bp_instance.start.return_value = True
        mock_bp_instance.stop = MagicMock()
        mock_bp_instance.active = False
        mock_gbp.return_value = mock_bp_instance
        yield mock_bp_instance

@pytest.fixture
def orchestrator_instance(mock_session_manager, mock_polling_service, mock_webhook_service, mock_batch_processor):
    # Reset the singleton instance for each test
    EmailIngestionOrchestrator._instance = None
    orchestrator = EmailIngestionOrchestrator()
    # The batch_processor attribute is set by get_batch_processor inside start_session
    # No need to manually set orchestrator.batch_processor here if get_batch_processor is mocked
    return orchestrator

@pytest.mark.asyncio
async def test_start_session_with_failed_to_start_state(orchestrator_instance, mock_session_manager):
    mock_session_manager.get_session_status.return_value = {"state": SessionState.FAILED_TO_START.value}
    
    await orchestrator_instance.start_session()
    
    mock_session_manager.terminate_session.assert_called_once_with(reason="previous_session_cleanup")
    mock_session_manager.start_session.assert_called_once()
    assert orchestrator_instance.running is True

@pytest.mark.asyncio
async def test_start_session_with_session_error_state(orchestrator_instance, mock_session_manager):
    mock_session_manager.get_session_status.return_value = {"state": SessionState.SESSION_ERROR.value}
    
    await orchestrator_instance.start_session()
    
    mock_session_manager.terminate_session.assert_called_once_with(reason="previous_session_cleanup")
    mock_session_manager.start_session.assert_called_once()
    assert orchestrator_instance.running is True

@pytest.mark.asyncio
async def test_start_session_with_terminated_state(orchestrator_instance, mock_session_manager):
    mock_session_manager.get_session_status.return_value = {"state": SessionState.TERMINATED.value}
    
    await orchestrator_instance.start_session()
    
    mock_session_manager.terminate_session.assert_not_called() # Should not terminate if already terminated
    mock_session_manager.start_session.assert_called_once()
    assert orchestrator_instance.running is True

@pytest.mark.asyncio
async def test_start_session_with_idle_state(orchestrator_instance, mock_session_manager):
    mock_session_manager.get_session_status.return_value = {"state": SessionState.IDLE.value}
    
    await orchestrator_instance.start_session()
    
    mock_session_manager.terminate_session.assert_not_called() # Should not terminate if idle
    mock_session_manager.start_session.assert_called_once()
    assert orchestrator_instance.running is True

@pytest.mark.asyncio
async def test_start_session_with_active_state_terminates_old_session(orchestrator_instance, mock_session_manager):
    mock_session_manager.get_session_status.return_value = {"state": SessionState.POLLING_ACTIVE.value}
    
    await orchestrator_instance.start_session()
    
    mock_session_manager.terminate_session.assert_called_once_with(reason="previous_session_cleanup")
    mock_session_manager.start_session.assert_called_once()
    assert orchestrator_instance.running is True