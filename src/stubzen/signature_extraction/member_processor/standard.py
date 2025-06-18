import inspect
import sys
from typing import Type, List, Optional

from ...constants import BUILTIN_ATTRS, ABC_INTERNALS
from .base import MemberProcessor


class StandardMemberProcessor(MemberProcessor):
    """Processes standard class members with TypeVar support"""

    def get_members(self, cls: Type, include_inherited: bool, context: dict) -> List[tuple]:
        members = []

        if include_inherited:
            classes_to_check = [cls] + [base for base in cls.__mro__[1:] if base.__name__ != 'object']

            # Add TypeVar bounds and prioritize them
            type_var_bounds = self._get_typevar_bounds(cls)
            if type_var_bounds:
                # Add TypeVar bounds FIRST so they take precedence
                classes_to_check = type_var_bounds + classes_to_check
        else:
            classes_to_check = [cls]

        # Remove duplicates while preserving order
        unique_classes = []
        seen_classes = set()
        for check_cls in classes_to_check:
            if check_cls.__name__ not in seen_classes:
                unique_classes.append(check_cls)
                seen_classes.add(check_cls.__name__)

        type_var_bounds = self._get_typevar_bounds(cls) if include_inherited else []

        for check_cls in unique_classes:
            if hasattr(check_cls, '__origin__'):
                continue

            for name, obj in inspect.getmembers(check_cls):
                if self._should_skip_member(name, obj):
                    continue

                # For TypeVar bound classes, include ALL members (since they're the "interface")
                # For regular classes, only include if defined in this specific class
                if check_cls in type_var_bounds:
                    # Include all members from TypeVar bounds, even inherited ones
                    members.append((name, obj, check_cls))
                elif name in getattr(check_cls, '__dict__', {}):
                    members.append((name, obj, check_cls))

        return members

    def _get_typevar_bounds(self, cls: Type) -> List[Type]:
        """Extract TypeVar bounds from generic classes"""
        bounds = []

        # First, check the module for TypeVar definitions
        module = inspect.getmodule(cls)
        if module:
            # Look for TypeVar definitions in the module
            for name, obj in inspect.getmembers(module):
                if hasattr(obj, '__class__') and obj.__class__.__name__ == 'TypeVar':
                    # Check if this TypeVar has a bound
                    if hasattr(obj, '__bound__') and obj.__bound__:
                        bound_class = obj.__bound__

                        # Handle ForwardRef
                        if hasattr(bound_class, '__forward_arg__'):
                            bound_class_name = bound_class.__forward_arg__
                            bound_class = self._resolve_string_to_class(bound_class_name)
                        elif isinstance(bound_class, str):
                            bound_class = self._resolve_string_to_class(bound_class)

                        if bound_class and inspect.isclass(bound_class):
                            bounds.append(bound_class)

        # Check __orig_bases__ for Generic[T] patterns
        if hasattr(cls, '__orig_bases__'):
            for base in cls.__orig_bases__:
                if hasattr(base, '__origin__') and hasattr(base, '__args__'):
                    # Look for Generic[T] patterns
                    if getattr(base.__origin__, '__name__', '') == 'Generic':
                        for arg in base.__args__:
                            if hasattr(arg, '__bound__') and arg.__bound__:
                                # Found a TypeVar with a bound
                                bound_class = arg.__bound__

                                # Handle ForwardRef
                                if hasattr(bound_class, '__forward_arg__'):
                                    bound_class_name = bound_class.__forward_arg__
                                    bound_class = self._resolve_string_to_class(bound_class_name)
                                elif isinstance(bound_class, str):
                                    bound_class = self._resolve_string_to_class(bound_class)

                                if bound_class and inspect.isclass(bound_class):
                                    bounds.append(bound_class)

        return bounds

    def _resolve_string_to_class(self, type_str: str) -> Optional[Type]:
        """Resolve a string class name to an actual class"""
        # Clean the type string
        clean_type_str = type_str.strip("'\"")

        # Look through loaded modules to find this class
        for module_name, module in sys.modules.items():
            if module is None:
                continue

            try:
                if hasattr(module, clean_type_str):
                    attr = getattr(module, clean_type_str)
                    if inspect.isclass(attr):
                        return attr
            except Exception:
                continue
        return None

    def _should_skip_member(self, name: str, obj) -> bool:
        if name.startswith('__') and name not in ['__init__', '__str__', '__repr__']:
            return True

        if name in BUILTIN_ATTRS:
            return True

        if name in ABC_INTERNALS:
            return True

        return False