"""
Enhanced import generation that works directly with type objects and forward references
"""
import inspect
import re
import sys
from typing import List, Type, Any, Set, get_origin, get_args

from .config import StubzenConfig
from .signature_extraction.dataclasses import SignatureInfo
from .signature_extraction.type_resolver import TypeResolver
from .constants import TYPING_CONSTRUCTS, BUILTIN_MODULES, TYPING_PATTERN

class ImportGenerator:
    """Handles import generation for stub files with enhanced forward reference support"""

    def __init__(self, type_resolver: TypeResolver):
        self.type_resolver = type_resolver
        self.current_package = None
        self.defined_classes = set()

    def set_current_package(self, package_name: str):
        """Set the current package being generated (for package-level stubs)"""
        self.current_package = package_name

    def set_defined_classes(self, class_names: set):
        """Set classes defined in current stub file"""
        self.defined_classes = class_names

    def generate_imports(self, signatures: List[SignatureInfo]) -> str:
        """Generate imports with enhanced forward reference and complex type handling"""
        if not signatures:
            return "\n"

        standard_imports = set()
        typing_imports = set()
        third_party_imports = set()
        type_checking_imports = set()

        # Process types from type resolver with better categorization
        for type_obj in self.type_resolver.used_types:
            self._categorize_type_import(type_obj, standard_imports, typing_imports,
                                       third_party_imports, type_checking_imports)

        # Process forward references explicitly
        if hasattr(self.type_resolver, 'forward_references'):
            for forward_ref in self.type_resolver.forward_references:
                self._categorize_forward_reference(forward_ref, type_checking_imports)

        # Process complex type expressions
        if hasattr(self.type_resolver, 'complex_type_expressions'):
            for complex_expr in self.type_resolver.complex_type_expressions:
                self._extract_imports_from_complex_expression(complex_expr, typing_imports, type_checking_imports)

        # Process string type references
        for type_name in self.type_resolver.string_type_references:
            self._categorize_string_type(type_name, typing_imports, type_checking_imports)

        # Extract typing constructs from signatures
        self._extract_typing_from_signatures(signatures, typing_imports)

        return self._build_import_statements(standard_imports, typing_imports,
                                           third_party_imports, type_checking_imports)

    def _categorize_forward_reference(self, forward_ref: str, type_checking_imports: Set[str]):
        """Handle forward references like 'module.Class'"""
        if '.' in forward_ref:
            module_name, class_name = forward_ref.rsplit('.', 1)

            # Skip if it's defined in current file
            if class_name in self.defined_classes:
                return

            # Skip excluded modules
            if StubzenConfig().is_excluded_module(module_name):
                return

            # For module-style stubs, always import from the original .py module, not the stub
            import_stmt = f"from {module_name} import {class_name}"
            type_checking_imports.add(import_stmt)

    def _extract_imports_from_complex_expression(self, expr: str, typing_imports: Set[str],
                                                type_checking_imports: Set[str]):
        """Extract imports from complex type expressions like 'Union[Service, Dict[str, Any]]'"""
        # Extract typing constructs
        typing_matches = re.findall(TYPING_PATTERN, expr)
        for match in typing_matches:
            typing_imports.add(match)

        # Extract quoted class names
        quoted_classes = re.findall(r"'([A-Z][a-zA-Z0-9_]*)'", expr)
        for class_name in quoted_classes:
            if class_name not in self.defined_classes:
                # Try to resolve where this class comes from
                resolved_module = self._resolve_string_type_module(class_name)
                if resolved_module and not StubzenConfig().is_excluded_module(resolved_module):
                    import_stmt = f"from {resolved_module} import {class_name}"
                    type_checking_imports.add(import_stmt)

    def _extract_typing_from_signatures(self, signatures: List[SignatureInfo], typing_imports: set):
        """Extract typing constructs from raw signature strings with enhanced patterns"""
        all_signature_text = ' '.join(sig.raw_signature for sig in signatures)
        typing_matches = re.findall(TYPING_PATTERN, all_signature_text)

        for match in typing_matches:
            typing_imports.add(match)

    def _categorize_type_import(self, type_obj: Type, standard_imports: Set[str],
                               typing_imports: Set[str], third_party_imports: Set[str],
                               type_checking_imports: Set[str]):
        """Categorize a type object for the appropriate import section with enhanced logic"""

        if not type_obj or type_obj == Any:
            return

        # Handle generic types
        origin = get_origin(type_obj)
        if origin is not None:
            # Process the origin type
            self._categorize_type_import(origin, standard_imports, typing_imports,
                                       third_party_imports, type_checking_imports)

            # Process type arguments
            for arg in get_args(type_obj):
                self._categorize_type_import(arg, standard_imports, typing_imports,
                                           third_party_imports, type_checking_imports)
            return

        # Get module and name info
        module_name = getattr(type_obj, '__module__', None)
        type_name = getattr(type_obj, '__name__', None)

        if not module_name or not type_name:
            return

        # Skip if it's defined in current file
        if type_name in self.defined_classes:
            return

        # Skip excluded modules completely
        if StubzenConfig().is_excluded_module(module_name):
            return

        # Categorize by module
        if module_name == 'builtins':
            return  # Built-in types don't need imports

        elif module_name == 'typing':
            typing_imports.add(type_name)

        elif module_name in ['collections', 'collections.abc', 'functools', 'itertools', 'pathlib', 'uuid', 'logging']:
            standard_imports.add(f"from {module_name} import {type_name}")

        else:
            # Everything else goes in TYPE_CHECKING
            type_checking_imports.add(f"from {module_name} import {type_name}")

    def _categorize_string_type(self, type_name: str, typing_imports: set, type_checking_imports: Set[str]):
        """Categorize string type references with enhanced resolution"""

        # Skip built-in types
        if type_name in ['str', 'int', 'float', 'bool', 'list', 'dict', 'tuple', 'set', 'None']:
            return

        # Skip if defined in current file
        if type_name in self.defined_classes:
            return

        if type_name in TYPING_CONSTRUCTS:
            typing_imports.add(type_name)
            return

        # Try to find where this type is defined
        resolved_module = self._resolve_string_type_module(type_name)
        if resolved_module:
            # Skip excluded modules
            if StubzenConfig().is_excluded_module(resolved_module):
                return

            import_stmt = f"from {resolved_module} import {type_name}"
            type_checking_imports.add(import_stmt)

    def _resolve_string_type_module(self, type_name: str) -> str | None:
        """Try to resolve which module a string type name comes from"""
        # Look through loaded modules with better prioritization
        project_candidates = []
        third_party_candidates = []

        for module_name, module in sys.modules.items():
            if module is None or module_name in BUILTIN_MODULES:
                continue

            # Skip modules that start with underscore (private/built-in)
            if module_name.startswith('_'):
                continue

            try:
                if hasattr(module, type_name):
                    attr = getattr(module, type_name)
                    if inspect.isclass(attr):
                        if not StubzenConfig().is_excluded_module(module_name):
                            project_candidates.append(module_name)
                        else:
                            third_party_candidates.append(module_name)
            except Exception:
                continue

        # Prefer project modules, then choose the most specific one
        if project_candidates:
            # Sort by specificity (longer module names are usually more specific)
            project_candidates.sort(key=len, reverse=True)
            return project_candidates[0]
        elif third_party_candidates:
            third_party_candidates.sort(key=len, reverse=True)
            return third_party_candidates[0]

        return None

    def _build_import_statements(self, standard_imports: Set[str], typing_imports: Set[str],
                                third_party_imports: Set[str], type_checking_imports: Set[str]) -> str:
        """Build the final import statements with enhanced organization"""
        lines = []

        # Add linter suppression for PyCharm and other tools
        lines.append("# noinspection PyUnresolvedReferences")
        lines.append("")

        # Standard library imports
        if standard_imports:
            lines.extend(sorted(standard_imports))
            lines.append("")

        # Third-party imports
        if third_party_imports:
            lines.extend(sorted(third_party_imports))
            lines.append("")

        # Typing imports with better organization
        if typing_imports:
            typing_list = sorted(typing_imports)
            # Split long import lines for better readability
            if len(typing_list) > 6:
                lines.append("from typing import (")
                for i, import_name in enumerate(typing_list):
                    comma = "," if i < len(typing_list) - 1 else ""
                    lines.append(f"    {import_name}{comma}")
                lines.append(")")
            else:
                lines.append(f"from typing import {', '.join(typing_list)}")
            lines.append("")

        # TYPE_CHECKING imports with better organization
        if type_checking_imports:
            lines.append("from typing import TYPE_CHECKING")
            lines.append("")
            lines.append("if TYPE_CHECKING:")

            # Sort imports by module for better organization
            imports_by_module = {}
            for import_stmt in type_checking_imports:
                # Extract module name for grouping
                if ' from ' in import_stmt:
                    module = import_stmt.split(' from ')[1].split(' import ')[0]
                else:
                    module = import_stmt.split(' import ')[0].replace('from ', '')

                if module not in imports_by_module:
                    imports_by_module[module] = []
                imports_by_module[module].append(import_stmt)

            # Output grouped imports
            for module in sorted(imports_by_module.keys()):
                for import_stmt in sorted(imports_by_module[module]):
                    lines.append(f"    {import_stmt}")
                lines.append("")

            # Remove trailing empty line
            if lines and lines[-1] == "":
                lines.pop()

        return "\n".join(lines) if lines else "\n"