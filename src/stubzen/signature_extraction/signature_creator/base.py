import logging
from abc import ABC, abstractmethod
from typing import Type, Optional

from ..dataclasses import SignatureInfo
from ..type_resolver import TypeResolver

logger = logging.getLogger(__name__)

class SignatureCreator(ABC):
    """Base class for creating specific types of signatures"""

    def __init__(self, type_resolver: TypeResolver, logger):
        self.type_resolver = type_resolver
        self.logger = logger

    @abstractmethod
    def can_handle(self, obj, context: dict) -> bool:
        """Check if this creator can handle the given object"""
        pass

    @abstractmethod
    def create_signature(self, name: str, obj, defining_class: Type, context: dict) -> Optional[SignatureInfo]:
        """Create a signature for the given object"""
        pass

    def _format_default_value(self, default) -> str:
        """Format default parameter values"""
        if default is None:
            return " = None"
        elif isinstance(default, str):
            return f' = "{default}"'
        elif isinstance(default, (int, float, bool)):
            return f" = {default}"
        else:
            return " = ..."
