import re
from typing import Set, Type, Any, get_origin, get_args, Union

from ..config import StubzenConfig
from ..constants import TYPING_CONSTRUCTS

class TypeResolver:
    """Handles type resolution and formatting for stub file with enhanced forward reference tracking"""

    def __init__(self):
        self.used_types: Set[Type] = set()
        self.string_type_references: Set[str] = set()
        self.forward_references: Set[str] = set()
        self.complex_type_expressions: Set[str] = set()

    def clear(self):
        """Clear all tracked types"""
        self.used_types.clear()
        self.string_type_references.clear()
        self.forward_references.clear()
        self.complex_type_expressions.clear()

    def track_type(self, type_obj):
        """Track a type object for import generation with enhanced categorization"""
        if type_obj and type_obj != Any and type_obj is not type(None):
            try:
                self.used_types.add(type_obj)

                # Also track the module for better import resolution
                if hasattr(type_obj, '__module__') and hasattr(type_obj, '__name__'):
                    module_name = type_obj.__module__
                    class_name = type_obj.__name__

                    # Track forward references from project modules
                    if not StubzenConfig().is_excluded_module(module_name):
                        self.forward_references.add(f"{module_name}.{class_name}")

            except TypeError:
                type_str = str(type_obj)

                # Categorize string types better
                if isinstance(type_obj, str):
                    if self._is_complex_type_expression(type_obj):
                        self.complex_type_expressions.add(type_obj)
                        # Extract individual type names from complex expressions
                        self._extract_types_from_complex_string(type_obj)
                    else:
                        self.string_type_references.add(type_obj.strip("'\""))
                else:
                    self.string_type_references.add(type_str)

    def format_type(self, type_annotation) -> str:
        """Format type annotation for stub file"""
        if type_annotation is None or type_annotation is type(None):
            return "None"

        if type_annotation is Any:
            return "Any"

        if isinstance(type_annotation, str):
            if self._is_dotted_name(type_annotation):
                return self._format_dotted_name(type_annotation)
            elif self._is_complex_type_expression(type_annotation):
                self._extract_types_from_complex_string(type_annotation)
                return type_annotation
            else:
                clean_name = type_annotation.strip("'\"")
                self.string_type_references.add(clean_name)
                if type_annotation.startswith("'") and type_annotation.endswith("'"):
                    return type_annotation
                else:
                    return f"'{clean_name}'"

        if hasattr(type_annotation, '__forward_arg__'):
            forward_arg = type_annotation.__forward_arg__
            self.string_type_references.add(forward_arg)
            return f"'{forward_arg}'"

        self.track_type(type_annotation)

        origin = get_origin(type_annotation)
        if origin is not None:
            return self._format_generic_type(type_annotation, origin)

        if hasattr(type_annotation, '__name__'):
            return type_annotation.__name__

        return str(type_annotation)

    def _is_dotted_name(self, type_str: str) -> bool:
        clean_str = type_str.strip("'\"")
        return ('.' in clean_str and not '[' in clean_str and not ' ' in clean_str)

    def _format_dotted_name(self, type_str: str) -> str:
        clean_str = type_str.strip("'\"")
        parts = clean_str.split('.')
        if len(parts) == 2:
            module_name, class_name = parts
            return class_name
        return f"'{clean_str}'"

    def _is_complex_type_expression(self, type_str: str) -> bool:
        return '[' in type_str and ']' in type_str

    def _extract_types_from_complex_string(self, type_str: str):
        """Extract types from complex type expressions"""
        # Extract quoted types
        quoted_types = re.findall(r"'([^']+)'", type_str)
        for quoted_type in quoted_types:
            clean_type = quoted_type.strip()
            if '.' in clean_type:
                # Handle module.Class references
                parts = clean_type.split('.')
                if len(parts) == 2:
                    module_name, class_name = parts
                    if not StubzenConfig().is_excluded_module(module_name):
                        self.forward_references.add(f"{module_name}.{class_name}")
                    else:
                        self.string_type_references.add(class_name)
                else:
                    self.string_type_references.add(clean_type)
            else:
                self.string_type_references.add(clean_type)

        # Extract unquoted types (but not typing constructs)
        unquoted_types = re.findall(r'\b[A-Z][a-zA-Z0-9_]*\b', type_str)

        for unquoted_type in unquoted_types:
            if unquoted_type not in TYPING_CONSTRUCTS:
                self.string_type_references.add(unquoted_type)

    def _format_generic_type(self, type_annotation, origin) -> str:
        args = get_args(type_annotation)

        if origin is list:
            if args:
                return f"List[{self.format_type(args[0])}]"
            return "List[Any]"
        elif origin is dict:
            if len(args) >= 2:
                return f"Dict[{self.format_type(args[0])}, {self.format_type(args[1])}]"
            return "Dict[Any, Any]"
        elif origin is type:
            if args:
                return f"Type[{self.format_type(args[0])}]"
            return "Type[Any]"
        elif origin is Union:
            if len(args) == 2 and type(None) in args:
                non_none_type = args[0] if args[1] is type(None) else args[1]
                return f"Optional[{self.format_type(non_none_type)}]"
            else:
                formatted_args = [self.format_type(arg) for arg in args]
                return f"Union[{', '.join(formatted_args)}]"

        origin_name = getattr(origin, '__name__', str(origin))
        if args:
            formatted_args = [self.format_type(arg) for arg in args]
            return f"{origin_name}[{', '.join(formatted_args)}]"
        return origin_name