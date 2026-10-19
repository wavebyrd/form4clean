"""Form4Clean: clean, standardized, research-ready SEC insider trading data."""

__version__ = "0.1.0"

from .client import InsiderData, TransactionSet
from .query import TransactionFilter
from .versions import CLEANING_VERSION, SCHEMA_VERSION

__all__ = [
    "CLEANING_VERSION",
    "SCHEMA_VERSION",
    "InsiderData",
    "TransactionFilter",
    "TransactionSet",
    "__version__",
]
