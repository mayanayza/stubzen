import inspect
from typing import Type, Optional, Any

from ..dataclasses import SignatureInfo
from .base import SignatureCreator


class PropertySignatureCreator(SignatureCreator):
    """Creates signatures for properties"""

    def can_handle(self, obj, context: dict) -> bool:
        return isinstance(obj, property)

    def create_signature(self, name: str, obj, defining_class: Type, context: dict) -> Optional[SignatureInfo]:
        member_type = context.get('type_hints', {}).get(name)

        if member_type is None and obj.fget:
            try:
                sig = inspect.signature(obj.fget)
                if sig.return_annotation != inspect.Parameter.empty:
                    member_type = sig.return_annotation
            except Exception:
                pass

        if member_type is None:
            member_type = Any

        self.type_resolver.track_type(member_type)
        raw_signature = f"{name}: {self.type_resolver.format_type(member_type)}"

        signature_type = "protocol_property" if context.get('is_protocol', False) else "property"

        return SignatureInfo(
            name=name,
            signature_type=signature_type,
            raw_signature=raw_signature,
            return_type=member_type
        )
