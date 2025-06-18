import importlib
import inspect
import logging
import pkgutil
import sys
from pathlib import Path
from typing import Union, Optional, Set, List, Callable, Type

logger = logging.getLogger(__name__)

class ModuleFinder:
    """Finds and loads modules from various sources"""

    @classmethod
    def find_modules_in_path(cls, search_path: Union[str, Path],
                             exclude_dirs: Optional[Set[str]] = None) -> List[str]:
        """Find all Python modules in a given path"""
        if exclude_dirs is None:
            exclude_dirs = {'.git', '__pycache__', '.pytest_cache', 'node_modules',
                            '.venv', 'venv', 'env', '.env', 'build', 'dist', 'tests'}

        search_path = Path(search_path).resolve()
        modules = []

        # Add to Python path if not already there
        if str(search_path) not in sys.path:
            sys.path.insert(0, str(search_path))

        for py_file in cls._find_python_files(search_path, exclude_dirs):
            module_path = cls._file_to_module_path(py_file, search_path)
            if module_path:
                modules.append(module_path)

        return modules

    @classmethod
    def _find_python_files(cls, root_path: Path, exclude_dirs: Set[str]) -> List[Path]:
        """Find all Python files in the path"""
        python_files = []

        for root, dirs, files in root_path.walk():
            # Remove excluded directories
            dirs[:] = [d for d in dirs if d not in exclude_dirs and not d.startswith('.')]

            for file in files:
                if file.endswith('.py') and not file.startswith('.'):
                    python_files.append(root / file)

        return python_files

    @classmethod
    def _file_to_module_path(cls, file_path: Path, root_path: Path) -> Optional[str]:
        """Convert file path to Python module path"""
        try:
            relative_path = file_path.relative_to(root_path)

            # Handle __init__.py files
            if relative_path.name == '__init__.py':
                if len(relative_path.parts) == 1:
                    return None  # Skip root __init__.py
                return '.'.join(relative_path.parts[:-1])

            # Convert path to module notation
            module_parts = list(relative_path.parts[:-1])  # Remove filename
            module_parts.append(relative_path.stem)  # Add filename without .py
            return '.'.join(module_parts)

        except ValueError:
            return None

class ClassFinder:
    """Finds classes based on various criteria"""

    @classmethod
    def find_classes_in_modules(cls,
                                module_names: List[str],
                                filter_func: Optional[Callable[[Type], bool]] = None,
                                recursive: bool = True) -> List[Type]:
        """Find classes in given modules that match the filter function

        Args:
            module_names: List of module names to search
            filter_func: Function to filter classes (if None, returns all classes)
            recursive: If True, recursively search submodules/subpackages
        """
        found_classes = []

        # If recursive, expand module names to include submodules
        if recursive:
            expanded_modules = set(module_names)  # Use set to avoid duplicates
            for module_name in module_names:
                expanded_modules.update(cls._get_submodules(module_name))
            module_names = list(expanded_modules)

        for module_name in module_names:
            try:
                if module_name in sys.modules:
                    module = sys.modules[module_name]
                else:
                    module = importlib.import_module(module_name)

                for name, obj in inspect.getmembers(module, inspect.isclass):
                    # Only include classes actually defined in this module
                    if obj.__module__ != module_name:
                        continue

                    if filter_func is None or filter_func(obj):
                        found_classes.append(obj)

            except ImportError as e:
                # Silently skip circular import errors, but log others
                if "circular import" not in str(e).lower():
                    logger.warning(f"⚠️  Could not import {module_name}: {e}")
                continue
            except Exception as e:
                # Skip any other import-related errors
                continue

        return found_classes

    @classmethod
    def _get_submodules(cls, module_name: str) -> List[str]:
        """Get all submodules of a given module recursively"""
        submodules = []

        try:
            module = importlib.import_module(module_name)

            # If it's a package (has __path__), recursively find submodules
            if hasattr(module, '__path__'):
                submodules.extend(cls._walk_package_recursively(module))

        except ImportError:
            # If we can't import the module, return empty list
            pass

        return submodules

    @classmethod
    def find_subclasses(cls,
                        base_classes: List[Type],
                        search_modules: Optional[List[str]] = None,
                        recursive: bool = True) -> List[Type]:
        """Find all subclasses of given base classes"""
        if search_modules is None:
            current_dir = Path(__file__).parent
            project_root = current_dir.parent.parent
            search_modules = ModuleFinder.find_modules_in_path(project_root)

        def is_target_subclass(obj: Type) -> bool:
            return any(
                inspect.isclass(obj) and
                issubclass(obj, base_class) and
                obj is not base_class
                for base_class in base_classes
            )

        return cls.find_classes_in_modules(search_modules, is_target_subclass, recursive=recursive)

    @classmethod
    def _walk_package_recursively(cls, package) -> List[str]:
        """Recursively walk a package's submodules"""
        if not hasattr(package, '__path__'):
            return []

        modules = []
        for importer, modname, ispkg in pkgutil.iter_modules(
                package.__path__, package.__name__ + "."
        ):
            modules.append(modname)

            if ispkg:
                try:
                    subpackage = importlib.import_module(modname)
                    modules.extend(cls._walk_package_recursively(subpackage))
                except ImportError:
                    continue

        return modules