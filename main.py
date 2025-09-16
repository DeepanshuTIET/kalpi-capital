"""
Main entry point for the Real-time Price System.
Starts the FastAPI server with integrated Angel broker streaming.
"""
import asyncio
import os
import sys
from pathlib import Path

# Add current directory to Python path
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

import uvicorn
from realtime_prices.api import app
from utils.logging import get_logger, log_startup_banner

logger = get_logger(__name__)


def main():
    """Main function to start the real-time price system"""
    try:
        # Configuration
        host = os.getenv("HOST", "0.0.0.0")
        port = int(os.getenv("PORT", "8000"))
        log_level = os.getenv("LOG_LEVEL", "info").lower()
        reload = os.getenv("RELOAD", "false").lower() == "true"
        
        # Startup banner
        server_url = f"http://{host}:{port}"
        log_startup_banner(
            logger,
            "🚀 Real-time Price System Started",
            server_url
        )
        
        # Additional startup info
        logger.info("=" * 60)
        logger.info("📊 Angel Broker Integration: Ready")
        logger.info("🗄️  DuckDB Database: Initialized")
        logger.info("🔌 WebSocket Streaming: Available")
        logger.info("📡 REST API: Available")
        logger.info("=" * 60)
        logger.info(f"📖 API Documentation: {server_url}/docs")
        logger.info(f"🔍 ReDoc Documentation: {server_url}/redoc")
        logger.info(f"💓 Health Check: {server_url}/health")
        logger.info(f"📈 Market Status: {server_url}/market/status")
        logger.info("=" * 60)
        logger.info("🔗 WebSocket Endpoints:")
        logger.info(f"   • Real-time Prices: ws://{host}:{port}/ws")
        logger.info(f"   • Market Updates: ws://{host}:{port}/ws/market")
        logger.info("=" * 60)
        
        # Start server
        uvicorn.run(
            "realtime_prices.api:app",
            host=host,
            port=port,
            log_level=log_level,
            reload=reload,
            access_log=True
        )
        
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
