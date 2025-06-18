import logging
from typing import Optional, Type, Dict, List, get_type_hints, Any

from .dataclasses import MissingAnnotation, SignatureInfo
from .member_processor.init import InitMemberProcessor
from .member_processor.standard import StandardMemberProcessor
from .signature_creator.method import MethodSignatureCreator
from .signature_creator.property import PropertySignatureCreator
from .signature_creator.synthetic import SyntheticPropertySignatureCreator
from .signature_creator.variable import VariableSignatureCreator
from .type_resolver import TypeResolver

logger = logging.getLogger(__name__)


class SignatureExtractor:
    """Extract method signatures from classes with enhanced type precedence and missing annotation detection"""

    def __init__(self, log_missing_types: bool = False):
        self.log_missing_types = log_missing_types
        self.missing_annotations: List[MissingAnnotation] = []
        self.type_resolver = TypeResolver()

        # Initialize signature creators
        self.signature_creators = [
            MethodSignatureCreator(self.type_resolver, logger),
            PropertySignatureCreator(self.type_resolver, logger),
            SyntheticPropertySignatureCreator(self.type_resolver, logger),
            VariableSignatureCreator(self.type_resolver, logger),
        ]

        # Initialize member processors
        self.member_processors = {
            'standard': StandardMemberProcessor(),
            'init': InitMemberProcessor(),
        }

    def clear_state(self):
        """Clear all state for a new extraction"""
        self.missing_annotations.clear()
        self.type_resolver.clear()

    def extract_class_signature(self, cls: Type, include_inherited: bool = False,
                                source_class_name: str = None) -> List[SignatureInfo]:
        """Extract all signatures from a class with enhanced type precedence"""
        try:
            signatures = []
            seen_names = set()

            # Get type hints with proper precedence
            type_hints = self._get_type_hints(cls, include_inherited)

            # If we're processing TypeVar bounds, get their type hints with HIGHEST precedence
            if include_inherited:
                member_processor = self.member_processors['standard']
                if hasattr(member_processor, '_get_typevar_bounds'):
                    typevar_bounds = member_processor._get_typevar_bounds(cls)

                    # Process TypeVar bounds FIRST to get their complete type information
                    for bound_class in typevar_bounds:
                        # Get type hints from the bound class with full inheritance
                        bound_type_hints = self._get_type_hints(bound_class, include_inherited=True)

                        # TypeVar bound type hints should override everything
                        for name, hint in bound_type_hints.items():
                            # Only override if we don't have a good type or current type is Any
                            current_type = type_hints.get(name)
                            if current_type is None or current_type == Any or str(current_type) == 'typing.Any':
                                type_hints[name] = hint
                                logger.debug(f"Using TypeVar bound type for {name}: {hint}")

            # Create enhanced context
            context = {
                'type_hints': type_hints,
                'include_inherited': include_inherited,
                'target_class': cls,
                'target_class_name': cls.__name__,
                'missing_annotations': self.missing_annotations
            }

            # Get members from different sources
            members_to_process = []

            # Standard members
            standard_members = self.member_processors['standard'].get_members(cls, include_inherited, context)
            members_to_process.extend(standard_members)

            # Init members
            init_members = self.member_processors['init'].get_members(cls, include_inherited, context)
            members_to_process.extend(init_members)

            # Also process init members from TypeVar bounds
            if include_inherited and hasattr(self.member_processors['standard'], '_get_typevar_bounds'):
                typevar_bounds = self.member_processors['standard']._get_typevar_bounds(cls)

                for bound_class in typevar_bounds:
                    # Get comprehensive type hints for the bound class
                    bound_type_hints = self._get_type_hints(bound_class, include_inherited=True)

                    # Extract init members from the bound class
                    bound_init_members = self.member_processors['init']._extract_from_init(bound_class,
                                                                                           bound_type_hints)

                    # Add these members if not already seen
                    for name, obj, defining_class in bound_init_members:
                        if name not in seen_names:
                            members_to_process.append((name, obj, defining_class))

            # Process all members
            for name, obj, defining_class in members_to_process:
                if name in seen_names:
                    continue

                # Find appropriate signature creator
                sig_info = self._create_signature(name, obj, defining_class, context)
                if sig_info:
                    sig_info.source_class = defining_class.__name__
                    signatures.append(sig_info)
                    seen_names.add(name)

            return signatures

        except Exception as e:
            logger.error(f"Error extracting signatures from {cls.__name__}: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _create_signature(self, name: str, obj, defining_class: Type, context: dict) -> Optional[SignatureInfo]:
        """Create signature using appropriate creator"""
        for creator in self.signature_creators:
            if creator.can_handle(obj, context):
                return creator.create_signature(name, obj, defining_class, context)
        return None

    def _get_type_hints(self, cls: Type, include_inherited: bool) -> Dict[str, Type]:
        """Get type hints with proper precedence - current class overrides inherited"""
        type_hints = {}

        if include_inherited:
            # Start with inherited classes (lower precedence)
            classes_to_check = [base for base in cls.__mro__[1:] if base.__name__ != 'object']
            classes_to_check.reverse()  # Process from most distant to closest

            for check_cls in classes_to_check:
                inherited_hints = self._get_direct_type_hints(check_cls)
                type_hints.update(inherited_hints)

        # Current class annotations take precedence
        current_class_hints = self._get_direct_type_hints(cls)
        type_hints.update(current_class_hints)

        return type_hints

    def _get_direct_type_hints(self, cls: Type) -> Dict[str, Type]:
        """Get type hints directly from a class (no inheritance)"""
        type_hints = {}

        try:
            # Try get_type_hints first for resolved types
            resolved_hints = get_type_hints(cls)
            type_hints.update(resolved_hints)
        except (NameError, AttributeError):
            # Fallback to raw annotations
            if hasattr(cls, '__annotations__'):
                type_hints.update(cls.__annotations__)
        except Exception:
            # Silent fallback
            if hasattr(cls, '__annotations__'):
                type_hints.update(cls.__annotations__)

        return type_hints

    def get_missing_annotations_report(self) -> str:
        """Generate missing annotations report"""
        if not self.missing_annotations:
            return "✅ No missing type annotations found!"

        report = [
            "\n" + "=" * 60,
            "MISSING TYPE ANNOTATIONS SUMMARY",
            "=" * 60
        ]

        # Group by module and class
        by_module = {}
        for annotation in self.missing_annotations:
            module = annotation.class_module
            if module not in by_module:
                by_module[module] = {}
            if annotation.class_name not in by_module[module]:
                by_module[module][annotation.class_name] = []
            by_module[module][annotation.class_name].append(annotation)

        # Generate detailed report
        for module_name in sorted(by_module.keys()):
            report.append(f"\n📂 {module_name}:")
            for class_name in sorted(by_module[module_name].keys()):
                annotations = by_module[module_name][class_name]
                report.append(f"   📄 {class_name}:")

                # Group by type for better organization
                by_type = {}
                for annotation in annotations:
                    member_type = annotation.member_type
                    if member_type not in by_type:
                        by_type[member_type] = []
                    by_type[member_type].append(annotation)

                for member_type in sorted(by_type.keys()):
                    type_annotations = by_type[member_type]
                    report.append(f"      {member_type}:")
                    for annotation in type_annotations:
                        details = f" - {annotation.details}" if annotation.details else ""
                        report.append(f"        • {annotation.member_name}{details}")

        report.extend([
            f"\n📊 Total missing annotations: {len(self.missing_annotations)}",
            "=" * 60
        ])

        return "\n".join(report)