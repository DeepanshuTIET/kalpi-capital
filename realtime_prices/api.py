"""
FastAPI application for real-time price system.
Provides REST endpoints and WebSocket connections for live price data.
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import asyncio
import json
import os
from datetime import datetime, date
import uvicorn

from realtime_prices.database import get_price_database, PriceDatabase
from realtime_prices.streamer import get_price_streamer, StreamingMode, SymbolConfig
from broker.angel.utils.auth_helper import auto_authenticate, refresh_authentication, get_authentication_status
from utils.logging import get_logger

logger = get_logger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Real-time Price API",
    description="Real-time financial data pipeline with Angel broker integration",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Pydantic models
class PriceResponse(BaseModel):
    """Response model for current price data"""
    symbol: str
    exchange: str
    open: float
    high: float
    low: float
    close: float
    ltp: float
    volume: int
    oi: int = 0
    last_updated: Optional[str] = None
    change_percent: Optional[float] = None


class HistoricalData(BaseModel):
    """Response model for historical price data"""
    date: str
    symbol: str
    exchange: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    oi: int = 0
    last_updated: Optional[str] = None


class TickData(BaseModel):
    """Response model for tick data"""
    timestamp: str
    symbol: str
    exchange: str
    ltp: float
    volume: int
    oi: int = 0
    bid: float = 0.0
    ask: float = 0.0


class MarketStatus(BaseModel):
    """Response model for market status"""
    symbols_tracked: int
    latest_update: Optional[str] = None
    ticks_today: int
    database_size_mb: float
    streaming_status: Dict[str, Any]


class StreamingConfig(BaseModel):
    """Request model for streaming configuration"""
    client_code: str = Field(..., description="Angel client code")
    pin: str = Field(..., description="Trading PIN")
    totp: str = Field(..., description="TOTP code")


class SymbolRequest(BaseModel):
    """Request model for adding/removing symbols"""
    symbol: str = Field(..., description="Trading symbol")
    exchange: str = Field(..., description="Exchange code")
    mode: Optional[str] = Field("QUOTE", description="Streaming mode: LTP, QUOTE, DEPTH")


class AuthRequest(BaseModel):
    """Request model for manual authentication"""
    client_code: str = Field(..., description="Angel client code")
    pin: str = Field(..., description="Trading PIN")
    totp: str = Field(..., description="6-digit TOTP code")


class AuthStatus(BaseModel):
    """Response model for authentication status"""
    authenticated: bool
    has_auth_token: bool
    has_feed_token: bool
    auth_token_preview: Optional[str] = None
    timestamp: str


class WebSocketManager:
    """Manages WebSocket connections for real-time price updates"""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.subscriptions: Dict[WebSocket, List[str]] = {}  # WebSocket -> [symbols]
        self.latest_prices: Dict[str, Dict] = {}  # Store latest prices for each symbol
        self.last_sent: Dict[str, float] = {}  # Track when we last sent data for each symbol
    
    async def connect(self, websocket: WebSocket):
        """Accept new WebSocket connection"""
        await websocket.accept()
        self.active_connections.append(websocket)
        self.subscriptions[websocket] = []
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        """Remove WebSocket connection"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        if websocket in self.subscriptions:
            del self.subscriptions[websocket]
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")
    
    async def send_personal_message(self, message: str, websocket: WebSocket):
        """Send message to specific WebSocket"""
        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.error(f"Error sending message to WebSocket: {e}")
            self.disconnect(websocket)
    
    async def broadcast(self, message: str, symbol_filter: Optional[str] = None):
        """Broadcast message to all or filtered connections"""
        disconnected = []
        
        for websocket in self.active_connections:
            try:
                # Apply symbol filter if specified
                if symbol_filter:
                    subscribed_symbols = self.subscriptions.get(websocket, [])
                    if symbol_filter not in subscribed_symbols:
                        continue
                
                await websocket.send_text(message)
            except Exception as e:
                logger.error(f"Error broadcasting to WebSocket: {e}")
                disconnected.append(websocket)
        
        # Clean up disconnected WebSockets
        for ws in disconnected:
            self.disconnect(ws)
    
    def subscribe_symbol(self, websocket: WebSocket, symbol: str):
        """Subscribe WebSocket to symbol updates"""
        if websocket not in self.subscriptions:
            self.subscriptions[websocket] = []
        
        if symbol not in self.subscriptions[websocket]:
            self.subscriptions[websocket].append(symbol)
            logger.info(f"WebSocket subscribed to {symbol}")
    
    def unsubscribe_symbol(self, websocket: WebSocket, symbol: str):
        """Unsubscribe WebSocket from symbol updates"""
        if websocket in self.subscriptions:
            if symbol in self.subscriptions[websocket]:
                self.subscriptions[websocket].remove(symbol)
                logger.info(f"WebSocket unsubscribed from {symbol}")
    
    async def broadcast_symbol_update(self, symbol_key: str, message: dict):
        """Broadcast price update to WebSockets subscribed to a specific symbol"""
        try:
            message_json = json.dumps(message)
            await self.broadcast(message_json, symbol_filter=symbol_key)
            logger.debug(f"Broadcasted update for {symbol_key} to {len(self.active_connections)} connections")
        except Exception as e:
            logger.error(f"Error broadcasting symbol update for {symbol_key}: {e}")
    
    async def push_latest_prices(self):
        """Push latest available prices to WebSocket clients"""
        try:
            import time
            current_time = time.time()
            
            for symbol_key, price_data in self.latest_prices.items():
                # Only send if we haven't sent this symbol's data recently (rate limiting)
                last_sent_time = self.last_sent.get(symbol_key, 0)
                if current_time - last_sent_time >= 0.5:  # Send at most every 500ms per symbol
                    message_json = json.dumps(price_data)
                    
                    # Send to subscribers of this symbol
                    sent_count = 0
                    for websocket in self.active_connections:
                        try:
                            subscribed_symbols = self.subscriptions.get(websocket, [])
                            if symbol_key in subscribed_symbols:
                                await websocket.send_text(message_json)
                                sent_count += 1
                        except Exception as e:
                            logger.debug(f"Error sending to WebSocket client: {e}")
                            # Don't remove client here, let the main disconnect handler do it
                    
                    if sent_count > 0:
                        self.last_sent[symbol_key] = current_time
                        logger.debug(f"Pushed {symbol_key} price update to {sent_count} clients")
                        
        except Exception as e:
            logger.error(f"Error pushing latest prices: {e}")


