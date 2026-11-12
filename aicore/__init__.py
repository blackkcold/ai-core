"""AI Core: shared, opt-in model and search integration primitives."""

__version__ = "1.1.0"

from .registry import get_provider, list_providers
from .settings import Settings

__all__ = ["Settings", "get_provider", "list_providers", "__version__"]
