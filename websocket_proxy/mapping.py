"""
Symbol mapping utilities for broker integrations.
Simplified implementation for the real-time price system.
"""
from typing import Dict, Optional
from database.token_db import get_token, get_br_symbol, get_brexchange
from utils.logging import get_logger

logger = get_logger(__name__)


class SymbolMapper:
    """Maps symbols between different broker formats"""
    
    @staticmethod
    def get_token_from_symbol(symbol: str, exchange: str) -> Optional[Dict[str, str]]:
        """
        Get token information for a symbol and exchange
        
        Args:
            symbol: Trading symbol
            exchange: Exchange code
            
        Returns:
            Dict with token info or None if not found
        """
        try:
            token = get_token(symbol, exchange)
            br_symbol = get_br_symbol(symbol, exchange)
            br_exchange = get_brexchange(symbol, exchange)
            
            if token:
                return {
                    'token': token,
                    'symbol': symbol,
                    'exchange': exchange,
                    'brsymbol': br_symbol or symbol,
                    'brexchange': br_exchange or exchange
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error mapping symbol {symbol}.{exchange}: {e}")
            return None
    
    @staticmethod
    def get_symbol_from_token(token: str, exchange: str) -> Optional[Dict[str, str]]:
        """
        Get symbol information for a token and exchange
        
        Args:
            token: Token ID
            exchange: Exchange code
            
        Returns:
            Dict with symbol info or None if not found
        """
        try:
            from database.token_db import get_symbol
            symbol = get_symbol(token, exchange)
            
            if symbol:
                br_symbol = get_br_symbol(symbol, exchange)
                br_exchange = get_brexchange(symbol, exchange)
                
                return {
                    'token': token,
                    'symbol': symbol,
                    'exchange': exchange,
                    'brsymbol': br_symbol or symbol,
                    'brexchange': br_exchange or exchange
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error mapping token {token}.{exchange}: {e}")
            return None
