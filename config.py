"""
Configuration settings for the Real-time Price System.
Uses environment variables with sensible defaults.
"""
import os
from typing import List, Dict, Any
from pathlib import Path

# Load environment variables
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / '.env'
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=False)
except ImportError:
    pass


class Settings:
    """Configuration settings"""
    
    # Server Configuration
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
    RELOAD: bool = os.getenv("RELOAD", "False").lower() == "true"
    
    # Database Configuration
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", "prices.db")
    TICK_RETENTION_DAYS: int = int(os.getenv("TICK_RETENTION_DAYS", "7"))
    
    # Angel Broker Configuration
    BROKER_API_KEY: str = os.getenv("BROKER_API_KEY", "")
    BROKER_API_SECRET: str = os.getenv("BROKER_API_SECRET", "")
    
    # Streaming Configuration
    MIN_UPDATE_INTERVAL: float = float(os.getenv("MIN_UPDATE_INTERVAL", "1.0"))
    RECONNECT_DELAY: int = int(os.getenv("RECONNECT_DELAY", "5"))
    MAX_RECONNECT_DELAY: int = int(os.getenv("MAX_RECONNECT_DELAY", "60"))
    MAX_RECONNECT_ATTEMPTS: int = int(os.getenv("MAX_RECONNECT_ATTEMPTS", "10"))
    
    # API Configuration
    CORS_ORIGINS: List[str] = os.getenv("CORS_ORIGINS", "*").split(",")
    REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", "30"))
    
    # WebSocket Configuration
    WS_HEARTBEAT_INTERVAL: int = int(os.getenv("WS_HEARTBEAT_INTERVAL", "30"))
    
    # Default Symbols to Stream
    DEFAULT_SYMBOLS: List[Dict[str, str]] = [
        {"symbol": "RELIANCE", "exchange": "NSE", "mode": "QUOTE"},
        {"symbol": "TCS", "exchange": "NSE", "mode": "QUOTE"},
        {"symbol": "INFY", "exchange": "NSE", "mode": "QUOTE"},
        {"symbol": "ICICIBANK", "exchange": "NSE", "mode": "QUOTE"},
        {"symbol": "SBIN", "exchange": "NSE", "mode": "QUOTE"},
        {"symbol": "NIFTY", "exchange": "NSE_INDEX", "mode": "LTP"},
        {"symbol": "SENSEX", "exchange": "BSE_INDEX", "mode": "LTP"},
    ]
    
    @classmethod
    def validate(cls) -> bool:
        """Validate required configuration"""
        required_env_vars = ["BROKER_API_KEY"]
        missing_vars = []
        
        for var in required_env_vars:
            if not getattr(cls, var):
                missing_vars.append(var)
        
        if missing_vars:
            print(f"Missing required environment variables: {', '.join(missing_vars)}")
            return False
        
        return True
    
    @classmethod
    def print_config(cls):
        """Print current configuration (excluding sensitive data)"""
        print("=" * 50)
        print("Real-time Price System Configuration")
        print("=" * 50)
        print(f"Host: {cls.HOST}")
        print(f"Port: {cls.PORT}")
        print(f"Log Level: {cls.LOG_LEVEL}")
        print(f"Database Path: {cls.DATABASE_PATH}")
        print(f"Tick Retention Days: {cls.TICK_RETENTION_DAYS}")
        print(f"Min Update Interval: {cls.MIN_UPDATE_INTERVAL}s")
        print(f"Reconnect Delay: {cls.RECONNECT_DELAY}s")
        print(f"Max Reconnect Attempts: {cls.MAX_RECONNECT_ATTEMPTS}")
        print(f"Default Symbols: {len(cls.DEFAULT_SYMBOLS)}")
        print(f"CORS Origins: {cls.CORS_ORIGINS}")
        print("=" * 50)


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get application settings"""
    return settings
