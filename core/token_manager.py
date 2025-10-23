import os
import msal
from dotenv import load_dotenv
import requests, datetime, json
from datetime import datetime, timedelta, UTC
from msal import ConfidentialClientApplication
from concurrent_storage.redis_manager import get_redis_storage, RedisStorageManager

load_dotenv()

KEY_REFRESH_TOKEN = RedisStorageManager.KEY_REFRESH_TOKEN
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
SCOPES = ["Mail.ReadWrite"]

def get_token():
    client = ConfidentialClientApplication(
        client_id=CLIENT_ID,
        client_credential=CLIENT_SECRET
    )
    
    redis = get_redis_storage()
    refresh_token = redis.redis.get(KEY_REFRESH_TOKEN)
    
    if not refresh_token:
        raise Exception("⚠ refresh_token not found. Please run get_access_token first.")
    
    # Lấy access_token mới
    result = client.acquire_token_by_refresh_token(refresh_token, SCOPES)
    
    if "access_token" not in result:
        raise Exception(f"⚠ Refreshing token error: {result}")
    
    access_token = result["access_token"]
    return access_token