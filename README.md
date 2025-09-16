# 🚀 Kalpi Capital - Real-time Price System

A high-performance real-time financial data pipeline with Angel Broking integration, built with FastAPI and DuckDB.

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.116+-green.svg)](https://fastapi.tiangolo.com)
[![DuckDB](https://img.shields.io/badge/DuckDB-1.3+-yellow.svg)](https://duckdb.org)
[![License](https://img.shields.io/badge/License-MIT-red.svg)](LICENSE)
[![GitHub](https://img.shields.io/badge/GitHub-Repository-black.svg)](https://github.com/DeepanshuTIET/kalpi-capital)

## 📋 Table of Contents

- [Features](#-features)
- [Architecture](#-architecture)
- [Quick Start](#-quick-start)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [API Documentation](#-api-documentation)
- [WebSocket API](#-websocket-api)
- [Web Interface](#-web-interface)
- [Testing](#-testing)
- [Project Structure](#-project-structure)
- [Contributing](#-contributing)
- [License](#-license)

## ✨ Features

### 🔄 Real-time Data Streaming
- **Live Price Updates**: Real-time streaming from Angel Broking API
- **WebSocket Support**: Bi-directional communication for instant updates
- **Market Data**: OHLC, volume, OI, bid/ask spreads
- **Multi-symbol Support**: Track multiple stocks simultaneously

### 🗄️ High-Performance Database
- **DuckDB Integration**: Fast columnar database for time-series data
- **Optimized Storage**: Efficient tick data storage and retrieval
- **Historical Data**: Query price history with various time intervals
- **Data Retention**: Configurable data cleanup policies

### 🌐 REST API
- **FastAPI Framework**: Modern, fast web framework
- **Auto Documentation**: Swagger UI and ReDoc integration
- **CORS Support**: Cross-origin resource sharing enabled
- **Health Monitoring**: System health and status endpoints

### 📊 Web Interface
- **Modern UI**: Beautiful dashboard with DaisyUI components
- **Real-time Charts**: Interactive price charts with Chart.js
- **Market Overview**: Live market status and statistics
- **Responsive Design**: Mobile-friendly interface

### 🔐 Security & Authentication
- **Secure Token Management**: JWT-based authentication
- **Environment Variables**: Secure configuration management
- **API Rate Limiting**: Protection against abuse
- **TOTP Support**: Two-factor authentication

## 🏗️ Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Angel Broker  │───▶│  Price Streamer  │───▶│   DuckDB Store  │
│      API        │    │   (WebSocket)    │    │   (Time Series) │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │
                                ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  Web Interface  │◀───│   FastAPI App    │───▶│   REST Clients  │
│   (Dashboard)   │    │  (HTTP/WebSocket)│    │   (External)    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

### Key Components

- **Price Streamer**: Handles real-time data ingestion from Angel Broker
- **Database Layer**: DuckDB for high-performance time-series storage
- **API Layer**: FastAPI for REST endpoints and WebSocket connections
- **Web Interface**: Modern dashboard for data visualization
- **Authentication**: Secure broker authentication and session management

## 🚀 Quick Start

### Prerequisites

- Python 3.12+
- Angel Broking API credentials
- Git

### 1-Minute Setup

```bash
# Clone the repository
git clone https://github.com/DeepanshuTIET/kalpi-capital.git
cd kalpi-capital

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp env_example.txt .env
# Edit .env with your API credentials

# Start the server
python main.py
```

🎉 **Server running at**: http://localhost:8000

## 📦 Installation

### Detailed Installation

1. **Clone Repository**
   ```bash
   git clone https://github.com/DeepanshuTIET/kalpi-capital.git
   cd kalpi-capital
   ```

2. **Setup Virtual Environment**
   ```bash
   python -m venv venv
   
   # Activate virtual environment
   # On Windows:
   venv\Scripts\activate
   
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Configuration**
   ```bash
   cp env_example.txt .env
   ```

### System Requirements

- **Python**: 3.12 or higher
- **Memory**: 4GB RAM minimum (8GB recommended)
- **Storage**: 10GB free space for data storage
- **Network**: Stable internet connection for API access

## ⚙️ Configuration

### Environment Variables

Create a `.env` file in the project root:

```env
# Angel Broker API Configuration
BROKER_API_KEY=your_angel_api_key_here

# Server Configuration
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=info
RELOAD=false

# Database Configuration
DB_PATH=prices.db
DB_CLEANUP_DAYS=30

# Streaming Configuration
MIN_UPDATE_INTERVAL=1.0
RECONNECT_DELAY=5
MAX_RECONNECT_ATTEMPTS=10
```

### Angel Broker Setup

1. **Get API Key**
   - Visit [Angel Broker SmartAPI](https://smartapi.angelbroking.com/)
   - Login to your account
   - Navigate to "My Profile" > "API" section
   - Generate your API key

2. **Required Information**
   - **CLIENT_CODE**: Your broker client code (e.g., AB12345)
   - **PIN**: Your 4-6 digit trading PIN
   - **TOTP**: 6-digit code from authenticator app

### Default Symbols

The system tracks these symbols by default:
- **Stocks**: RELIANCE, TCS, INFY, ICICIBANK, SBIN
- **Indices**: NIFTY, SENSEX

Modify `config.py` to customize the symbol list.

## 📚 API Documentation

### REST Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | API information |
| `/health` | GET | System health check |
| `/market/status` | GET | Market status and statistics |
| `/price/{symbol}` | GET | Current price for symbol |
| `/history/{symbol}` | GET | Historical price data |
| `/auth/login` | POST | Broker authentication |
| `/auth/status` | GET | Authentication status |
| `/streaming/start` | POST | Start price streaming |
| `/streaming/stop` | POST | Stop price streaming |
| `/streaming/symbols` | GET | Get tracked symbols |

### Interactive Documentation

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Example API Calls

```bash
# Get current price
curl "http://localhost:8000/price/RELIANCE?exchange=NSE"

# Get historical data
curl "http://localhost:8000/history/RELIANCE?exchange=NSE&days=7"

# Market status
curl "http://localhost:8000/market/status"
```

## 🔌 WebSocket API

### Connection

```javascript
const ws = new WebSocket('ws://localhost:8000/ws');
```

### Message Types

#### Subscribe to Symbol
```json
{
  "type": "subscribe",
  "symbol": "RELIANCE",
  "exchange": "NSE"
}
```

#### Unsubscribe from Symbol
```json
{
  "type": "unsubscribe", 
  "symbol": "RELIANCE",
  "exchange": "NSE"
}
```

#### Price Update (Received)
```json
{
  "type": "price_update",
  "symbol": "RELIANCE",
  "exchange": "NSE",
  "data": {
    "ltp": 2450.50,
    "open": 2445.00,
    "high": 2455.75,
    "low": 2440.25,
    "volume": 1234567,
    "timestamp": "2025-09-16T10:30:00Z"
  }
}
```

### JavaScript Example

```javascript
const ws = new WebSocket('ws://localhost:8000/ws');

ws.onopen = function() {
    // Subscribe to RELIANCE
    ws.send(JSON.stringify({
        type: 'subscribe',
        symbol: 'RELIANCE',
        exchange: 'NSE'
    }));
};

ws.onmessage = function(event) {
    const data = JSON.parse(event.data);
    if (data.type === 'price_update') {
        console.log(`${data.symbol}: ₹${data.data.ltp}`);
    }
};
```

## 🌐 Web Interface

### Dashboard Features

- **Live Price Grid**: Real-time price updates for all tracked symbols
- **Interactive Charts**: Candlestick and line charts with zoom/pan
- **Market Statistics**: Volume, turnover, and market breadth
- **Symbol Search**: Quick search and filtering
- **Dark/Light Theme**: Toggle between themes

### Access the Dashboard

Open http://localhost:8000/static/index.html in your browser.

### Mobile Support

The web interface is fully responsive and works on:
- Desktop browsers (Chrome, Firefox, Safari, Edge)
- Mobile browsers (iOS Safari, Android Chrome)
- Tablet devices

## 🧪 Testing

### Run System Tests

```bash
# Run all tests
python test_system.py

# Test specific components
python test_system.py --skip-ws  # Skip WebSocket tests

# Test with custom URL
python test_system.py --url http://localhost:8000
```

### Test Coverage

The test suite covers:
- ✅ Database operations (CRUD, indexing)
- ✅ REST API endpoints (all routes)
- ✅ WebSocket connections (subscribe/unsubscribe)
- ✅ Configuration validation
- ✅ Authentication flow
- ✅ Error handling

### Manual Testing

1. **Start the server**: `python main.py`
2. **Open browser**: http://localhost:8000/docs
3. **Test endpoints**: Use Swagger UI to test API calls
4. **WebSocket test**: Open static/index.html for live updates

## 📁 Project Structure

```
kalpi-capital/
├── 📁 broker/                    # Broker integrations
│   └── 📁 angel/                 # Angel Broker plugin
│       ├── 📁 api/               # API endpoints
│       ├── 📁 database/          # Database operations
│       ├── 📁 mapping/           # Data transformations
│       ├── 📁 streaming/         # WebSocket streaming
│       └── 📁 utils/             # Helper utilities
├── 📁 database/                  # Database modules
│   ├── auth_db.py               # Authentication storage
│   ├── symbol.py                # Symbol management
│   └── token_db.py              # Token storage
├── 📁 realtime_prices/          # Core price system
│   ├── api.py                   # FastAPI application
│   ├── database.py              # Price database
│   └── streamer.py              # Real-time streaming
├── 📁 static/                   # Web interface
│   └── index.html               # Dashboard
├── 📁 utils/                    # Shared utilities
│   ├── httpx_client.py          # HTTP client
│   └── logging.py               # Logging setup
├── 📁 websocket_proxy/          # WebSocket handling
├── 📄 config.py                 # Configuration
├── 📄 main.py                   # Application entry point
├── 📄 requirements.txt          # Dependencies
└── 📄 test_system.py            # Test suite
```

### Key Files

- **`main.py`**: Application entry point and server startup
- **`config.py`**: Configuration management with environment variables
- **`realtime_prices/api.py`**: FastAPI application with REST endpoints
- **`realtime_prices/database.py`**: DuckDB integration for price storage
- **`realtime_prices/streamer.py`**: Real-time data streaming logic
- **`test_system.py`**: Comprehensive test suite

## 🔧 Development

### Setup Development Environment

```bash
# Install development dependencies
pip install -r requirements.txt

# Install optional development tools
pip install pytest pytest-asyncio black flake8

# Format code
black .

# Lint code
flake8 .

# Run tests
pytest
```

### Adding New Features

1. **New Broker**: Add to `broker/` directory
2. **New Endpoints**: Extend `realtime_prices/api.py`
3. **Database Changes**: Modify `realtime_prices/database.py`
4. **UI Updates**: Edit `static/index.html`

### Debugging

- **Logs**: Check `logs/` directory for application logs
- **Database**: Use DuckDB CLI to inspect `prices.db`
- **API**: Use `/health` endpoint for system status

## 🤝 Contributing

We welcome contributions! Please see our contributing guidelines:

### Getting Started

1. Fork the repository: [https://github.com/DeepanshuTIET/kalpi-capital](https://github.com/DeepanshuTIET/kalpi-capital)
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass: `python test_system.py`
6. Submit a pull request

### Code Standards

- Follow PEP 8 style guidelines
- Add docstrings to all functions and classes
- Include tests for new features
- Update documentation as needed

## 📞 Support

### Common Issues

**Q: Authentication fails**
A: Verify your API key, client code, and TOTP code are correct.

**Q: No price updates**
A: Check your internet connection and broker API status.

**Q: Database errors**
A: Ensure sufficient disk space and write permissions.

### Getting Help

- **Issues**: Report bugs on [GitHub Issues](https://github.com/DeepanshuTIET/kalpi-capital/issues)
- **Discussions**: Join our [GitHub Discussions](https://github.com/DeepanshuTIET/kalpi-capital/discussions)
- **Documentation**: Check the `/docs` endpoint

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Angel Broking**: For providing the market data API
- **FastAPI**: For the excellent web framework
- **DuckDB**: For high-performance analytics database
- **OpenAlgo**: For broker integration patterns

---

**Built with ❤️ by Kalpi Capital**

*Real-time financial data pipeline for modern trading systems*