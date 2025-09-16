"""
Authentication database functions for Angel broker integration.
Persistent storage implementation for the real-time price system.
"""
import os
import json
from datetime import datetime, timedelta
from utils.logging import get_logger

logger = get_logger(__name__)

# File-based storage for authentication tokens
TOKEN_FILE = 'angel_tokens.json'

# In-memory cache for performance
_auth_tokens = {}
_feed_tokens = {}
_token_expiry = {}  # Track token expiry times

def _load_tokens():
    """Load tokens from file storage"""
    global _auth_tokens, _feed_tokens, _token_expiry
    
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, 'r') as f:
                data = json.load(f)
                _auth_tokens = data.get('auth_tokens', {})
                _feed_tokens = data.get('feed_tokens', {})
                _token_expiry = data.get('token_expiry', {})
                
                # Clean up expired tokens
                current_time = datetime.now()
                expired_users = []
                for user_id, expiry_str in _token_expiry.items():
                    if datetime.fromisoformat(expiry_str) < current_time:
                        expired_users.append(user_id)
                
                for user_id in expired_users:
                    _auth_tokens.pop(user_id, None)
                    _feed_tokens.pop(user_id, None)
                    _token_expiry.pop(user_id, None)
                    logger.info(f"Expired tokens cleaned for user {user_id}")
                    
        except Exception as e:
            logger.error(f"Error loading tokens: {e}")
            _auth_tokens = {}
            _feed_tokens = {}
            _token_expiry = {}

def _save_tokens():
    """Save tokens to file storage"""
    try:
        data = {
            'auth_tokens': _auth_tokens,
            'feed_tokens': _feed_tokens,
            'token_expiry': _token_expiry
        }
        with open(TOKEN_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving tokens: {e}")

def get_auth_token(user_id: str = None) -> str:
    """
    Get authentication token for user
    
    Args:
        user_id: User identifier (optional, defaults to 'default')
        
    Returns:
        str: Authentication token or None
    """
    if user_id is None:
        user_id = 'default'
    
    # Load tokens from file if not in memory
    if not _auth_tokens:
        _load_tokens()
    
    return _auth_tokens.get(user_id)

def store_auth_token(user_id: str, auth_token: str, expires_hours: int = 24):
    """
    Store authentication token for user
    
    Args:
        user_id: User identifier
        auth_token: Authentication token
        expires_hours: Token expiry in hours (default 24)
    """
    _auth_tokens[user_id] = auth_token
    _token_expiry[user_id] = (datetime.now() + timedelta(hours=expires_hours)).isoformat()
    _save_tokens()
    logger.info(f"Stored auth token for user {user_id} (expires in {expires_hours} hours)")

def get_feed_token(user_id: str = None) -> str:
    """
    Get feed token for user
    
    Args:
        user_id: User identifier (optional, defaults to 'default')
        
    Returns:
        str: Feed token or None
    """
    if user_id is None:
        user_id = 'default'
    
    # Load tokens from file if not in memory
    if not _feed_tokens:
        _load_tokens()
    
    return _feed_tokens.get(user_id)

def store_feed_token(user_id: str, feed_token: str):
    """
    Store feed token for user
    
    Args:
        user_id: User identifier
        feed_token: Feed token
    """
    _feed_tokens[user_id] = feed_token
    _save_tokens()
    logger.info(f"Stored feed token for user {user_id}")

def clear_tokens(user_id: str):
    """
    Clear all tokens for user
    
    Args:
        user_id: User identifier
    """
    _auth_tokens.pop(user_id, None)
    _feed_tokens.pop(user_id, None)
    _token_expiry.pop(user_id, None)
    _save_tokens()
    logger.info(f"Cleared tokens for user {user_id}")

def get_stored_auth_token() -> str:
    """
    Get stored authentication token for default user (backward compatibility)
    
    Returns:
        str: Authentication token or None
    """
    return get_auth_token('default')

def store_tokens(auth_token: str, feed_token: str, user_id: str = 'default'):
    """
    Store both auth and feed tokens for a user
    
    Args:
        auth_token: Authentication token
        feed_token: Feed token
        user_id: User identifier (defaults to 'default')
    """
    store_auth_token(user_id, auth_token)
    store_feed_token(user_id, feed_token)
    logger.info(f"Stored both tokens for user {user_id}")

# Load tokens on module import
_load_tokens()
