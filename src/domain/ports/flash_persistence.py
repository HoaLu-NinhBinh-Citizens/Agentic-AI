"""Flash Transaction Persistence Port.

Defines the abstract interface for flash transaction storage.
Follows Clean Architecture: domain defines the port, infrastructure implements it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..hardware.flash.flash_transaction import FlashTransaction, TransactionStatus


class FlashTransactionStore(ABC):
    """Abstract interface for flash transaction persistence.
    
    Domain layer defines this port; infrastructure implements it.
    This allows the domain to be independent of the persistence technology.
    """
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the store (create tables, open connections, etc.)."""
        ...
    
    @abstractmethod
    async def close(self) -> None:
        """Close the store (close connections, cleanup)."""
        ...
    
    @abstractmethod
    async def save_transaction(self, transaction: FlashTransaction) -> None:
        """Save or update a flash transaction.
        
        Args:
            transaction: The transaction to save.
        """
        ...
    
    @abstractmethod
    async def load_transaction(self, transaction_id: str) -> FlashTransaction | None:
        """Load a transaction by ID.
        
        Args:
            transaction_id: The transaction ID to load.
            
        Returns:
            The transaction if found, None otherwise.
        """
        ...
    
    @abstractmethod
    async def get_pending_transaction(
        self,
        target_name: str,
    ) -> FlashTransaction | None:
        """Get pending transaction for target (for resume detection).
        
        Args:
            target_name: The target name to query.
            
        Returns:
            The pending transaction if found, None otherwise.
        """
        ...
    
    @abstractmethod
    async def list_transactions(
        self,
        target_name: str | None = None,
        status: TransactionStatus | None = None,
        limit: int = 100,
    ) -> list[FlashTransaction]:
        """List transactions with optional filters.
        
        Args:
            target_name: Optional filter by target name.
            status: Optional filter by status.
            limit: Maximum number of results.
            
        Returns:
            List of matching transactions.
        """
        ...
