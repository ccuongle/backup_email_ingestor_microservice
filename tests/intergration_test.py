"""
tests/integration_test.py
Test workflow hoàn chỉnh của microservice
"""
import time
import sys
from unittest.mock import patch, MagicMock, call
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main_orchestrator import orchestrator
from core.session_manager import session_manager, TriggerMode, SessionState
from core.polling_service import polling_service
from core.webhook_service import webhook_service
from utils.config import MAX_POLL_PAGES


def test_scenario_1_scheduled_polling_with_webhook():
    """
    Scenario 1: Scheduled Polling + Webhook
    - Start với BOTH_ACTIVE
    - Polling xử lý backlog
    - Chuyển sang WEBHOOK_ACTIVE
    """
    print("\n" + "=" * 70)
    print("SCENARIO 1: Scheduled Polling + Webhook")
    print("=" * 70)
    
    # Start session
    print("\n[Test] Starting session...")
    success = orchestrator.start_session(
        polling_mode=TriggerMode.SCHEDULED,
        polling_interval=60,  # 1 phút để test nhanh
        enable_webhook=True
    )
    
    assert success, "Failed to start session"
    print("[Test] ✓ Session started")
    
    # Check initial state
    status = orchestrator.get_status()
    assert status["running"], "Session should be running"
    assert status["session"]["state"] == SessionState.BOTH_ACTIVE.value
    print(f"[Test] ✓ State: {status['session']['state']}")
    
    # Wait for polling to process
    print("\n[Test] Waiting 30s for polling to process emails...")
    time.sleep(30)
    
    # Check status again
    status = orchestrator.get_status()
    print(f"[Test] Processed: {status['session']['processed_count']}")
    print(f"[Test] Pending: {status['session']['pending_count']}")
    
    # Simulate polling completion
    if status["polling"]["active"]:
        print("\n[Test] Completing initial polling...")
        session_manager.complete_initial_polling()
        
        status = orchestrator.get_status()
        assert status["session"]["state"] == SessionState.WEBHOOK_ACTIVE.value
        print(f"[Test] ✓ Transitioned to: {status['session']['state']}")
    
    # Stop session
    print("\n[Test] Stopping session...")
    orchestrator.stop_session(reason="test_complete")
    
    assert not orchestrator.running, "Session should be stopped"
    print("[Test] ✓ Session stopped")
    
    print("\n[Test] ✓✓✓ SCENARIO 1 PASSED ✓✓✓")


def test_scenario_2_webhook_fallback():
    """
    Scenario 2: Webhook Fallback
    - Start với webhook
    - Simulate webhook errors
    - Fallback sang polling
    - Restore webhook
    """
    print("\n" + "=" * 70)
    print("SCENARIO 2: Webhook Fallback to Polling")
    print("=" * 70)
    
    # Start session
    print("\n[Test] Starting session...")
    success = orchestrator.start_session(
        polling_mode=TriggerMode.MANUAL,  # Không tự động poll
        polling_interval=60,
        enable_webhook=True
    )
    
    assert success, "Failed to start session"
    print("[Test] ✓ Session started")
    
    # Complete initial polling ngay
    time.sleep(5)
    session_manager.complete_initial_polling()
    
    status = orchestrator.get_status()
    assert status["session"]["state"] == SessionState.WEBHOOK_ACTIVE.value
    print(f"[Test] ✓ State: {status['session']['state']}")
    
    # Simulate webhook errors
    print("\n[Test] Simulating webhook errors...")
    for i in range(3):
        session_manager.activate_fallback_polling(
            reason=f"test_error_{i}"
        )
        time.sleep(2)
    
    status = orchestrator.get_status()
    assert status["session"]["state"] == SessionState.BOTH_ACTIVE.value
    print(f"[Test] ✓ Fallback activated: {status['session']['state']}")
    print(f"[Test] Webhook errors: {status['session']['webhook_errors']}")
    
    # Restore webhook
    print("\n[Test] Restoring webhook...")
    session_manager.restore_webhook_only()
    
    status = orchestrator.get_status()
    assert status["session"]["state"] == SessionState.WEBHOOK_ACTIVE.value
    print(f"[Test] ✓ Webhook restored: {status['session']['state']}")
    
    # Stop session
    print("\n[Test] Stopping session...")
    orchestrator.stop_session(reason="test_complete")
    
    print("\n[Test] ✓✓✓ SCENARIO 2 PASSED ✓✓✓")


