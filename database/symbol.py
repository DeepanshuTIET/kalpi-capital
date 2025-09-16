"""
Symbol token database model for compatibility with existing code.
Simplified version for the real-time price system.
"""
from sqlalchemy import Column, Integer, String, Float, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

class SymToken(Base):
    """Symbol token model"""
    __tablename__ = 'symtoken'
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String, nullable=False, index=True)
    brsymbol = Column(String, nullable=False, index=True)
    name = Column(String)
    exchange = Column(String, index=True)
    brexchange = Column(String, index=True)
    token = Column(String, index=True)
    expiry = Column(String)
    strike = Column(Float)
    lotsize = Column(Integer)
    instrumenttype = Column(String)
    tick_size = Column(Float)
    
    # Mock query property for compatibility
    query = None

# Mock database setup for compatibility
engine = None
Session = None

def init_mock_db():
    """Initialize mock database for testing"""
    global engine, Session
    try:
        # Use SQLite in-memory database for compatibility
        engine = create_engine('sqlite:///:memory:', echo=False)
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        
        # Set up mock query property
        session = Session()
        SymToken.query = session.query(SymToken)
        
        return True
    except Exception:
        return False

# Initialize mock database
init_mock_db()