# Global WebSocket manager
manager = WebSocketManager()

# Background task to push latest prices
async def price_pusher_task():
    """Background task that regularly pushes latest prices to WebSocket clients"""
    while True:
        try:
            if manager.active_connections and manager.latest_prices:
                await manager.push_latest_prices()
            await asyncio.sleep(0.5)  # Check every 500ms
        except Exception as e:
            logger.error(f"Error in price pusher task: {e}")
            await asyncio.sleep(1)  # Wait longer on error

# Start background task
@app.on_event("startup")
async def startup_event():
    """Start background tasks when the app starts"""
    logger.info("Starting Real-time Price API...")
    
    # Initialize database
    db = get_price_database()
    logger.info("Database initialized")
    
    # Start price pusher background task
    asyncio.create_task(price_pusher_task())
    logger.info("Price pusher background task started")
    
    # Set up periodic cleanup
    asyncio.create_task(periodic_cleanup())
    logger.info("Periodic cleanup task started")
    
    logger.info("Real-time Price API ready for Angel broker data")

@app.on_event("shutdown") 
async def shutdown_event():
    """Cleanup when the app shuts down"""
    logger.info("Shutting down Real-time Price API...")
    
    # Stop streaming if running
    try:
        streamer = get_price_streamer()
        await streamer.stop_streaming()
    except Exception as e:
        logger.debug(f"Error stopping streamer during shutdown: {e}")
    
    logger.info("Real-time Price API shutdown complete")

# Dependencies
def get_database():
    """Dependency to get database instance"""
    return get_price_database()

def get_streamer():
    """Dependency to get streamer instance"""
    return get_price_streamer()

