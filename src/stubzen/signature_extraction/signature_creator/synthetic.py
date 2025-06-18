import logging
from typing import Type, Optional, Any, get_type_hints

from ..dataclasses import SignatureInfo
from .base import SignatureCreator
from ...utils.ast import extract_init_type_annotations

logger = logging.getLogger(__name__)

class SyntheticPropertySignatureCreator(SignatureCreator):
    """Creates signatures for synthetic properties with enhanced type precedence"""

    def can_handle(self, obj, context: dict) -> bool:
        return hasattr(obj, 'var_name') and hasattr(obj, 'resolved_type')

    def create_signature(self, name: str, obj, defining_class: Type, context: dict) -> Optional[SignatureInfo]:
        # Use class-specific type hints with proper precedence
        target_class = context.get('target_class', defining_class)
        class_specific_hints = self._get_class_specific_type_hints(target_class, name)

        # Priority: 1) Class-specific hints, 2) Resolved type, 3) Fallback
        if class_specific_hints:
            member_type = class_specific_hints
            self.type_resolver.track_type(member_type)
            formatted_type = self.type_resolver.format_type(member_type)
        elif hasattr(obj, 'resolved_type') and obj.resolved_type:
            member_type = obj.resolved_type
            self.type_resolver.track_type(member_type)
            formatted_type = self.type_resolver.format_type(member_type)
        else:
            # Fall back to type hints or Any
            type_hints = context.get('type_hints', {})
            member_type = type_hints.get(name, Any)
            self.type_resolver.track_type(member_type)
            formatted_type = self.type_resolver.format_type(member_type)

        raw_signature = f"{name}: {formatted_type}"

        return SignatureInfo(
            name=name,
            signature_type="property",
            raw_signature=raw_signature,
            return_type=member_type
        )

    def _get_class_specific_type_hints(self, cls: Type, attribute_name: str) -> Optional[Type]:
        """Get type hints specifically from this class, not inherited ones"""
        try:
            # Check if this class has annotations for this attribute
            if hasattr(cls, '__annotations__') and attribute_name in cls.__annotations__:
                annotation = cls.__annotations__[attribute_name]

                # Try to resolve the annotation using get_type_hints for this specific class
                try:
                    resolved_hints = get_type_hints(cls)
                    if attribute_name in resolved_hints:
                        return resolved_hints[attribute_name]
                except (NameError, AttributeError):
                    # Fallback to raw annotation
                    return annotation

            # Check if defined in __init__ method
            if hasattr(cls, '__init__'):
                init_source = extract_init_type_annotations(cls, attribute_name)
                if init_source:
                    return init_source

        except Exception:
            pass

        return None