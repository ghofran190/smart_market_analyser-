# utils/__init__.py
from utils.logger import get_logger

logger = get_logger(__name__)

__all__ = ['logger', 'get_logger']