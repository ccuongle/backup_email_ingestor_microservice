import pytest
from core.session_manager import SessionState

def test_session_state_enum_has_failed_to_start():
    """Verify SessionState enum includes FAILED_TO_START."""
    assert SessionState.FAILED_TO_START.value == "failed_to_start"

def test_session_state_enum_has_session_error():
    """Verify SessionState enum includes SESSION_ERROR."""
    assert SessionState.SESSION_ERROR.value == "session_error"

def test_session_state_enum_values():
    """Verify all expected SessionState enum values."""
    expected_states = {
        "idle",
        "polling_active",
        "webhook_active",
        "both_active",
        "terminated",
        "failed_to_start",
        "session_error",
        "error",
    }
    actual_states = {state.value for state in SessionState}
    assert actual_states == expected_states
