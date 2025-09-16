"""
Real-time price streaming service that integrates with Angel broker.
Manages live data feeds and broadcasts price updates via WebSocket.
"""
import asyncio
import json
import os
import time
from datetime import datetime
from typing import Dict, List, Set, Optional, Any, Callable
import threading
from dataclasses import dataclass
from enum import Enum

from broker.angel.api.auth_api import authenticate_broker
from broker.angel.api.data import BrokerData, get_api_response
from broker.angel.streaming.angel_adapter import AngelWebSocketAdapter
from realtime_prices.database import get_price_database, PriceDatabase
from database.auth_db import store_tokens
from utils.logging import get_logger

logger = get_logger(__name__)


class StreamingMode(Enum):
    """Streaming modes for different data types"""
    LTP = 1      # Last Traded Price
    QUOTE = 2    # Quote with OHLC and volume
    DEPTH = 3    # Market depth data


@dataclass
class SymbolConfig:
    """Configuration for a symbol to stream"""
    symbol: str
    exchange: str
    mode: StreamingMode = StreamingMode.QUOTE
    enabled: bool = True


class AngelPriceStreamer:
    """Real-time price streamer using Angel broker WebSocket"""
    
    def __init__(self, symbols: List[SymbolConfig] = None):
        """
        Initialize the price streamer
        
        Args:
            symbols: List of symbols to stream. If None, uses default symbols.
        """
        self.symbols = symbols or self._get_default_symbols()
        self.db = get_price_database()
        self.ws_adapter = None
        self.broker_data = None
        self.auth_token = None
        self.feed_token = None
        
        # Streaming state
        self.running = False
        self.connected = False
        self._subscribers = set()  # WebSocket connections to broadcast to
        self._lock = threading.RLock()
        
        # Reconnection settings
        self.reconnect_delay = 5
        self.max_reconnect_delay = 60
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 10
        
        # Rate limiting for database updates
        self._last_db_update = {}
        self.min_update_interval = 1.0  # Minimum seconds between DB updates per symbol
        
        # Statistics
        self.stats = {
            'messages_received': 0,
            'db_updates': 0,
            'broadcast_count': 0,
            'start_time': None,
            'last_message_time': None
        }
    
    def _get_default_symbols(self) -> List[SymbolConfig]:
        """Get default symbols to stream"""
        return [
            SymbolConfig("RELIANCE", "NSE", StreamingMode.QUOTE),
            SymbolConfig("TCS", "NSE", StreamingMode.QUOTE),
            SymbolConfig("INFY", "NSE", StreamingMode.QUOTE),
            SymbolConfig("ICICIBANK", "NSE", StreamingMode.QUOTE),
            SymbolConfig("SBIN", "NSE", StreamingMode.QUOTE),
            SymbolConfig("NIFTY", "NSE_INDEX", StreamingMode.LTP),
            SymbolConfig("SENSEX", "BSE_INDEX", StreamingMode.LTP),
        ]
    
    async def authenticate(self, client_code: str, pin: str, totp: str) -> bool:
        """
        Authenticate with Angel broker
        
        Args:
            client_code: Angel client code
            pin: Trading PIN
            totp: TOTP code
            
        Returns:
            bool: True if authentication successful
        """
        try:
            logger.info("Authenticating with Angel broker...")
            auth_token, feed_token, error = authenticate_broker(client_code, pin, totp)
            
            if auth_token and feed_token:
                self.auth_token = auth_token
                self.feed_token = feed_token
                self.broker_data = BrokerData(auth_token)
                
                # Store tokens for persistence
                store_tokens(auth_token, feed_token, client_code)
                logger.info("Angel broker authentication successful and tokens stored")
                return True
            else:
                logger.error(f"Angel broker authentication failed: {error}")
                return False
                
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return False
    
    async def start_streaming(self):
        """Start real-time price streaming"""
        if not self.auth_token or not self.feed_token:
            raise ValueError("Must authenticate before starting streaming")
        
        self.running = True
        self.stats['start_time'] = datetime.now()
        
        logger.info("Starting Angel price streaming...")
        
        try:
            # Initialize WebSocket adapter
            await self._initialize_websocket()
            
            # Start streaming loop
            await self._streaming_loop()
            
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            await self.stop_streaming()
            raise
    
    async def _initialize_websocket(self):
        """Initialize Angel WebSocket connection"""
        try:
            logger.info("🔧 Initializing Angel WebSocket adapter...")
            self.ws_adapter = AngelWebSocketAdapter()
            
            # Configure authentication data
            auth_data = {
                'auth_token': self.auth_token,
                'feed_token': self.feed_token,
                'api_key': os.getenv('BROKER_API_KEY')
            }
            
            logger.info("🔧 Setting up Angel WebSocket authentication...")
            # Initialize and connect
            self.ws_adapter.initialize("angel", "STREAMING_CLIENT", auth_data)
            
            # Set up message handler BEFORE connecting
            self.ws_adapter.on_market_data = self._handle_market_data
            logger.info("🔧 Message handler configured")
            
            logger.info("🔗 Connecting to Angel WebSocket...")
            self.ws_adapter.connect()
            
            # Wait for connection
            await self._wait_for_connection()
            
            # Subscribe to symbols
            await self._subscribe_symbols()
            
            logger.info("🎉 Angel WebSocket initialization completed successfully")
            
        except Exception as e:
            logger.error(f"❌ WebSocket initialization failed: {e}")
            logger.exception("Full exception details:")
            raise
    
    async def _wait_for_connection(self, timeout: int = 30):
        """Wait for WebSocket connection to be established"""
        start_time = time.time()
        logger.info(f"🔗 Waiting for WebSocket connection (timeout: {timeout}s)...")
        
        while not self.connected and time.time() - start_time < timeout:
            # Check multiple connection indicators
            ws_connected = False
            if hasattr(self.ws_adapter, 'connected'):
                ws_connected = self.ws_adapter.connected
            elif hasattr(self.ws_adapter, 'ws_client') and self.ws_adapter.ws_client:
                ws_connected = getattr(self.ws_adapter.ws_client, 'connected', False)
            
            if ws_connected:
                self.connected = True
                logger.info("✅ WebSocket connection established successfully")
                return
            
            elapsed = time.time() - start_time
            logger.debug(f"🔗 Still waiting for connection... ({elapsed:.1f}s elapsed)")
            await asyncio.sleep(1)
        
        if not self.connected:
            logger.error(f"❌ WebSocket connection timeout after {timeout}s")
            # Try to proceed anyway - sometimes the connection works but status isn't updated
            logger.warning("🔄 Proceeding with subscription attempt despite connection timeout...")
            self.connected = True  # Force connected state
    
    async def _subscribe_symbols(self):
        """Subscribe to all configured symbols"""
        logger.info(f"🔔 Starting subscription to {len(self.symbols)} symbols...")
        
        for symbol_config in self.symbols:
            if not symbol_config.enabled:
                continue
                
            try:
                logger.info(f"📡 Attempting to subscribe to {symbol_config.symbol}.{symbol_config.exchange} (mode: {symbol_config.mode.name})")
                
                # Use asyncio.to_thread for the synchronous subscribe call
                response = await asyncio.to_thread(
                    self.ws_adapter.subscribe,
                    symbol_config.symbol,
                    symbol_config.exchange,
                    symbol_config.mode.value
                )
                
                logger.info(f"📡 Subscription response for {symbol_config.symbol}: {response}")
                
                if response and response.get('status') == 'success':
                    logger.info(f"✅ Successfully subscribed to {symbol_config.symbol}.{symbol_config.exchange}")
                elif response and 'error' in response:
                    logger.warning(f"❌ Subscription failed for {symbol_config.symbol}.{symbol_config.exchange}: {response.get('error', response)}")
                else:
                    logger.warning(f"❌ Unexpected subscription response for {symbol_config.symbol}.{symbol_config.exchange}: {response}")
                
                # Add a small delay between subscriptions
                await asyncio.sleep(1.0)  # Increased delay for Angel rate limits
                
            except Exception as e:
                logger.error(f"❌ Error subscribing to {symbol_config.symbol}.{symbol_config.exchange}: {e}")
        
        logger.info(f"🔔 Subscription process completed. Waiting for real-time data...")
    
    async def _streaming_loop(self):
        """Main streaming loop"""
        logger.info("Price streaming started")
        
        while self.running:
            try:
                # Check connection health
                if not self.connected:
                    logger.warning("Connection lost, attempting to reconnect...")
                    await self._handle_reconnection()
                
                # Update statistics
                await self._update_stats()
                
                # Clean up old tick data periodically
                await self._periodic_cleanup()
                
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Error in streaming loop: {e}")
                await asyncio.sleep(5)
    
    def _handle_market_data(self, topic: str, data: Dict[str, Any]):
        """
        Handle incoming market data from WebSocket
        
        Args:
            topic: Message topic (e.g., "NSE_RELIANCE_QUOTE")
            data: Market data dictionary
        """
        try:
            self.stats['messages_received'] += 1
            self.stats['last_message_time'] = datetime.now()
            
            # Debug: Log all incoming data
            logger.info(f"🔥 Received market data - Topic: {topic}")
            logger.info(f"🔥 Data keys: {list(data.keys()) if data else 'None'}")
            logger.info(f"🔥 Raw data: {data}")
            
            # Extract symbol and exchange from topic or data
            # Angel WebSocket2 format handling
            symbol = None
            exchange = None
            
            # Try to parse from topic first
            if topic and '_' in topic:
                parts = topic.split('_')
                if len(parts) >= 2:
                    exchange = parts[0]
                    symbol = parts[1]
            
            # Fallback to data parsing if available
            if not symbol and data:
                symbol = data.get('symbol') or data.get('tk')  # tk is token in Angel format
                exchange = data.get('exchange') or data.get('e')
                
                # Map token to symbol if needed
                if symbol and symbol.isdigit():
                    from database.token_db import get_br_symbol, get_brexchange
                    try:
                        symbol = get_br_symbol(symbol)
                        exchange = get_brexchange(symbol) if not exchange else exchange
                    except Exception as e:
                        logger.debug(f"Token mapping failed for {symbol}: {e}")
            
            if not symbol or not exchange:
                logger.warning(f"Unable to extract symbol/exchange from topic: {topic}, data keys: {list(data.keys()) if data else 'None'}")
                return
            
            # Prepare price data - Angel WebSocket2 format
            # Angel uses specific field names: lp (last price), v (volume), etc.
            price_data = {
                'ltp': data.get('lp') or data.get('ltp') or 0,  # lp = last price in Angel format
                'open': data.get('o') or data.get('open') or 0,
                'high': data.get('h') or data.get('high') or 0,
                'low': data.get('l') or data.get('low') or 0,
                'close': data.get('c') or data.get('close') or data.get('lp') or data.get('ltp') or 0,
                'volume': data.get('v') or data.get('volume') or 0,
                'oi': data.get('oi') or 0,
                'bid': data.get('bp1') or data.get('bid') or 0,  # bp1 = best bid price
                'ask': data.get('sp1') or data.get('ask') or 0,  # sp1 = best ask price
                'timestamp': data.get('timestamp') or data.get('ft') or int(time.time() * 1000)  # ft = feed time
            }
            
            # Validate LTP
            if not price_data['ltp'] or price_data['ltp'] <= 0:
                logger.debug(f"Invalid LTP for {symbol}.{exchange}: {price_data['ltp']}")
                return
            
            # Rate limit database updates
            symbol_key = f"{symbol}.{exchange}"
            current_time = time.time()
            
            if (symbol_key not in self._last_db_update or 
                current_time - self._last_db_update[symbol_key] >= self.min_update_interval):
                
                # Update database
                try:
                    if self.db.upsert_price(symbol, exchange, price_data):
                        self.stats['db_updates'] += 1
                        self._last_db_update[symbol_key] = current_time
                        logger.info(f"📈 Real-time update: {symbol}.{exchange} = ₹{price_data['ltp']:.2f} (Vol: {price_data['volume']})")
                    else:
                        logger.warning(f"Failed to update database for {symbol}.{exchange}")
                except Exception as e:
                    logger.error(f"Database update error for {symbol}.{exchange}: {e}")
            
            # Broadcast to subscribers
            asyncio.create_task(self._broadcast_update(symbol, exchange, price_data))
            
        except Exception as e:
            logger.error(f"Error handling market data: {e}")
    
    async def _broadcast_update(self, symbol: str, exchange: str, price_data: Dict[str, Any]):
        """Broadcast price update to WebSocket subscribers"""
        try:
            message = {
                'type': 'price_update',
                'symbol': symbol,
                'exchange': exchange,
                'data': price_data,
                'timestamp': int(time.time() * 1000)
            }
            
            message_json = json.dumps(message)
            
            # Broadcast to streamer's direct subscribers
            if self._subscribers:
                disconnected = set()
                for websocket in self._subscribers.copy():
                    try:
                        await websocket.send_text(message_json)
                        self.stats['broadcast_count'] += 1
                    except Exception:
                        disconnected.add(websocket)
                
                # Remove disconnected clients
                self._subscribers -= disconnected
            
            # Store latest data for WebSocket manager to access
            try:
                # Import here to avoid circular import
                from realtime_prices.api import manager
                symbol_key = f"{exchange}_{symbol}"
                
                # Store the latest message in the manager for WebSocket clients to access
                if hasattr(manager, 'latest_prices'):
                    manager.latest_prices[symbol_key] = message
                else:
                    manager.latest_prices = {symbol_key: message}
                
                # Try simple broadcast - if it fails, the data is still stored
                try:
                    # Create a simple message JSON for direct sending
                    message_json = json.dumps(message)
                    # Use the manager's existing broadcast method with symbol filter
                    import asyncio
                    # Only try if there's an active event loop in this thread
                    try:
                        loop = asyncio.get_running_loop()
                        # Schedule for next cycle
                        loop.call_soon(lambda: asyncio.create_task(manager.broadcast(message_json, symbol_key)))
                        logger.debug(f"Scheduled broadcast for {symbol}.{exchange}")
                    except RuntimeError:
                        # No running loop in this thread - that's OK, data is stored
                        logger.debug(f"Stored data for {symbol}.{exchange} - WebSocket will get it on next check")
                except Exception as e:
                    logger.debug(f"Broadcast scheduling failed for {symbol}.{exchange}: {e}")
                
                self.stats['broadcast_count'] += 1
                
            except Exception as e:
                logger.debug(f"Could not handle WebSocket data for main manager: {e}")
            
        except Exception as e:
            logger.error(f"Error broadcasting update: {e}")
    
    async def _handle_reconnection(self):
        """Handle WebSocket reconnection"""
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            logger.error("Max reconnection attempts reached")
            await self.stop_streaming()
            return
        
        self.reconnect_attempts += 1
        delay = min(self.reconnect_delay * (2 ** self.reconnect_attempts), self.max_reconnect_delay)
        
        logger.info(f"Reconnecting in {delay} seconds (attempt {self.reconnect_attempts})")
        await asyncio.sleep(delay)
        
        try:
            await self._initialize_websocket()
            self.reconnect_attempts = 0  # Reset on successful connection
            logger.info("Reconnection successful")
        except Exception as e:
            logger.error(f"Reconnection failed: {e}")
    
    async def _update_stats(self):
        """Update streaming statistics"""
        # This could be extended to save stats to database or log periodically
        pass
    
    async def _periodic_cleanup(self):
        """Perform periodic cleanup tasks"""
        try:
            # Clean up old tick data every hour
            if hasattr(self, '_last_cleanup'):
                if time.time() - self._last_cleanup < 3600:  # 1 hour
                    return
            
            self.db.cleanup_old_ticks(days_to_keep=7)
            self._last_cleanup = time.time()
            
        except Exception as e:
            logger.error(f"Error in periodic cleanup: {e}")
    
    def add_subscriber(self, websocket):
        """Add WebSocket subscriber for price updates"""
        with self._lock:
            self._subscribers.add(websocket)
            logger.info(f"Added subscriber. Total: {len(self._subscribers)}")
    
    def remove_subscriber(self, websocket):
        """Remove WebSocket subscriber"""
        with self._lock:
            self._subscribers.discard(websocket)
            logger.info(f"Removed subscriber. Total: {len(self._subscribers)}")
    
    def add_symbol(self, symbol: str, exchange: str, mode: StreamingMode = StreamingMode.QUOTE):
        """Add a new symbol to stream"""
        symbol_config = SymbolConfig(symbol, exchange, mode)
        self.symbols.append(symbol_config)
        
        # Subscribe immediately if streaming
        if self.running and self.ws_adapter:
            try:
                response = self.ws_adapter.subscribe(symbol, exchange, mode.value)
                if response.get('status') == 'success':
                    logger.info(f"Added and subscribed to {symbol}.{exchange}")
                else:
                    logger.warning(f"Failed to subscribe to new symbol {symbol}.{exchange}")
            except Exception as e:
                logger.error(f"Error adding symbol {symbol}.{exchange}: {e}")
    
    def remove_symbol(self, symbol: str, exchange: str):
        """Remove a symbol from streaming"""
        # Remove from config
        self.symbols = [s for s in self.symbols if not (s.symbol == symbol and s.exchange == exchange)]
        
        # Unsubscribe if streaming
        if self.running and self.ws_adapter:
            try:
                response = self.ws_adapter.unsubscribe(symbol, exchange)
                if response.get('status') == 'success':
                    logger.info(f"Removed and unsubscribed from {symbol}.{exchange}")
            except Exception as e:
                logger.error(f"Error removing symbol {symbol}.{exchange}: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get streaming statistics"""
        stats = self.stats.copy()
        stats['symbols_count'] = len([s for s in self.symbols if s.enabled])
        stats['subscribers_count'] = len(self._subscribers)
        stats['running'] = self.running
        stats['connected'] = self.connected
        
        if stats['start_time']:
            stats['uptime_seconds'] = (datetime.now() - stats['start_time']).total_seconds()
        
        return stats
    
    async def stop_streaming(self):
        """Stop price streaming"""
        logger.info("Stopping price streaming...")
        self.running = False
        self.connected = False
        
        if self.ws_adapter:
            try:
                self.ws_adapter.disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting WebSocket: {e}")
        
        # Clear subscribers
        with self._lock:
            self._subscribers.clear()
        
        logger.info("Price streaming stopped")


# Global streamer instance
_streamer_instance = None
_streamer_lock = threading.Lock()


def get_price_streamer() -> AngelPriceStreamer:
    """Get singleton streamer instance"""
    global _streamer_instance
    
    if _streamer_instance is None:
        with _streamer_lock:
            if _streamer_instance is None:
                _streamer_instance = AngelPriceStreamer()
    
    return _streamer_instance


async def start_price_streaming_service(client_code: str, pin: str, totp: str):
    """
    Start the price streaming service
    
    Args:
        client_code: Angel client code
        pin: Trading PIN
        totp: TOTP code
    """
    streamer = get_price_streamer()
    
    # Authenticate
    if not await streamer.authenticate(client_code, pin, totp):
        raise ValueError("Authentication failed")
    
    # Start streaming
    await streamer.start_streaming()