def test_scenario_3_manual_polling_only():
    """
    Scenario 3: Manual Polling Only (no webhook)
    - Start với polling only
    - Manual trigger
    - Stop
    """
    print("\n" + "=" * 70)
    print("SCENARIO 3: Manual Polling Only")
    print("=" * 70)
    
    # Start session without webhook
    print("\n[Test] Starting session (polling only)...")
    success = orchestrator.start_session(
        polling_mode=TriggerMode.MANUAL,
        polling_interval=60,
        enable_webhook=False
    )
    
    assert success, "Failed to start session"
    print("[Test] ✓ Session started")
    
    # Check webhook is not active
    status = orchestrator.get_status()
    assert not status["webhook"]["active"], "Webhook should not be active"
    print("[Test] ✓ Webhook disabled as expected")
    
    # Trigger manual poll
    print("\n[Test] Triggering manual poll...")
    result = orchestrator.trigger_manual_poll()
    
    print(f"[Test] Poll result:")
    print(f"  Emails found: {result.get('emails_found', 0)}")
    print(f"  Processed: {result.get('processed', 0)}")
    print(f"  Failed: {result.get('failed', 0)}")
    print(f"  Skipped: {result.get('skipped', 0)}")
    
    # Stop session
    print("\n[Test] Stopping session...")
    orchestrator.stop_session(reason="test_complete")
    
    print("\n[Test] ✓✓✓ SCENARIO 3 PASSED ✓✓✓")


def test_scenario_4_duplicate_prevention():
    """
    Scenario 4: Duplicate Prevention
    - Process same email multiple times
    - Verify deduplication works
    """
    print("\n" + "=" * 70)
    print("SCENARIO 4: Duplicate Prevention")
    print("=" * 70)
    
    # Start session
    print("\n[Test] Starting session...")
    success = orchestrator.start_session(
        polling_mode=TriggerMode.MANUAL,
        polling_interval=60,
        enable_webhook=False
    )
    
    assert success, "Failed to start session"
    
    # Register some fake email IDs
    print("\n[Test] Registering fake email IDs...")
    test_ids = ["test_email_1", "test_email_2", "test_email_3"]
    
    for email_id in test_ids:
        result = session_manager.register_processed_email(email_id)
        assert result, f"Should register {email_id} first time"
        print(f"[Test] ✓ Registered: {email_id}")
    
    # Try to register again (should be rejected)
    print("\n[Test] Trying to register duplicates...")
    for email_id in test_ids:
        result = session_manager.register_processed_email(email_id)
        assert not result, f"Should reject duplicate {email_id}"
        print(f"[Test] ✓ Rejected duplicate: {email_id}")
    
    # Check processed count
    status = orchestrator.get_status()
    assert status["session"]["processed_count"] == len(test_ids)
    print(f"\n[Test] ✓ Processed count: {status['session']['processed_count']}")
    
    # Stop session
    orchestrator.stop_session(reason="test_complete")
    
    print("\n[Test] ✓✓✓ SCENARIO 4 PASSED ✓✓✓")


