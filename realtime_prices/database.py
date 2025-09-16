"""
DuckDB database implementation for real-time price data storage.
Provides efficient OHLC data storage with upsert capabilities.
"""
import duckdb
import asyncio
from datetime import datetime, date, timezone
from typing import Optional, List, Dict, Any
from pathlib import Path
import threading
from utils.logging import get_logger

logger = get_logger(__name__)


class PriceDatabase:
    """DuckDB-based price database for real-time OHLC data"""
    
    def __init__(self, db_path: str = "prices.db"):
        """
        Initialize the price database with DuckDB
        
        Args:
            db_path: Path to the DuckDB database file
        """
        self.db_path = db_path
        self.conn = None
        self._lock = threading.RLock()
        self._initialize_database()
    
    def _initialize_database(self):
        """Initialize database connection and create schema"""
        try:
            # Ensure directory exists
            db_file = Path(self.db_path)
            db_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Connect to DuckDB
            self.conn = duckdb.connect(self.db_path)
            
            # Create schema
            self._create_schema()
            logger.info(f"Initialized DuckDB database at {self.db_path}")
            
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
    
    def _create_schema(self):
        """Create the price table schema with proper indexing"""
        with self._lock:
            try:
                # Create main prices table
                self.conn.execute("""
                    CREATE TABLE IF NOT EXISTS prices (
                        date DATE NOT NULL,
                        symbol VARCHAR(20) NOT NULL,
                        exchange VARCHAR(10) NOT NULL,
                        open DECIMAL(12,2) NOT NULL DEFAULT 0.00,
                        high DECIMAL(12,2) NOT NULL DEFAULT 0.00,
                        low DECIMAL(12,2) NOT NULL DEFAULT 0.00,
                        close DECIMAL(12,2) NOT NULL DEFAULT 0.00,
                        volume BIGINT NOT NULL DEFAULT 0,
                        oi BIGINT NOT NULL DEFAULT 0,
                        last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (date, symbol, exchange)
                    )
                """)
                
                # Create indexes for fast lookups
                self.conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_symbol_date 
                    ON prices(symbol, exchange, date DESC)
                """)
                
                self.conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_date_symbol 
                    ON prices(date DESC, symbol, exchange)
                """)
                
                self.conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_last_updated 
                    ON prices(last_updated DESC)
                """)
                
                # Create real-time ticks table for intraday data
                self.conn.execute("""
                    CREATE TABLE IF NOT EXISTS real_time_ticks (
                        id BIGINT PRIMARY KEY,
                        timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
                        symbol VARCHAR(20) NOT NULL,
                        exchange VARCHAR(10) NOT NULL,
                        ltp DECIMAL(12,2) NOT NULL,
                        volume BIGINT DEFAULT 0,
                        oi BIGINT DEFAULT 0,
                        bid DECIMAL(12,2) DEFAULT 0.00,
                        ask DECIMAL(12,2) DEFAULT 0.00,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Create sequence for tick IDs
                self.conn.execute("""
                    CREATE SEQUENCE IF NOT EXISTS tick_id_seq START 1
                """)
                
                # Index for real-time ticks
                self.conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ticks_symbol_time 
                    ON real_time_ticks(symbol, exchange, timestamp DESC)
                """)
                
                logger.info("Database schema created successfully")
                
            except Exception as e:
                logger.error(f"Failed to create database schema: {e}")
                raise
    
    def upsert_price(self, symbol: str, exchange: str, price_data: Dict[str, Any]) -> bool:
        """
        Update existing or insert new price data for today
        
        Args:
            symbol: Trading symbol
            exchange: Exchange code
            price_data: Dictionary containing price information
                      {ltp, volume, oi, bid, ask, open, high, low, close}
        
        Returns:
            bool: True if successful, False otherwise
        """
        with self._lock:
            try:
                today = date.today()
                current_price = float(price_data.get('ltp', 0))
                volume = int(price_data.get('volume', 0))
                oi = int(price_data.get('oi', 0))
                
                # Check if record exists for today
                existing = self.conn.execute("""
                    SELECT open, high, low, close, volume, oi 
                    FROM prices 
                    WHERE date = ? AND symbol = ? AND exchange = ?
                """, [today, symbol, exchange]).fetchone()
                
                if existing:
                    # Update existing record
                    old_open, old_high, old_low, old_close, old_volume, old_oi = existing
                    
                    new_high = max(float(old_high), current_price)
                    new_low = min(float(old_low), current_price) if float(old_low) > 0 else current_price
                    new_volume = max(old_volume, volume)  # Use max volume seen
                    new_oi = oi if oi > 0 else old_oi  # Use latest OI if available
                    
                    self.conn.execute("""
                        UPDATE prices SET 
                            high = ?,
                            low = ?,
                            close = ?,
                            volume = ?,
                            oi = ?,
                            last_updated = CURRENT_TIMESTAMP
                        WHERE date = ? AND symbol = ? AND exchange = ?
                    """, [new_high, new_low, current_price, new_volume, new_oi, today, symbol, exchange])
                    
                else:
                    # Insert new record
                    open_price = price_data.get('open', current_price)
                    high_price = price_data.get('high', current_price)
                    low_price = price_data.get('low', current_price)
                    
                    self.conn.execute("""
                        INSERT INTO prices (date, symbol, exchange, open, high, low, close, volume, oi)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, [today, symbol, exchange, open_price, high_price, low_price, 
                         current_price, volume, oi])
                
                # Also insert real-time tick
                self._insert_tick(symbol, exchange, price_data)
                
                return True
                
            except Exception as e:
                logger.error(f"Failed to upsert price for {symbol}.{exchange}: {e}")
                return False
    
    def _insert_tick(self, symbol: str, exchange: str, price_data: Dict[str, Any]):
        """Insert real-time tick data"""
        try:
            tick_id = self.conn.execute("SELECT nextval('tick_id_seq')").fetchone()[0]
            
            self.conn.execute("""
                INSERT INTO real_time_ticks 
                (id, timestamp, symbol, exchange, ltp, volume, oi, bid, ask)
                VALUES (?, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?, ?)
            """, [
                tick_id,
                symbol,
                exchange,
                float(price_data.get('ltp', 0)),
                int(price_data.get('volume', 0)),
                int(price_data.get('oi', 0)),
                float(price_data.get('bid', 0)),
                float(price_data.get('ask', 0))
            ])
            
        except Exception as e:
            logger.error(f"Failed to insert tick for {symbol}.{exchange}: {e}")
    
    def get_current_price(self, symbol: str, exchange: str) -> Optional[Dict[str, Any]]:
        """
        Get current price data for a symbol
        
        Args:
            symbol: Trading symbol
            exchange: Exchange code
            
        Returns:
            Dict containing current price data or None if not found
        """
        with self._lock:
            try:
                result = self.conn.execute("""
                    SELECT symbol, exchange, open, high, low, close, volume, oi, last_updated
                    FROM prices 
                    WHERE symbol = ? AND exchange = ? AND date = CURRENT_DATE
                    ORDER BY last_updated DESC 
                    LIMIT 1
                """, [symbol, exchange]).fetchone()
                
                if result:
                    return {
                        'symbol': result[0],
                        'exchange': result[1],
                        'open': float(result[2]),
                        'high': float(result[3]),
                        'low': float(result[4]),
                        'close': float(result[5]),
                        'ltp': float(result[5]),  # Close price as LTP
                        'volume': int(result[6]),
                        'oi': int(result[7]),
                        'last_updated': result[8].isoformat() if result[8] else None
                    }
                
                return None
                
            except Exception as e:
                logger.error(f"Failed to get current price for {symbol}.{exchange}: {e}")
                return None
    
    def get_price_history(self, symbol: str, exchange: str, days: int = 30) -> List[Dict[str, Any]]:
        """
        Get historical price data for a symbol
        
        Args:
            symbol: Trading symbol
            exchange: Exchange code
            days: Number of days to fetch
            
        Returns:
            List of price data dictionaries
        """
        with self._lock:
            try:
                results = self.conn.execute("""
                    SELECT date, symbol, exchange, open, high, low, close, volume, oi, last_updated
                    FROM prices 
                    WHERE symbol = ? AND exchange = ?
                    ORDER BY date DESC 
                    LIMIT ?
                """, [symbol, exchange, days]).fetchall()
                
                history = []
                for row in results:
                    history.append({
                        'date': row[0].isoformat() if row[0] else None,
                        'symbol': row[1],
                        'exchange': row[2],
                        'open': float(row[3]),
                        'high': float(row[4]),
                        'low': float(row[5]),
                        'close': float(row[6]),
                        'volume': int(row[7]),
                        'oi': int(row[8]),
                        'last_updated': row[9].isoformat() if row[9] else None
                    })
                
                return history
                
            except Exception as e:
                logger.error(f"Failed to get price history for {symbol}.{exchange}: {e}")
                return []
    
    def get_recent_ticks(self, symbol: str, exchange: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get recent tick data for a symbol
        
        Args:
            symbol: Trading symbol
            exchange: Exchange code
            limit: Number of recent ticks to fetch
            
        Returns:
            List of tick data dictionaries
        """
        with self._lock:
            try:
                results = self.conn.execute("""
                    SELECT timestamp, symbol, exchange, ltp, volume, oi, bid, ask
                    FROM real_time_ticks 
                    WHERE symbol = ? AND exchange = ?
                    ORDER BY timestamp DESC 
                    LIMIT ?
                """, [symbol, exchange, limit]).fetchall()
                
                ticks = []
                for row in results:
                    ticks.append({
                        'timestamp': row[0].isoformat() if row[0] else None,
                        'symbol': row[1],
                        'exchange': row[2],
                        'ltp': float(row[3]),
                        'volume': int(row[4]),
                        'oi': int(row[5]),
                        'bid': float(row[6]),
                        'ask': float(row[7])
                    })
                
                return ticks
                
            except Exception as e:
                logger.error(f"Failed to get recent ticks for {symbol}.{exchange}: {e}")
                return []
    
    def get_market_status(self) -> Dict[str, Any]:
        """
        Get overall market status and statistics
        
        Returns:
            Dict containing market statistics
        """
        with self._lock:
            try:
                # Count total symbols being tracked today
                symbol_count = self.conn.execute("""
                    SELECT COUNT(DISTINCT symbol || '.' || exchange) 
                    FROM prices 
                    WHERE date = CURRENT_DATE
                """).fetchone()[0]
                
                # Get latest update time
                latest_update = self.conn.execute("""
                    SELECT MAX(last_updated) 
                    FROM prices 
                    WHERE date = CURRENT_DATE
                """).fetchone()[0]
                
                # Count total ticks today
                tick_count = self.conn.execute("""
                    SELECT COUNT(*) 
                    FROM real_time_ticks 
                    WHERE DATE(timestamp) = CURRENT_DATE
                """).fetchone()[0]
                
                return {
                    'symbols_tracked': symbol_count,
                    'latest_update': latest_update.isoformat() if latest_update else None,
                    'ticks_today': tick_count,
                    'database_size_mb': self._get_db_size_mb()
                }
                
            except Exception as e:
                logger.error(f"Failed to get market status: {e}")
                return {}
    
    def _get_db_size_mb(self) -> float:
        """Get database file size in MB"""
        try:
            db_file = Path(self.db_path)
            if db_file.exists():
                return db_file.stat().st_size / (1024 * 1024)
            return 0.0
        except Exception:
            return 0.0
    
    def cleanup_old_ticks(self, days_to_keep: int = 7):
        """
        Clean up old tick data to manage database size
        
        Args:
            days_to_keep: Number of days of tick data to retain
        """
        with self._lock:
            try:
                deleted_count = self.conn.execute("""
                    DELETE FROM real_time_ticks 
                    WHERE timestamp < CURRENT_TIMESTAMP - INTERVAL ? DAYS
                """, [days_to_keep]).fetchone()
                
                if deleted_count:
                    logger.info(f"Cleaned up {deleted_count} old tick records")
                
            except Exception as e:
                logger.error(f"Failed to cleanup old ticks: {e}")
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")


# Global database instance
_db_instance = None
_db_lock = threading.Lock()


def get_price_database() -> PriceDatabase:
    """Get singleton database instance"""
    global _db_instance
    
    if _db_instance is None:
        with _db_lock:
            if _db_instance is None:
                _db_instance = PriceDatabase()
    
    return _db_instance
