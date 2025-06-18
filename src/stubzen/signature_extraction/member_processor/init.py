from typing import Type, List, Dict

from .base import MemberProcessor
from ...utils.ast import extract_from_init

class InitMemberProcessor(MemberProcessor):
    """Processes members from __init__ methods using AST parsing with enhanced type resolution"""

    def get_members(self, cls: Type, include_inherited: bool, context: dict) -> List[tuple]:
        signatures = []
        type_hints = context.get('type_hints', {})

        classes_to_check = [cls]
        if include_inherited:
            classes_to_check.extend([base for base in cls.__mro__[1:] if base.__name__ != 'object'])

        for check_cls in classes_to_check:
            init_sigs = self._extract_from_init(check_cls, type_hints)
            signatures.extend(init_sigs)

        return signatures

    def _extract_from_init(self, cls: Type, type_hints: Dict[str, Type]) -> List[tuple]:
        """Extract instance variables from __init__ using AST parsing"""
        return extract_from_init(cls, type_hints)