async def fetch_live_price_from_angel(symbol: str, exchange: str) -> Optional[Dict[str, Any]]:
    """Fetch live price data directly from Angel broker API"""
    try:
        from broker.angel.api.data import BrokerData
        import time
        
        # Try auto-authentication first
        auth_token, feed_token, error = auto_authenticate()
        
        if not auth_token:
            # Only log as debug before authentication, not warning
            logger.debug(f"No Angel auth token available for live data fetch: {error}")
            return None
        
        broker_data = BrokerData(auth_token)
        
        # Get quote from Angel - using proper Angel API call
        quote = await asyncio.to_thread(broker_data.get_quotes, symbol, exchange)
        if not quote:
            logger.debug(f"No quote data returned from Angel for {symbol}.{exchange}")
            return None
        
        # Convert Angel format to our format
        result = {
            'symbol': symbol,
            'exchange': exchange,
            'ltp': float(quote.get('ltp', 0)) if quote.get('ltp') else 0,
            'open': float(quote.get('open', 0)) if quote.get('open') else 0,
            'high': float(quote.get('high', 0)) if quote.get('high') else 0,
            'low': float(quote.get('low', 0)) if quote.get('low') else 0,
            'close': float(quote.get('close', quote.get('ltp', 0))) if quote.get('close') or quote.get('ltp') else 0,
            'volume': int(quote.get('volume', 0)) if quote.get('volume') else 0,
            'oi': int(quote.get('oi', 0)) if quote.get('oi') else 0,
            'last_updated': datetime.now().isoformat(),
            'timestamp': int(time.time() * 1000)
        }
        
        logger.info(f"📊 Angel API live data for {symbol}.{exchange}: LTP=₹{result['ltp']}")
        return result
        
    except Exception as e:
        logger.error(f"Error fetching live data from Angel for {symbol}.{exchange}: {e}")
        return None


# REST API Endpoints

