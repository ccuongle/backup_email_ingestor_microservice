import webbrowser
import logging
from msal import ConfidentialClientApplication
from typing import Optional, Tuple
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
    logger.info("After successful login, you will be redirected to a blank page (e.g., localhost).")
    logger.info("Copy the ENTIRE address from your browser's address bar.")
    logger.info("It will look like: http://localhost:8000/callback?code=M.R3_BAY.some_long_code...")
    logger.info("="*80)

    auth_code_url = input("Paste the full redirected URL here: ").strip()

    if not auth_code_url:
        logger.error("No authorization URL provided. Authentication cancelled.")
        return None, None

    # Extract the authorization code from the URL
    from urllib.parse import urlparse, parse_qs
    try:
        query_params = parse_qs(urlparse(auth_code_url).query)
        auth_code = query_params.get("code", [None])[0]
    except Exception as e:
        logger.error(f"Could not parse the provided URL: {e}")
        return None, None

    if not auth_code:
        logger.error("Could not find 'code' in the provided URL. Please ensure you paste the full redirected URL.")
        return None, None

    try:
        logger.info("Attempting to acquire token using the authorization code...")
        result = app.acquire_token_by_authorization_code(
            code=auth_code, # Use the extracted code
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI
        )
    except Exception as e:
        logger.error(f"An unexpected error occurred during token acquisition: {e}")
        return None, None

    if "access_token" in result:
        access_token = result["access_token"]
        refresh_token = result.get("refresh_token")
        expires_in = result.get("expires_in", 3600)

        redis_manager = get_redis_storage()
        redis_manager.save_tokens(
            access_token=access_token,
            expires_in=expires_in,
            refresh_token=refresh_token
        )
        
        logger.info("Successfully acquired and stored tokens in Redis.")
        return access_token, refresh_token
    else:
        error = result.get("error")
        error_description = result.get("error_description")
        logger.error(f"Failed to acquire token. Error: {error}. Description: {error_description}")
        return None, None