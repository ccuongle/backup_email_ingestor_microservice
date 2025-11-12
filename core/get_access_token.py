import os
import webbrowser
import logging
from msal import ConfidentialClientApplication
from typing import Dict, Optional, Tuple
from utils.config import CLIENT_ID, CLIENT_SECRET, SCOPES, REDIRECT_URI
from cache.redis_manager import get_redis_storage

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def get_ms_graph_tokens_interactively() -> Tuple[Optional[str], Optional[str]]:
    """
    Guides the user through the interactive MS Graph API login process to obtain
    access and refresh tokens. Automatically opens the browser and prompts for
    the authorization code.

    Returns:
        A tuple containing (access_token, refresh_token) or (None, None) if unsuccessful.
    """
    if not all([CLIENT_ID, CLIENT_SECRET, SCOPES, REDIRECT_URI]):
        logger.error("Missing one or more required configuration variables (CLIENT_ID, CLIENT_SECRET, SCOPES, REDIRECT_URI).")
        return None, None

    app = ConfidentialClientApplication(
        client_id=CLIENT_ID,
        client_credential=CLIENT_SECRET
    )
    
    logger.info(f"Loaded Client_ID: {CLIENT_ID}")

    # Get the authorization request URL
    auth_url = app.get_authorization_request_url(
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    
    logger.info("Attempting to open browser for authentication...")
    try:
        browser_opened = webbrowser.open(auth_url)
        if browser_opened:
            logger.info("Browser opened successfully. Please complete the login.")
        else:
            logger.warning("Could not open browser automatically. Please open the following URL in your web browser:")
            logger.warning(auth_url)
    except Exception as e:
        logger.warning(f"Could not open browser automatically: {e}")
        logger.warning(f"Please open the following URL in your web browser:\n{auth_url}")

    logger.info("="*80)
    logger.info("Please complete the login in your browser.")
    logger.info(f"If the browser did not open, please navigate to this URL manually:\n{auth_url}")
    logger.info("After successful login, you will be redirected to a blank page or localhost.")
    logger.info("Read the redirected URI on your browser's address bar (http://localhost:8000/callback?code=M...), copy from `code = ...` and paste it below.")
    logger.info("="*80)

    auth_code_url = input("Paste the authorization code here: ").strip()

    if not auth_code_url:
        logger.error("No authorization code provided. Authentication cancelled.")
        return None, None

    try:
        # MSAL can parse the code from the full redirected URL
        result = app.acquire_token_by_authorization_code(
            code=auth_code_url, # Pass the full URL here
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI
        )
    except Exception as e:
        logger.error(f"Error acquiring token by authorization code: {e}")
        return None, None

    if "access_token" in result:
        access_token = result["access_token"]
        refresh_token = result.get("refresh_token")
        expires_in = result.get("expires_in", 3600) # Default to 1 hour if not provided

        redis_manager = get_redis_storage()
        redis_manager.set_access_token(access_token, expires_in)
        if refresh_token:
            redis_manager.set_refresh_token(refresh_token)
        
        logger.info("Access and Refresh tokens saved to Redis.")
        return access_token, refresh_token
    else:
        logger.error(f"Unable to retrieve tokens. Response: {result.get('error_description', result)}")
        return None, None