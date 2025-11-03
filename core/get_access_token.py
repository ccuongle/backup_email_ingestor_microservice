import json
import os
import msal 
from msal import ConfidentialClientApplication
from utils.config import CLIENT_ID, CLIENT_SECRET, SCOPES
from cache.redis_manager import get_redis_storage, RedisStorageManager

KEY_REFRESH_TOKEN = RedisStorageManager.KEY_REFRESH_TOKEN

def login_first_time():
    client = ConfidentialClientApplication(
        client_id=CLIENT_ID,
        client_credential=CLIENT_SECRET
    )
    
    print(f"[logging]: Load Client_ID:{CLIENT_ID}, CLIENT_SECRET: {CLIENT_SECRET} successfully")
    
    # Lấy URL để user mở và login
    auth_url = client.get_authorization_request_url(
        scopes=SCOPES,
        redirect_uri="http://localhost:8000/callback"
    )
    print("Follow this link to login:", auth_url)
    
    # Nhập code trả về từ callback URL
    auth_code = input("Paste code from URL callback here: ").strip()
    
    result = client.acquire_token_by_authorization_code(
        code=auth_code,
        scopes=SCOPES,
        redirect_uri="http://localhost:8000/callback"
    )
    
    # Lưu refresh_token vào Redis
    if "refresh_token" in result:
        redis = get_redis_storage()
        redis.redis.set(KEY_REFRESH_TOKEN, result["refresh_token"])
        print("Refresh token saved to Redis")
    else:
        print("Unable to retrieve refresh_token. Response:", result)
    
    return result.get("access_token")

if __name__ == "__main__":
    login_first_time()