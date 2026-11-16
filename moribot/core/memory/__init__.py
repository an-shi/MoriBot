"""MoriBot-specific MoriMemory integration helpers.

These modules are copied from the MoriMemory repository and depend only on
FastAPI, httpx and loguru, which MoriBot already ships.
"""

from .client import MemoryClient, MemoryRecall
from .proxy import create_memory_proxy_router
from .service_manager import (
    MemoryServiceManager,
    MemoryServiceSettings,
    MemoryServiceStatus,
)

__all__ = [
    "MemoryClient",
    "MemoryRecall",
    "MemoryServiceManager",
    "MemoryServiceSettings",
    "MemoryServiceStatus",
    "create_memory_proxy_router",
]
