"""
Simplified discovery without Protocol support
"""
import importlib
import inspect
import logging
import sys
from pathlib import Path
from typing import Dict, List, Type
from dataclasses import dataclass

from .config import StubzenConfig
from .utils.finder import ModuleFinder, ClassFinder

logger = logging.getLogger(__name__)

@dataclass
class ClassInfo:
    """Information about a discovered class"""
    name: str
    module_path: str
    file_path: Path
    class_obj: Type
    category: str  # 'mixin', 'abstract', 'concrete'
    base_classes: List[str]


class ClassIdentifier:
    """Identifies classes by explicit inheritance and custom rules"""

    def __init__(self):
        self.base_classes: List[Type] = StubzenConfig().get_base_class_objects()
        self.mixin_classes: List[Type] = StubzenConfig().get_mixin_class_objects()

    def is_target_class(self, cls: Type) -> bool:
        """Check if a class should have stubs generated"""
        if not inspect.isclass(cls):
            return False

        # Check if it inherits from any target base classes
        for base_class in self.base_classes:
            try:
                if issubclass(cls, base_class):
                    return True
            except TypeError:
                continue

        # Check if it's a mixin
        if self.is_mixin_class(cls):
            return True

        return False

    def is_mixin_class(self, cls: Type) -> bool:
        """Check if a class is a mixin"""
        if not inspect.isclass(cls):
            return False

        # Check explicit mixin inheritance
        for mixin_class in self.mixin_classes:
            try:
                if issubclass(cls, mixin_class):
                    return True
            except TypeError:
                continue

        # Check naming convention as fallback
        return cls.__name__.endswith('Mixin')

    def get_class_category(self, cls: Type) -> str:
        """Categorize a class for stub organization"""
        if self.is_mixin_class(cls):
            return 'mixin'
        elif self._is_base_class(cls):
            return 'base'
        elif self.is_abstract_class(cls):
            return 'abstract'
        else:
            return 'concrete'

    def is_abstract_class(self, cls: Type) -> bool:
        """Check if a class is abstract/base"""
        if not inspect.isclass(cls):
            return False

        # Check if it's an ABC
        try:
            from abc import ABC
            if issubclass(cls, ABC):
                return True
        except (TypeError, ImportError):
            pass

        # Check if it has abstract methods
        abstract_methods = getattr(cls, '__abstractmethods__', set())
        if abstract_methods:
            return True

        # Check naming patterns as fallback
        class_name = cls.__name__
        abstract_indicators = ['Base', 'Abstract', 'ABC']
        return any(indicator in class_name for indicator in abstract_indicators)

    def _is_base_class(self, cls: Type) -> bool:
        """Check if a class is one of our target base classes"""
        return cls in self.base_classes


class ProjectDiscovery:
    """Discovers classes in a project which need stubs"""

    def __init__(self):
        self.project_root = StubzenConfig().project_root
        self.base_classes: List[Type] = StubzenConfig().get_base_class_objects()
        self.mixin_classes: List[Type] = StubzenConfig().get_mixin_class_objects()
        self.class_identifier = ClassIdentifier()

        # Add project root to Python path for imports
        if str(self.project_root) not in sys.path:
            sys.path.insert(0, str(self.project_root))

    def discover_target_classes(self) -> Dict[str, List[ClassInfo]]:
        """Discover all target classes in the project, grouped by module"""
        classes_by_module = {}

        logger.info(f"🔍 Searching for Python modules in {self.project_root}")
        logger.info(f"🚫 Excluding directories: {StubzenConfig().exclude_dirs}")

        # Use ModuleFinder to get all modules
        module_names = ModuleFinder.find_modules_in_path(
            self.project_root,
            StubzenConfig().exclude_dirs
        )

        logger.info(f"📦 Found {len(module_names)} modules to check")

        # Use ClassFinder to get all target classes
        logger.info("🔍 Running ClassFinder.find_classes_in_modules...")
        target_classes = ClassFinder.find_classes_in_modules(
            module_names,
            self.class_identifier.is_target_class,
            recursive=True
        )

        logger.info(f"✅ Found {len(target_classes)} target classes total")

        # Group classes by their module
        for cls in target_classes:
            module_path = cls.__module__

            if module_path not in classes_by_module:
                classes_by_module[module_path] = []

            # Create ClassInfo
            base_classes = [base.__name__ for base in cls.__bases__]
            category = self.class_identifier.get_class_category(cls)

            # Find the file path for this module
            file_path = self._get_file_path_for_module(module_path)

            class_info = ClassInfo(
                name=cls.__name__,
                module_path=module_path,
                file_path=file_path,
                class_obj=cls,
                category=category,
                base_classes=base_classes
            )

            classes_by_module[module_path].append(class_info)
            logger.debug(f"  📝 {cls.__name__} ({category}) in {module_path}")

        # Summary by module
        for module_path, class_infos in classes_by_module.items():
            logger.info(f"📋 {module_path}: {len(class_infos)} classes")

        return classes_by_module

    def _get_file_path_for_module(self, module_path: str) -> Path:
        """Get the file path for a module"""
        try:
            if module_path in sys.modules:
                module = sys.modules[module_path]
            else:
                module = importlib.import_module(module_path)

            if hasattr(module, '__file__') and module.__file__:
                return Path(module.__file__)
        except Exception:
            pass

        # Fallback: construct path from module name
        module_parts = module_path.split('.')
        file_path = self.project_root
        for part in module_parts[:-1]:
            file_path = file_path / part
        file_path = file_path / f"{module_parts[-1]}.py"

        return file_path