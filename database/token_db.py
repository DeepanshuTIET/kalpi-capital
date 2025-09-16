"""
Token database functions for Angel broker integration.
Simplified mock implementation for the real-time price system.
"""
from cachetools import TTLCache
from utils.logging import get_logger

logger = get_logger(__name__)

# Define a cache for the tokens, symbols with a max size and a 3600-second TTL
token_cache = TTLCache(maxsize=1024, ttl=3600)

# Mock token data for testing - in production this would come from a proper database
_mock_tokens = {
    ("RELIANCE", "NSE"): {"token": "2885", "brsymbol": "RELIANCE", "brexchange": "NSE"},
    ("TCS", "NSE"): {"token": "11536", "brsymbol": "TCS", "brexchange": "NSE"},
    ("INFY", "NSE"): {"token": "9220", "brsymbol": "INFY", "brexchange": "NSE"},
    ("ICICIBANK", "NSE"): {"token": "4963", "brsymbol": "ICICIBANK", "brexchange": "NSE"},
    ("SBIN", "NSE"): {"token": "3045", "brsymbol": "SBIN", "brexchange": "NSE"},
    ("NIFTY", "NSE_INDEX"): {"token": "99926000", "brsymbol": "NIFTY 50", "brexchange": "NSE"},
    ("SENSEX", "BSE_INDEX"): {"token": "1", "brsymbol": "SENSEX", "brexchange": "BSE"},
}

def get_token(symbol, exchange):
    """
    Retrieves a token for a given symbol and exchange, utilizing a cache to improve performance.
    """
    cache_key = f"{symbol}-{exchange}"
    # Attempt to retrieve from cache
    if cache_key in token_cache:
        return token_cache[cache_key]
    else:
        # Query mock database if not in cache
        token = get_token_dbquery(symbol, exchange)
        # Cache the result for future requests
        if token is not None:
            token_cache[cache_key] = token
        return token

def get_token_dbquery(symbol, exchange):
    """
    Queries the mock database for a token by symbol and exchange.
    """
    try:
        mock_data = _mock_tokens.get((symbol, exchange))
        if mock_data:
            return mock_data["token"]
        else:
            logger.warning(f"Token not found for {symbol}.{exchange}")
            return None
    except Exception as e:
        logger.error(f"Error while querying the database: {e}")
        return None

def get_symbol(token, exchange):
    """
    Retrieves a symbol for a given token and exchange, utilizing a cache to improve performance.
    """
    cache_key = f"{token}-{exchange}"
    # Attempt to retrieve from cache
    if cache_key in token_cache:
        return token_cache[cache_key]
    else:
        # Query database if not in cache
        symbol = get_symbol_dbquery(token, exchange)
        # Cache the result for future requests
        if symbol is not None:
            token_cache[cache_key] = symbol
        return symbol

def get_symbol_dbquery(token, exchange):
    """
    Queries the mock database for a symbol by token and exchange.
    """
    try:
        for (symbol, exch), data in _mock_tokens.items():
            if data["token"] == token and (exch == exchange or data["brexchange"] == exchange):
                return symbol
        logger.warning(f"Symbol not found for token {token}.{exchange}")
        return None
    except Exception as e:
        logger.error(f"Error while querying the database: {e}")
        return None

def get_oa_symbol(symbol, exchange):
    """
    Retrieves a symbol for a given token and exchange, utilizing a cache to improve performance.
    """
    cache_key = f"oa{symbol}-{exchange}"
    # Attempt to retrieve from cache
    if cache_key in token_cache:
        return token_cache[cache_key]
    else:
        # Query database if not in cache
        oasymbol = get_oa_symbol_dbquery(symbol, exchange)
        # Cache the result for future requests
        if oasymbol is not None:
            token_cache[cache_key] = oasymbol
        return oasymbol

def get_oa_symbol_dbquery(symbol, exchange):
    """
    Queries the mock database for a symbol by token and exchange.
    """
    try:
        # For mock implementation, just return the symbol
        return symbol
    except Exception as e:
        logger.error(f"Error while querying the database: {e}")
        return None

def get_symbol_count():
    """
    Get the total count of symbols in the database.
    """
    try:
        return len(_mock_tokens)
    except Exception as e:
        logger.error(f"Error while counting symbols: {e}")
        return 0

def get_br_symbol(symbol, exchange):
    """
    Retrieves a broker symbol for a given symbol and exchange, utilizing a cache to improve performance.
    """
    cache_key = f"br{symbol}-{exchange}"
    # Attempt to retrieve from cache
    if cache_key in token_cache:
        return token_cache[cache_key]
    else:
        # Query database if not in cache
        brsymbol = get_br_symbol_dbquery(symbol, exchange)
        # Cache the result for future requests
        if brsymbol is not None:
            token_cache[cache_key] = brsymbol
        return brsymbol

def get_br_symbol_dbquery(symbol, exchange):
    """
    Queries the mock database for a broker symbol by symbol and exchange.
    """
    try:
        mock_data = _mock_tokens.get((symbol, exchange))
        if mock_data:
            return mock_data["brsymbol"]
        else:
            logger.warning(f"Broker symbol not found for {symbol}.{exchange}")
            return symbol  # Fallback to original symbol
    except Exception as e:
        logger.error(f"Error while querying the database: {e}")
        return symbol

def get_brexchange(symbol, exchange):
    """
    Retrieves the broker exchange for a given symbol and exchange, utilizing a cache to improve performance.
    """
    cache_key = f"brex-{symbol}-{exchange}"
    # Attempt to retrieve from cache
    if cache_key in token_cache:
        return token_cache[cache_key]
    else:
        # Query database if not in cache
        brexchange = get_brexchange_dbquery(symbol, exchange)
        # Cache the result for future requests
        if brexchange is not None:
            token_cache[cache_key] = brexchange
        return brexchange

def get_brexchange_dbquery(symbol, exchange):
    """
    Queries the mock database for a broker exchange by symbol and exchange.
    """
    try:
        mock_data = _mock_tokens.get((symbol, exchange))
        if mock_data:
            return mock_data["brexchange"]
        else:
            logger.warning(f"Broker exchange not found for {symbol}.{exchange}")
            return exchange  # Fallback to original exchange
    except Exception as e:
        logger.error(f"Error while querying the database: {e}")
        return exchange

def add_mock_token(symbol: str, exchange: str, token: str, brsymbol: str = None, brexchange: str = None):
    """
    Add a mock token for testing purposes
    
    Args:
        symbol: Trading symbol
        exchange: Exchange code  
        token: Token ID
        brsymbol: Broker symbol (defaults to symbol)
        brexchange: Broker exchange (defaults to exchange)
    """
    _mock_tokens[(symbol, exchange)] = {
        "token": token,
        "brsymbol": brsymbol or symbol,
        "brexchange": brexchange or exchange
    }
    logger.info(f"Added mock token for {symbol}.{exchange}: {token}")
