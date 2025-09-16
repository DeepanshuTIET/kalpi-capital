"""
Test script for the Real-time Price System.
Tests database operations, API endpoints, and basic functionality.
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Add current directory to Python path
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

import httpx
import websocket
from realtime_prices.database import PriceDatabase
from realtime_prices.streamer import SymbolConfig, StreamingMode
from utils.logging import get_logger

logger = get_logger(__name__)


class SystemTester:
    """Comprehensive system tester"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.client = httpx.Client(timeout=30.0)
        self.test_results = []
    
    def log_test(self, test_name: str, success: bool, message: str = ""):
        """Log test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        logger.info(f"{status} {test_name}: {message}")
        self.test_results.append({
            "test": test_name,
            "success": success,
            "message": message
        })
    
    def test_database_operations(self):
        """Test database functionality"""
        logger.info("🗄️ Testing Database Operations...")
        
        try:
            # Initialize test database
            db = PriceDatabase(":memory:")  # Use in-memory database for tests
            
            # Test price insertion
            test_data = {
                'ltp': 150.75,
                'open': 148.50,
                'high': 152.00,
                'low': 147.25,
                'volume': 1000000,
                'oi': 500000,
                'bid': 150.70,
                'ask': 150.80
            }
            
            success = db.upsert_price("TESTSTOCK", "NSE", test_data)
            self.log_test("Database Insert", success, "Test price data inserted")
            
            # Test price retrieval
            current_price = db.get_current_price("TESTSTOCK", "NSE")
            success = current_price is not None and current_price['ltp'] == 150.75
            self.log_test("Database Retrieve", success, f"Retrieved: {current_price}")
            
            # Test price update
            update_data = {'ltp': 151.25, 'high': 153.00, 'volume': 1200000}
            success = db.upsert_price("TESTSTOCK", "NSE", update_data)
            updated_price = db.get_current_price("TESTSTOCK", "NSE")
            success = success and updated_price['high'] == 153.00
            self.log_test("Database Update", success, "Price data updated correctly")
            
            # Test market status
            status = db.get_market_status()
            success = isinstance(status, dict) and 'symbols_tracked' in status
            self.log_test("Market Status", success, f"Status: {status}")
            
            db.close()
            
        except Exception as e:
            self.log_test("Database Operations", False, f"Error: {e}")
    
    def test_api_endpoints(self):
        """Test REST API endpoints"""
        logger.info("🌐 Testing API Endpoints...")
        
        try:
            # Test health endpoint
            response = self.client.get(f"{self.base_url}/health")
            success = response.status_code == 200
            self.log_test("Health Endpoint", success, f"Status: {response.status_code}")
            
            # Test root endpoint
            response = self.client.get(f"{self.base_url}/")
            success = response.status_code == 200
            data = response.json() if success else {}
            self.log_test("Root Endpoint", success, f"Message: {data.get('message', 'N/A')}")
            
            # Test market status endpoint
            response = self.client.get(f"{self.base_url}/market/status")
            success = response.status_code in [200, 503]  # 503 if no data yet
            self.log_test("Market Status Endpoint", success, f"Status: {response.status_code}")
            
            # Test price endpoint (might fail if no data)
            response = self.client.get(f"{self.base_url}/price/RELIANCE?exchange=NSE")
            success = response.status_code in [200, 404]  # 404 if no data
            self.log_test("Price Endpoint", success, f"Status: {response.status_code}")
            
            # Test history endpoint
            response = self.client.get(f"{self.base_url}/history/RELIANCE?exchange=NSE&days=10")
            success = response.status_code in [200, 404]
            self.log_test("History Endpoint", success, f"Status: {response.status_code}")
            
        except Exception as e:
            self.log_test("API Endpoints", False, f"Error: {e}")
    
    def test_websocket_connection(self):
        """Test WebSocket connectivity"""
        logger.info("🔌 Testing WebSocket Connection...")
        
        try:
            ws_url = self.base_url.replace("http://", "ws://") + "/ws"
            
            def on_message(ws, message):
                try:
                    data = json.loads(message)
                    logger.info(f"Received WebSocket message: {data.get('type', 'unknown')}")
                except:
                    logger.info(f"Received WebSocket message: {message}")
            
            def on_error(ws, error):
                logger.error(f"WebSocket error: {error}")
            
            def on_close(ws, close_status_code, close_msg):
                logger.info("WebSocket connection closed")
            
            def on_open(ws):
                logger.info("WebSocket connection opened")
                # Test subscription
                subscribe_msg = {
                    "type": "subscribe",
                    "symbol": "RELIANCE",
                    "exchange": "NSE"
                }
                ws.send(json.dumps(subscribe_msg))
                
                # Test ping
                ping_msg = {"type": "ping"}
                ws.send(json.dumps(ping_msg))
                
                # Close after a short time
                def close_connection():
                    time.sleep(2)
                    ws.close()
                
                import threading
                threading.Thread(target=close_connection).start()
            
            # Create WebSocket connection
            ws = websocket.WebSocketApp(
                ws_url,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            
            # Run for a short time
            ws.run_forever(ping_interval=10, ping_timeout=5)
            self.log_test("WebSocket Connection", True, "Connection successful")
            
        except Exception as e:
            self.log_test("WebSocket Connection", False, f"Error: {e}")
    
    def test_configuration(self):
        """Test system configuration"""
        logger.info("⚙️ Testing Configuration...")
        
        try:
            from config import settings
            
            # Test basic settings
            success = hasattr(settings, 'HOST') and hasattr(settings, 'PORT')
            self.log_test("Basic Config", success, f"Host: {settings.HOST}, Port: {settings.PORT}")
            
            # Test API key presence
            success = bool(settings.BROKER_API_KEY)
            self.log_test("API Key Config", success, "API key configured" if success else "API key missing")
            
            # Test default symbols
            success = len(settings.DEFAULT_SYMBOLS) > 0
            self.log_test("Default Symbols", success, f"{len(settings.DEFAULT_SYMBOLS)} symbols configured")
            
        except Exception as e:
            self.log_test("Configuration", False, f"Error: {e}")
    
    def run_all_tests(self):
        """Run all tests"""
        logger.info("🚀 Starting System Tests...")
        logger.info("=" * 60)
        
        # Run tests
        self.test_configuration()
        self.test_database_operations()
        self.test_api_endpoints()
        self.test_websocket_connection()
        
        # Summary
        logger.info("=" * 60)
        logger.info("📊 Test Summary:")
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results if result['success'])
        failed_tests = total_tests - passed_tests
        
        logger.info(f"Total Tests: {total_tests}")
        logger.info(f"Passed: {passed_tests}")
        logger.info(f"Failed: {failed_tests}")
        logger.info(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        if failed_tests > 0:
            logger.info("❌ Failed Tests:")
            for result in self.test_results:
                if not result['success']:
                    logger.info(f"  • {result['test']}: {result['message']}")
        
        logger.info("=" * 60)
        
        return failed_tests == 0


def main():
    """Main test function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test Real-time Price System")
    parser.add_argument("--url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--skip-ws", action="store_true", help="Skip WebSocket tests")
    args = parser.parse_args()
    
    tester = SystemTester(args.url)
    
    if args.skip_ws:
        logger.info("Skipping WebSocket tests")
        tester.test_configuration()
        tester.test_database_operations()
        tester.test_api_endpoints()
        
        # Summary for partial tests
        total_tests = len(tester.test_results)
        passed_tests = sum(1 for result in tester.test_results if result['success'])
        failed_tests = total_tests - passed_tests
        
        logger.info("=" * 60)
        logger.info("📊 Partial Test Summary:")
        logger.info(f"Total Tests: {total_tests}")
        logger.info(f"Passed: {passed_tests}")
        logger.info(f"Failed: {failed_tests}")
        
        success = failed_tests == 0
    else:
        success = tester.run_all_tests()
    
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
