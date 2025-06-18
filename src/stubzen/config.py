"""
Configuration loader for stub generation
Supports both pyproject.toml and fallback defaults
"""
import logging
import tomllib
from pathlib import Path
from typing import List, Type, Set, Optional, Dict, Any

from .constants import DEFAULT_EXCLUDE_DIRS
from .utils.finder import ModuleFinder

logger = logging.getLogger(__name__)

DEFAULTS = {
    "base_classes": [],
    "mixin_classes": [],
    "exclude_modules": [],
    "exclude_dirs": [
        'docs',
        'scripts',
        'migrations',
    ],
    "stub_style": "module", # module, package
    "verbose_logging": False,
    "log_missing_types": True,
    "watch_paths": [],
    "watch_patterns": []
}

class StubzenConfig:
    """Configuration management for stubzen"""
    _instance = None

    def __new__(cls, project_root: Optional[Path] = None):
        if cls._instance is None:
            print('Creating the object')
            cls._instance = super(StubzenConfig, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        self._project_root: Path
        self._config_data: Dict[str, Any]

    def load_config(self, project_root: Optional[Path] = None) -> None:
        """Load configuration from pyproject.toml or use defaults"""
        self._project_root = project_root or Path.cwd()
        pyproject_path = self._project_root / "pyproject.toml"

        # Try to load from pyproject.toml
        if pyproject_path.exists():
            try:
                with open(pyproject_path, 'rb') as f:
                    pyproject_data = tomllib.load(f)

                # Extract stubzen configuration
                tool_config = pyproject_data.get('tool', {})
                stubzen_config = tool_config.get('stubzen', {})

                if stubzen_config:
                    logger.info(f"✅ Loaded configuration from {pyproject_path}")
                    # Merge with defaults
                    self._config_data = DEFAULTS.update(stubzen_config)
                    logger.info(f"Using config {self._config_data}")
                else:
                    logger.warning("ℹ️  No [tool.stubzen] section found, using defaults")

            except Exception as e:
                logger.warning(f"⚠️  Could not read pyproject.toml: {e}")
                logger.info("ℹ️  Using default configuration")
        else:
            logger.warning("ℹ️  No pyproject.toml found, using default configuration")

        self._config_data = DEFAULTS
        logger.info(f"Using default config {self._config_data}")



    @property
    def project_root(self) -> Path:
        return self._project_root

    @property
    def base_classes(self) -> List[str]:
        return self._config_data.get("base_classes", [])

    @property
    def mixin_classes(self) -> List[str]:
        return self._config_data.get("mixin_classes", [])

    @property
    def exclude_modules(self) -> Set[str]:
        return set(self._config_data.get("exclude_modules", []))

    @property
    def exclude_dirs(self) -> Set[str]:
        user_dirs = set(self._config_data.get("exclude_dirs", []))
        return DEFAULT_EXCLUDE_DIRS | user_dirs

    @property
    def stub_style(self) -> str:
        return self._config_data.get("stub_style", "module")

    @property
    def verbose_logging(self) -> bool:
        return self._config_data.get("verbose_logging", False)

    @property
    def log_missing_types(self) -> bool:
        return self._config_data.get("log_missing_types", True)

    @property
    def watch_paths(self) -> List[str]:
        return self._config_data.get("watch_paths", [])

    @property
    def watch_patterns(self) -> List[str]:
        return self._config_data.get("watch_patterns", [])

    def get_base_class_objects(self) -> List[Type]:
        """Import and return base class objects using ModuleFinder"""
        base_classes = []

        # Temporarily add project root to sys.path for imports
        project_modules = ModuleFinder.find_modules_in_path(
            self._project_root,
            exclude_dirs=self.exclude_dirs
        )

        for class_string in self.base_classes:
            cls_obj = self._resolve_class_reference(class_string)
            if cls_obj:
                base_classes.append(cls_obj)
                logger.info(f"✅ Found base class: {class_string}")

        return base_classes

    def get_mixin_class_objects(self) -> List[Type]:
        """Import and return mixin class objects using ModuleFinder"""
        mixin_classes = []

        for class_string in self.mixin_classes:
            cls_obj = self._resolve_class_reference(class_string)
            if cls_obj:
                mixin_classes.append(cls_obj)
                logger.info(f"✅ Found mixin class: {class_string}")

        return mixin_classes

    def _resolve_class_reference(self, class_path: str) -> Optional[Type]:
        """Resolve a class reference like 'common.layer.Layer' from the target project"""
        import importlib
        import sys

        # Add project root to sys.path temporarily
        project_str = str(self._project_root)
        if project_str not in sys.path:
            sys.path.insert(0, project_str)
            added_to_path = True
        else:
            added_to_path = False

        try:
            module_name, class_name = class_path.rsplit('.', 1)
            module = importlib.import_module(module_name)
            return getattr(module, class_name)
        except (ImportError, AttributeError) as e:
            logger.warning(f"⚠️  Could not import class: {class_path} - {e}")
            return None
        finally:
            # Clean up sys.path
            if added_to_path:
                sys.path.remove(project_str)

    def is_excluded_module(self, module_name: str) -> bool:
        """Check if a module should be excluded from stub generation"""
        return any(excluded in module_name for excluded in self.exclude_modules)