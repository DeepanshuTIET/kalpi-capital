"""
Authentication helper utilities for Angel broker.
"""
import os
from datetime import datetime
from database.auth_db import get_auth_token, get_feed_token, store_tokens, clear_tokens
from utils.logging import get_logger

logger = get_logger(__name__)


def auto_authenticate(client_code: str = None, pin: str = None, totp: str = None) -> tuple:
    """
    Automatically authenticate using stored tokens or provided credentials.
    
    Args:
        client_code: Angel client code (optional if tokens are stored)
        pin: Trading PIN (optional if tokens are stored)
        totp: TOTP code (optional if tokens are stored)
        
    Returns:
        tuple: (auth_token, feed_token, error_message)
    """
    # First try to use stored tokens
    # Try with provided client_code first, then default
    stored_auth_token = None
    stored_feed_token = None
    
    if client_code:
        stored_auth_token = get_auth_token(client_code)
        stored_feed_token = get_feed_token(client_code)
    
    # If not found with client_code, try default
    if not (stored_auth_token and stored_feed_token):
        stored_auth_token = get_auth_token('default')
        stored_feed_token = get_feed_token('default')
    
    # If still not found, try to find any stored tokens
    if not (stored_auth_token and stored_feed_token):
        from database.auth_db import _auth_tokens, _feed_tokens
        if _auth_tokens and _feed_tokens:
            # Get the first available token pair
            for user_id in _auth_tokens:
                if user_id in _feed_tokens and _auth_tokens[user_id] and _feed_tokens[user_id]:
                    stored_auth_token = _auth_tokens[user_id]
                    stored_feed_token = _feed_tokens[user_id]
                    logger.info(f"Using stored authentication tokens for user {user_id}")
                    break
    
    if stored_auth_token and stored_feed_token:
        logger.info("Using stored authentication tokens")
        return stored_auth_token, stored_feed_token, None
    
    # If no stored tokens or they're expired, authenticate with credentials
    if not all([client_code, pin, totp]):
        # Try to get from environment as fallback
        client_code = client_code or os.getenv('ANGEL_CLIENT_CODE')
        pin = pin or os.getenv('ANGEL_PIN')
        
        if not all([client_code, pin, totp]):
            error_msg = "No stored tokens found and insufficient credentials provided for authentication"
            # Log as debug instead of error when no credentials provided
            logger.debug(error_msg)
            return None, None, error_msg
    
    # Authenticate with Angel (import here to avoid circular import)
    from broker.angel.api.auth_api import authenticate_broker
    logger.info("Authenticating with Angel broker using provided credentials")
    auth_token, feed_token, error = authenticate_broker(client_code, pin, totp)
    
    if auth_token and feed_token:
        # Store tokens for future use with client code as user ID
        store_tokens(auth_token, feed_token, client_code if client_code else 'default')
        logger.info("Authentication successful and tokens stored")
        return auth_token, feed_token, None
    else:
        logger.error(f"Authentication failed: {error}")
        return None, None, error


def refresh_authentication(client_code: str, pin: str, totp: str) -> tuple:
    """
    Force refresh authentication tokens.
    
    Args:
        client_code: Angel client code
        pin: Trading PIN
        totp: TOTP code
        
    Returns:
        tuple: (auth_token, feed_token, error_message)
    """
    # Clear existing tokens first
    clear_tokens('default')
    
    # Authenticate fresh (import here to avoid circular import)
    from broker.angel.api.auth_api import authenticate_broker
    logger.info("Refreshing authentication tokens")
    auth_token, feed_token, error = authenticate_broker(client_code, pin, totp)
    
    if auth_token and feed_token:
        # Store new tokens
        store_tokens(auth_token, feed_token, client_code)
        logger.info("Authentication refreshed and tokens stored")
        return auth_token, feed_token, None
    else:
        logger.error(f"Authentication refresh failed: {error}")
        return None, None, error


def is_authenticated() -> bool:
    """
    Check if valid authentication tokens are available.
    
    Returns:
        bool: True if valid tokens are available
    """
    auth_token = get_auth_token('default')
    feed_token = get_feed_token('default')
    return bool(auth_token and feed_token)


def get_authentication_status() -> dict:
    """
    Get current authentication status.
    
    Returns:
        dict: Authentication status information
    """
    auth_token = get_auth_token('default')
    feed_token = get_feed_token('default')
    
    return {
        'authenticated': bool(auth_token and feed_token),
        'has_auth_token': bool(auth_token),
        'has_feed_token': bool(feed_token),
        'auth_token_preview': f"{auth_token[:10]}..." if auth_token else None,
        'timestamp': datetime.now().isoformat()
    }
