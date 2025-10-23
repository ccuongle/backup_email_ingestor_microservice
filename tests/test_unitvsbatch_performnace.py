"""
Test batch operations performance
"""
import time
from concurrent_storage.redis_manager import get_redis_storage


def test_single_vs_batch():
    """So sánh single vs batch operations"""
    redis = get_redis_storage()
    
    # Generate test email IDs
    email_ids = [f"test_email_{i}" for i in range(1000)]
    
    print("=" * 70)
    print("PERFORMANCE TEST: Single vs Batch Operations")
    print("=" * 70)
    
    # Test 1: Single operations
    print("\n[TEST 1] Single operations (1000 emails)...")
    start = time.time()
    
    for email_id in email_ids:
        redis.is_email_processed(email_id)
    
    single_time = time.time() - start
    print(f"Time: {single_time:.3f}s")
    print(f"Operations/sec: {len(email_ids)/single_time:.0f}")
    
    # Test 2: Batch operations
    print("\n[TEST 2] Batch operations (1000 emails)...")
    start = time.time()
    
    results = redis.batch_check_processed(email_ids)
    
    batch_time = time.time() - start
    print(f"Time: {batch_time:.3f}s")
    print(f"Operations/sec: {len(email_ids)/batch_time:.0f}")
    
    # Comparison
    improvement = ((single_time - batch_time) / single_time) * 100
    speedup = single_time / batch_time
    
    print("\n" + "=" * 70)
    print("RESULTS:")
    print("=" * 70)
    print(f"Single operations : {single_time:.3f}s")
    print(f"Batch operations  : {batch_time:.3f}s")
    print(f"Improvement       : {improvement:.1f}% faster")
    print(f"Speedup           : {speedup:.1f}x")
    print("=" * 70)

if __name__ == "__main__":
    test_single_vs_batch()