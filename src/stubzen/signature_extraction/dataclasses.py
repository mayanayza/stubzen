import logging
from dataclasses import dataclass
from typing import Optional, Type, Dict

logger = logging.getLogger(__name__)

@dataclass
class MissingAnnotation:
    """Represents a missing type annotation"""
    class_name: str
    class_module: str
    member_name: str
    member_type: str
    details: str = ""

    @property
    def unique_key(self) -> str:
        return f"{self.class_name}.{self.member_name}({self.member_type}){self.details}"


@dataclass
class SignatureInfo:
    """Represents a method or property signature with its metadata"""
    name: str
    signature_type: str  # 'method', 'property', 'class_variable', 'protocol_method', 'protocol_property'
    raw_signature: str
    return_type: Optional[Type] = None
    param_types: Dict[str, Type] = None
    details: str = ""
    source_class: Optional[str] = None

    def __post_init__(self):
        if self.param_types is None:
            self.param_types = {}
