import logging
from abc import ABC, abstractmethod
from typing import Type, List

logger = logging.getLogger(__name__)

class MemberProcessor(ABC):
    """Base class for processing different types of class members"""

    @abstractmethod
    def get_members(self, cls: Type, include_inherited: bool, context: dict) -> List[tuple]:
        """Get list of (name, obj, defining_class) tuples to process"""
        pass