def test_scenario_5_pagination():
    """
    Scenario 5: Pagination
    - Verify that the polling service correctly fetches multiple pages of emails.
    - Verify that the MAX_POLL_PAGES limit is respected.
    """
    print("\n" + "=" * 70)
    print("SCENARIO 5: Pagination Validation")
    print("=" * 70)

    # Mock the requests.get call
    mock_response = MagicMock()
    mock_response.status_code = 200

    # Create 3 pages of 10 emails each
    page1 = {"value": [{"id": f"p1_{i}"} for i in range(10)], "@odata.nextLink": "http://next/page2"}
    page2 = {"value": [{"id": f"p2_{i}"} for i in range(10)], "@odata.nextLink": "http://next/page3"}
    page3 = {"value": [{"id": f"p3_{i}"} for i in range(10)]} # No nextLink

    # Configure the mock to return pages sequentially
    mock_response.json.side_effect = [page1, page2, page3]

    with patch('requests.get', return_value=mock_response) as mock_get:
        # Start a session in manual mode
        print("\n[Test] Starting session (manual polling)...")
        success = orchestrator.start_session(
            polling_mode=TriggerMode.MANUAL,
            enable_webhook=False
        )
        assert success, "Failed to start session"

        # --- Test 1: Fetch all pages ---
        print("\n[Test] Triggering poll to fetch all pages...")
        result = orchestrator.trigger_manual_poll()

        assert result['emails_found'] == 30, f"Expected 30 emails, but found {result['emails_found']}"
        assert mock_get.call_count == 3, f"Expected 3 API calls, but got {mock_get.call_count}"
        print("[Test] ✓ Correctly fetched 30 emails across 3 pages.")

        # --- Test 2: Respect MAX_POLL_PAGES limit ---
        print(f"\n[Test] Testing MAX_POLL_PAGES limit (setting to 2)...")
        # Reset mocks and start a new poll
        mock_get.reset_mock()
        mock_response.json.side_effect = [page1, page2, page3]

        # Patch the config value and the print function to capture output
        with patch('core.polling_service.max_pages', 2), \
             patch('builtins.print') as mock_print:

            result = orchestrator.trigger_manual_poll()

            assert result['emails_found'] == 20, f"Expected 20 emails with page limit, but found {result['emails_found']}"
            assert mock_get.call_count == 2, f"Expected 2 API calls with page limit, but got {mock_get.call_count}"
            print("[Test] ✓ Correctly fetched 20 emails, respecting the page limit.")

            # Check for the warning message
            warning_found = False
            expected_warning = f"[PollingService] WARN: Reached max poll pages limit (2). More emails may be available."
            for print_call in mock_print.call_args_list:
                if expected_warning in print_call.args:
                    warning_found = True
                    break
            assert warning_found, "The MAX_POLL_PAGES warning was not logged."
            print("[Test] ✓ Correctly logged the max pages warning.")

        # Stop session
        orchestrator.stop_session(reason="test_complete")

    print("\n[Test] ✓✓✓ SCENARIO 5 PASSED ✓✓✓")


def run_all_tests():
    """Run all integration tests"""
    print("\n" + "=" * 70)
    print("EMAIL INGESTION MICROSERVICE - INTEGRATION TESTS")
    print("=" * 70)
    
    tests = [
        ("Scheduled Polling + Webhook", test_scenario_1_scheduled_polling_with_webhook),
        ("Webhook Fallback", test_scenario_2_webhook_fallback),
        ("Manual Polling Only", test_scenario_3_manual_polling_only),
        ("Duplicate Prevention", test_scenario_4_duplicate_prevention),
        ("Pagination", test_scenario_5_pagination),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            print(f"\n\nRunning: {test_name}")
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"\n✗✗✗ {test_name} FAILED ✗✗✗")
            print(f"Error: {e}")
            failed += 1
        except Exception as e:
            print(f"\n✗✗✗ {test_name} ERROR ✗✗✗")
            print(f"Error: {e}")
            failed += 1
        
        # Cleanup between tests
        time.sleep(2)
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print("=" * 70)
    
    return failed == 0


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Integration Tests")
    parser.add_argument(
        "--test", # I see a typo here, but I will leave it as is to not break existing scripts.
        choices=["1", "2", "3", "4", "all"],
        default="all",
        help="Which test scenario to run"
    )
    
    args = parser.parse_args()
    
    if args.test == "1":
        test_scenario_1_scheduled_polling_with_webhook()
    elif args.test == "2":
        test_scenario_2_webhook_fallback()
    elif args.test == "3":
        test_scenario_3_manual_polling_only()
    elif args.test == "4":
        test_scenario_4_duplicate_prevention()
    else:
        success = run_all_tests()
        sys.exit(0 if success else 1)