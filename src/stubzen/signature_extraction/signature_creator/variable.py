import inspect
import logging
from typing import Type, Optional, Any

from ..dataclasses import SignatureInfo
from .base import SignatureCreator

logger = logging.getLogger(__name__)

class VariableSignatureCreator(SignatureCreator):
    """Creates signatures for class variables"""

    def can_handle(self, obj, context: dict) -> bool:
        return (not callable(obj) and
                not inspect.isclass(obj) and
                not isinstance(obj, property) and
                not hasattr(obj, '__get__'))

    def create_signature(self, name: str, obj, defining_class: Type, context: dict) -> Optional[SignatureInfo]:
        # Skip ABC internal attributes
        if name.startswith('_abc_'):
            return None

        # Get the type hint - this is the key fix!
        type_hints = context.get('type_hints', {})
        member_type = type_hints.get(name)

        # IMPORTANT: For class variables, always prioritize type annotations over object values
        # This is especially important for TypeVar bound classes where values might be NotImplemented
        if member_type is None:
            # Check if this class has type annotations for this attribute
            if hasattr(defining_class, '__annotations__') and name in defining_class.__annotations__:
                member_type = defining_class.__annotations__[name]
                self.type_resolver.track_type(member_type)
                formatted_type = self.type_resolver.format_type(member_type)
            elif obj is not None and obj is not NotImplemented:
                # Only use object value if no annotation and object is meaningful
                member_type = type(obj)
                self.type_resolver.track_type(member_type)
                formatted_type = self.type_resolver.format_type(member_type)
            else:
                # Last resort fallback
                member_type = Any
                formatted_type = "Any"
        else:
            # Use the resolved type hint (this should be the common case now)
            self.type_resolver.track_type(member_type)
            formatted_type = self.type_resolver.format_type(member_type)

        raw_signature = f"{name}: {formatted_type}"

        return SignatureInfo(
            name=name,
            signature_type="class_variable",
            raw_signature=raw_signature,
            return_type=member_type
        )