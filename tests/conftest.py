import pytest
import logging
import sys
from datetime import datetime
from starlette.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from server import build_app, Settings


class ExceptionLoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, logger):
        super().__init__(app)
        self.logger = logger
    
    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
        except Exception as e:
            self.logger.error(f"Exception in {request.method} {request.url}: {type(e).__name__}: {e}", exc_info=True)
            raise


@pytest.fixture(scope="function")
def client():
    """Fixture providing TestClient following ws-tests pattern."""
    # Configure logging to write to file
    log_filename = f"test_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    
    # Clear any existing handlers
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    
    # Set up file and console logging
    file_handler = logging.FileHandler(log_filename)
    console_handler = logging.StreamHandler(sys.stdout)
    
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # Configure logger for exceptions
    logger = logging.getLogger("test_exceptions")
    logger.setLevel(logging.ERROR)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    settings = Settings(redis_url="redis://localhost:6379/0", ttl=60 * 60)
    app = build_app(settings)
    
    # Add exception logging middleware
    app.add_middleware(ExceptionLoggingMiddleware, logger=logger)
    
    with TestClient(app) as client:
        yield client