@app.get("/api/", response_model=Dict[str, str])
async def api_root():
    """API root endpoint with information"""
    return {
        "message": "Real-time Price API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }

@app.get("/")
async def root():
    """Serve the landing page"""
    from fastapi.responses import FileResponse
    return FileResponse('static/index.html')


@app.get("/health", response_model=Dict[str, Any])
async def health_check(db: PriceDatabase = Depends(get_database)):
    """Health check endpoint"""
    try:
        market_status = db.get_market_status()
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "database": "connected",
            "market_status": market_status
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unhealthy")


@app.get("/price/{symbol}", response_model=PriceResponse)
async def get_current_price(
    symbol: str, 
    exchange: str = "NSE",
    db: PriceDatabase = Depends(get_database)
):
    """Get current price for a symbol"""
    try:
        result = db.get_current_price(symbol.upper(), exchange.upper())
        
        # If not in database, try to fetch from Angel broker
        if not result:
            try:
                result = await fetch_live_price_from_angel(symbol.upper(), exchange.upper())
                if result:
                    # Store in database for future requests
                    db.upsert_price(symbol.upper(), exchange.upper(), result)
                    logger.info(f"📊 Fetched and cached live data for {symbol}.{exchange}")
                else:
                    raise HTTPException(
                        status_code=404, 
                        detail=f"Price data not found for {symbol}.{exchange}"
                    )
            except Exception as e:
                logger.error(f"Failed to fetch live data for {symbol}.{exchange}: {e}")
                raise HTTPException(
                    status_code=404, 
                    detail=f"Price data not found for {symbol}.{exchange}"
                )
        
        # Calculate change percentage if possible
        change_percent = None
        if result.get('open') and result.get('close'):
            change_percent = ((result['close'] - result['open']) / result['open']) * 100
        
        return PriceResponse(
            symbol=result['symbol'],
            exchange=result['exchange'],
            open=result['open'],
            high=result['high'],
            low=result['low'],
            close=result['close'],
            ltp=result['ltp'],
            volume=result['volume'],
            oi=result['oi'],
            last_updated=result['last_updated'],
            change_percent=change_percent
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting price for {symbol}.{exchange}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ================================
# Authentication Endpoints
# ================================

@app.get("/auth/status", response_model=AuthStatus)
async def get_auth_status():
    """Get current authentication status"""
    try:
        status = get_authentication_status()
        return AuthStatus(**status)
    except Exception as e:
        logger.error(f"Error getting auth status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get authentication status")


@app.post("/auth/login")
async def authenticate_user(auth_request: AuthRequest):
    """Manually authenticate with Angel broker"""
    try:
        auth_token, feed_token, error = refresh_authentication(
            auth_request.client_code,
            auth_request.pin,
            auth_request.totp
        )
        
        if auth_token and feed_token:
            return {
                "status": "success",
                "message": "Authentication successful",
                "auth_token_preview": f"{auth_token[:10]}..." if auth_token else None
            }
        else:
            raise HTTPException(
                status_code=401, 
                detail=f"Authentication failed: {error}"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        raise HTTPException(status_code=500, detail="Authentication service error")


@app.post("/auth/auto")
async def auto_authenticate_user():
    """Attempt automatic authentication using stored tokens"""
    try:
        auth_token, feed_token, error = auto_authenticate()
        
        if auth_token and feed_token:
            return {
                "status": "success",
                "message": "Auto-authentication successful",
                "auth_token_preview": f"{auth_token[:10]}..." if auth_token else None
            }
        else:
            return {
                "status": "failed",
                "message": f"Auto-authentication failed: {error}",
                "requires_manual_auth": True
            }
    except Exception as e:
        logger.error(f"Auto-authentication error: {e}")
        raise HTTPException(status_code=500, detail="Auto-authentication service error")


@app.get("/streaming/status")
async def get_streaming_status(streamer: Any = Depends(get_streamer)):
    """Get current streaming status and statistics"""
    try:
        stats = streamer.get_stats()
        return {
            "streaming": {
                "running": stats.get('running', False),
                "connected": stats.get('connected', False),
                "uptime_seconds": stats.get('uptime_seconds', 0),
                "symbols_count": stats.get('symbols_count', 0),
                "subscribers_count": stats.get('subscribers_count', 0)
            },
            "statistics": {
                "messages_received": stats.get('messages_received', 0),
                "db_updates": stats.get('db_updates', 0),
                "broadcast_count": stats.get('broadcast_count', 0),
                "last_message_time": stats.get('last_message_time')
            },
            "websocket_connections": len(manager.active_connections),
            "auth_status": get_authentication_status()
        }
    except Exception as e:
        logger.error(f"Error getting streaming status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get streaming status")


@app.get("/debug/websocket-data")
async def get_websocket_debug_data():
    """Debug endpoint to check WebSocket manager state"""
    try:
        return {
            "active_connections": len(manager.active_connections),
            "latest_prices_count": len(manager.latest_prices),
            "latest_prices": {k: v for k, v in list(manager.latest_prices.items())[-5:]},  # Last 5 only
            "subscriptions_count": len(manager.subscriptions),
            "subscriptions": {i: subs for i, subs in enumerate(list(manager.subscriptions.values())[:3])}  # First 3 only
        }
    except Exception as e:
        logger.error(f"Error getting WebSocket debug data: {e}")
        raise HTTPException(status_code=500, detail="Failed to get debug data")


# ================================
# Historical Data Endpoints
# ================================

@app.get("/history/{symbol}", response_model=List[HistoricalData])
async def get_price_history(
    symbol: str,
    exchange: str = "NSE",
    days: Optional[int] = 30,
    db: PriceDatabase = Depends(get_database)
):
    """Get historical OHLC data for a symbol"""
    try:
        if days and (days < 1 or days > 365):
            raise HTTPException(status_code=400, detail="Days must be between 1 and 365")
        
        results = db.get_price_history(symbol.upper(), exchange.upper(), days or 30)
        
        return [
            HistoricalData(
                date=row['date'],
                symbol=row['symbol'],
                exchange=row['exchange'],
                open=row['open'],
                high=row['high'],
                low=row['low'],
                close=row['close'],
                volume=row['volume'],
                oi=row['oi'],
                last_updated=row['last_updated']
            )
            for row in results
        ]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting history for {symbol}.{exchange}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/ticks/{symbol}", response_model=List[TickData])
async def get_recent_ticks(
    symbol: str,
    exchange: str = "NSE",
    limit: Optional[int] = 100,
    db: PriceDatabase = Depends(get_database)
):
    """Get recent tick data for a symbol"""
    try:
        if limit and (limit < 1 or limit > 1000):
            raise HTTPException(status_code=400, detail="Limit must be between 1 and 1000")
        
        results = db.get_recent_ticks(symbol.upper(), exchange.upper(), limit or 100)
        
        return [
            TickData(
                timestamp=row['timestamp'],
                symbol=row['symbol'],
                exchange=row['exchange'],
                ltp=row['ltp'],
                volume=row['volume'],
                oi=row['oi'],
                bid=row['bid'],
                ask=row['ask']
            )
            for row in results
        ]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting ticks for {symbol}.{exchange}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/market/status", response_model=MarketStatus)
async def get_market_status(
    db: PriceDatabase = Depends(get_database),
    streamer: Any = Depends(get_streamer)
):
    """Get overall market status and streaming statistics"""
    try:
        db_status = db.get_market_status()
        streaming_stats = streamer.get_stats()
        
        return MarketStatus(
            symbols_tracked=db_status.get('symbols_tracked', 0),
            latest_update=db_status.get('latest_update'),
            ticks_today=db_status.get('ticks_today', 0),
            database_size_mb=db_status.get('database_size_mb', 0.0),
            streaming_status=streaming_stats
        )
        
    except Exception as e:
        logger.error(f"Error getting market status: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/streaming/start")
async def start_streaming(
    config: StreamingConfig,
    background_tasks: BackgroundTasks,
    streamer: Any = Depends(get_streamer)
):
    """Start price streaming with Angel broker"""
    try:
        # Authenticate first
        auth_success = await streamer.authenticate(
            config.client_code,
            config.pin,
            config.totp
        )
        
        if not auth_success:
            raise HTTPException(status_code=401, detail="Authentication failed")
        
        # Start streaming in background
        background_tasks.add_task(streamer.start_streaming)
        
        return {"message": "Streaming started successfully", "status": "running"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting streaming: {e}")
        raise HTTPException(status_code=500, detail="Failed to start streaming")


@app.post("/streaming/stop")
async def stop_streaming(streamer: Any = Depends(get_streamer)):
    """Stop price streaming"""
    try:
        await streamer.stop_streaming()
        return {"message": "Streaming stopped", "status": "stopped"}
        
    except Exception as e:
        logger.error(f"Error stopping streaming: {e}")
        raise HTTPException(status_code=500, detail="Failed to stop streaming")


@app.post("/streaming/symbol/add")
async def add_streaming_symbol(
    symbol_req: SymbolRequest,
    streamer: Any = Depends(get_streamer)
):
    """Add symbol to streaming"""
    try:
        mode_map = {
            "LTP": StreamingMode.LTP,
            "QUOTE": StreamingMode.QUOTE,
            "DEPTH": StreamingMode.DEPTH
        }
        
        mode = mode_map.get(symbol_req.mode.upper(), StreamingMode.QUOTE)
        streamer.add_symbol(symbol_req.symbol.upper(), symbol_req.exchange.upper(), mode)
        
        return {
            "message": f"Added {symbol_req.symbol}.{symbol_req.exchange} to streaming",
            "symbol": symbol_req.symbol.upper(),
            "exchange": symbol_req.exchange.upper(),
            "mode": symbol_req.mode.upper()
        }
        
    except Exception as e:
        logger.error(f"Error adding streaming symbol: {e}")
        raise HTTPException(status_code=500, detail="Failed to add symbol")


@app.delete("/streaming/symbol/remove")
async def remove_streaming_symbol(
    symbol_req: SymbolRequest,
    streamer: Any = Depends(get_streamer)
):
    """Remove symbol from streaming"""
    try:
        streamer.remove_symbol(symbol_req.symbol.upper(), symbol_req.exchange.upper())
        
        return {
            "message": f"Removed {symbol_req.symbol}.{symbol_req.exchange} from streaming",
            "symbol": symbol_req.symbol.upper(),
            "exchange": symbol_req.exchange.upper()
        }
        
    except Exception as e:
        logger.error(f"Error removing streaming symbol: {e}")
        raise HTTPException(status_code=500, detail="Failed to remove symbol")


# WebSocket Endpoints

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Main WebSocket endpoint for real-time price updates"""
    await manager.connect(websocket)
    
    try:
        while True:
            # Wait for client messages
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
                
                if message.get('type') == 'subscribe':
                    symbol = message.get('symbol', '').upper()
                    exchange = message.get('exchange', 'NSE').upper()
                    symbol_key = f"{exchange}_{symbol}"
                    
                    manager.subscribe_symbol(websocket, symbol_key)
                    
                    response = {
                        'type': 'subscription_ack',
                        'symbol': symbol,
                        'exchange': exchange,
                        'status': 'subscribed'
                    }
                    await manager.send_personal_message(json.dumps(response), websocket)
                
                elif message.get('type') == 'unsubscribe':
                    symbol = message.get('symbol', '').upper()
                    exchange = message.get('exchange', 'NSE').upper()
                    symbol_key = f"{exchange}_{symbol}"
                    
                    manager.unsubscribe_symbol(websocket, symbol_key)
                    
                    response = {
                        'type': 'unsubscription_ack',
                        'symbol': symbol,
                        'exchange': exchange,
                        'status': 'unsubscribed'
                    }
                    await manager.send_personal_message(json.dumps(response), websocket)
                
                elif message.get('type') == 'ping':
                    pong_response = {
                        'type': 'pong',
                        'timestamp': datetime.now().isoformat()
                    }
                    await manager.send_personal_message(json.dumps(pong_response), websocket)
                
            except json.JSONDecodeError:
                error_response = {
                    'type': 'error',
                    'message': 'Invalid JSON format'
                }
                await manager.send_personal_message(json.dumps(error_response), websocket)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


@app.websocket("/ws/market")
async def market_websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for market-wide updates"""
    await manager.connect(websocket)
    
    try:
        # Send initial market status
        db = get_price_database()
        streamer = get_price_streamer()
        
        initial_status = {
            'type': 'market_status',
            'data': {
                'database': db.get_market_status(),
                'streaming': streamer.get_stats()
            },
            'timestamp': datetime.now().isoformat()
        }
        await manager.send_personal_message(json.dumps(initial_status), websocket)
        
        # Keep connection alive and send periodic updates
        while True:
            await asyncio.sleep(30)  # Send updates every 30 seconds
            
            status_update = {
                'type': 'market_status',
                'data': {
                    'database': db.get_market_status(),
                    'streaming': streamer.get_stats()
                },
                'timestamp': datetime.now().isoformat()
            }
            await manager.send_personal_message(json.dumps(status_update), websocket)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"Market WebSocket error: {e}")
        manager.disconnect(websocket)


# Event handlers (startup event is defined earlier)

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down Real-time Price API...")
    
    # Stop streaming
    try:
        streamer = get_price_streamer()
        await streamer.stop_streaming()
    except Exception as e:
        logger.error(f"Error stopping streamer: {e}")


async def periodic_cleanup():
    """Periodic cleanup task"""
    while True:
        try:
            await asyncio.sleep(3600)  # Run every hour
            
            db = get_price_database()
            db.cleanup_old_ticks(days_to_keep=7)
            
        except Exception as e:
            logger.error(f"Error in periodic cleanup: {e}")

@app.get("/test/angel-data/{symbol}")
async def test_angel_data(symbol: str, exchange: str = "NSE"):
    """Test endpoint to manually fetch data from Angel broker"""
    try:
        logger.info(f"🧪 Testing Angel data fetch for {symbol}.{exchange}")
        
        # Try direct Angel API call
        result = await fetch_live_price_from_angel(symbol.upper(), exchange.upper())
        
        if result:
            logger.info(f"🧪 Test successful - got data: {result}")
            return {"status": "success", "data": result}
        else:
            logger.warning(f"🧪 Test failed - no data returned")
            return {"status": "error", "message": "No data returned from Angel API"}
            
    except Exception as e:
        logger.error(f"🧪 Test failed with error: {e}")
        raise HTTPException(status_code=500, detail=f"Test failed: {str(e)}")

@app.get("/debug/streamer-stats")
async def get_streamer_stats(streamer: Any = Depends(get_streamer)):
    """Get detailed streaming statistics for debugging"""
    try:
        stats = streamer.get_stats()
        return {
            "streaming_active": streamer.running,
            "connected": streamer.connected,
            "subscribers": len(streamer._subscribers),
            "symbols_count": len(streamer.symbols),
            "stats": stats
        }
    except Exception as e:
        logger.error(f"Error getting streamer stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get stats")


# Main entry point
if __name__ == "__main__":
    logger.info("Starting Real-time Price API server...")
    
    uvicorn.run(
        "realtime_prices.api:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
        reload=False  # Set to True for development
    )
