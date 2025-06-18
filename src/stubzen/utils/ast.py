"""
Shared AST utilities for processing __init__ methods and synthetic properties
"""

import ast
import inspect
import re
import sys
import textwrap
from typing import Type, List, Dict, Any, Optional

def extract_from_init(cls: Type, type_hints: Dict[str, Type]) -> List[tuple]:
    """Extract instance variables from __init__ using AST parsing"""
    members = []

    if not hasattr(cls, '__init__') or cls.__module__ in ['abc', 'typing', 'builtins']:
        return members

    try:
        source_code = inspect.getsource(cls.__init__)
        dedented_source = textwrap.dedent(source_code)
        tree = ast.parse(dedented_source)

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == '__init__':
                # Look for annotated assignments to self
                for stmt in ast.walk(node):
                    if isinstance(stmt, ast.AnnAssign):
                        # Check if target is self.something
                        if (isinstance(stmt.target, ast.Attribute) and
                                isinstance(stmt.target.value, ast.Name) and
                                stmt.target.value.id == 'self'):

                            var_name = stmt.target.attr

                            # Type resolution priority:
                            # 1. Use type hints from get_type_hints if available
                            # 2. Parse and resolve the AST annotation
                            # 3. Fall back to the raw annotation string

                            var_type = type_hints.get(var_name)
                            if not var_type:
                                # Parse the AST annotation
                                type_str = ast_annotation_to_string(stmt.annotation)

                                # Try to resolve the type string
                                resolved_type = resolve_type_string(type_str, cls)

                                if resolved_type and resolved_type != Any:
                                    var_type = resolved_type
                                else:
                                    # Keep the original type string for the TypeResolver to handle
                                    var_type = type_str

                            # Create a synthetic property object with type information
                            synthetic_prop = type('SyntheticProperty', (), {
                                'var_name': var_name,
                                'annotation': stmt.annotation,
                                'resolved_type': var_type
                            })()
                            members.append((var_name, synthetic_prop, cls))
                break

    except Exception:
        # Silent failure - just return empty list
        pass

    return members

def resolve_type_string(type_str: str, context_class: Type) -> Optional[Type]:
    """Resolve a type string to an actual type object"""
    # Clean the type string
    clean_type_str = type_str.strip("'\"")

    # Handle Union types specially
    if 'Union[' in type_str:
        return resolve_union_type(type_str, context_class)

    # Try direct lookup in the context class's module
    context_module = inspect.getmodule(context_class)
    if context_module:
        # Check module globals
        if hasattr(context_module, clean_type_str):
            candidate = getattr(context_module, clean_type_str)
            if inspect.isclass(candidate):
                return candidate

        # Check TYPE_CHECKING imports in the module
        try:
            module_source = inspect.getsource(context_module)
            type_checking_imports = extract_type_checking_imports(module_source)

            for import_info in type_checking_imports:
                if import_info['name'] == clean_type_str:
                    # Try to import from the TYPE_CHECKING import
                    try:
                        imported_module = __import__(import_info['module'], fromlist=[clean_type_str])
                        if hasattr(imported_module, clean_type_str):
                            candidate = getattr(imported_module, clean_type_str)
                            if inspect.isclass(candidate):
                                return candidate
                    except ImportError:
                        continue
        except (OSError, TypeError):
            pass

    # Fallback: search all loaded modules
    for module_name, module in sys.modules.items():
        if module is None or module_name.startswith('_'):
            continue

        try:
            if hasattr(module, clean_type_str):
                candidate = getattr(module, clean_type_str)
                if inspect.isclass(candidate):
                    return candidate
        except Exception:
            continue

    return None

def resolve_union_type(type_str: str, context_class: Type) -> str:
    """Resolve Union type strings like 'Union[Registry, InitializedRegistrySubclass]'"""
    # For Union types, keep them as strings for the TypeResolver to handle properly
    # This ensures they get formatted correctly in the stub files
    return type_str

def extract_type_checking_imports(source_code: str) -> List[Dict[str, str]]:
    """Extract imports from TYPE_CHECKING blocks"""
    imports = []

    # Find TYPE_CHECKING blocks
    type_checking_pattern = r'if TYPE_CHECKING:(.*?)(?=\n\S|\nif |\ndef |\nclass |\Z)'
    type_checking_blocks = re.findall(type_checking_pattern, source_code, re.DOTALL)

    for block in type_checking_blocks:
        # Extract from imports
        from_import_pattern = r'from\s+([^\s]+)\s+import\s+([^\n]+)'
        from_imports = re.findall(from_import_pattern, block)

        for module_name, import_list in from_imports:
            # Handle multiple imports
            for imported_name in re.split(r',\s*', import_list):
                imported_name = imported_name.strip()
                imports.append({
                    'module': module_name,
                    'name': imported_name
                })

    return imports

def ast_annotation_to_string(annotation_node) -> str:
    """Convert an AST annotation node to a string representation"""
    try:
        if hasattr(ast, 'unparse'):
            return ast.unparse(annotation_node)
        else:
            return manual_ast_unparse(annotation_node)
    except Exception:
        return "Any"

def manual_ast_unparse(node) -> str:
    """Manual AST unparsing for older Python versions"""
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Constant):
        if isinstance(node.value, str):
            return f"'{node.value}'"
        else:
            return str(node.value)
    elif isinstance(node, ast.Attribute):
        value = manual_ast_unparse(node.value)
        return f"{value}.{node.attr}"
    elif isinstance(node, ast.Subscript):
        value = manual_ast_unparse(node.value)
        slice_value = manual_ast_unparse(node.slice)
        return f"{value}[{slice_value}]"
    elif isinstance(node, ast.Tuple):
        elements = [manual_ast_unparse(elt) for elt in node.elts]
        return f"({', '.join(elements)})"
    elif isinstance(node, ast.List):
        elements = [manual_ast_unparse(elt) for elt in node.elts]
        return f"[{', '.join(elements)}]"
    elif hasattr(node, 'elts'):  # Handle tuple slices
        elements = [manual_ast_unparse(elt) for elt in node.elts]
        return ', '.join(elements)
    else:
        return str(node)

def extract_init_type_annotations(cls: Type, attribute_name: str) -> Optional[Type]:
    """Extract type annotations from __init__ method for specific attribute"""
    try:
        source_code = inspect.getsource(cls.__init__)
        dedented_source = textwrap.dedent(source_code)
        tree = ast.parse(dedented_source)

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == '__init__':
                for stmt in ast.walk(node):
                    if isinstance(stmt, ast.AnnAssign):
                        if (isinstance(stmt.target, ast.Attribute) and
                                isinstance(stmt.target.value, ast.Name) and
                                stmt.target.value.id == 'self' and
                                stmt.target.attr == attribute_name):

                            # Found the annotation - try to resolve it
                            type_str = ast_annotation_to_string(stmt.annotation)
                            return resolve_type_string(type_str, cls)
                break
    except Exception:
        pass
    return None