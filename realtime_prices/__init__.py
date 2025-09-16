"""
Real-time Price System

A comprehensive real-time financial data pipeline that integrates with Angel broker
for live price feeds, stores data in DuckDB, and provides REST/WebSocket APIs.

Features:
- Real-time price streaming from Angel broker
- Efficient OHLC data storage with DuckDB
- REST API for historical and current price data
- WebSocket connections for live price updates
- Automatic reconnection and error handling
- Market statistics and monitoring
"""

__version__ = "1.0.0"
__author__ = "Kalpi Capital"

from .database import PriceDatabase, get_price_database
from .streamer import AngelPriceStreamer, get_price_streamer, StreamingMode, SymbolConfig
from .api import app

__all__ = [
    "PriceDatabase",
    "get_price_database", 
    "AngelPriceStreamer",
    "get_price_streamer",
    "StreamingMode",
    "SymbolConfig",
    "app"
]
