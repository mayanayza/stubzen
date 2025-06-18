"""
Simplified planning without Protocol support
"""
from pathlib import Path
from typing import Dict, List

from .config import StubzenConfig
from .discovery import ClassInfo

class StubPlanner:
    """Plans how to organize classes into stub files"""

    def plan_stub_files(self, classes_by_module: Dict[str, List[ClassInfo]]) -> Dict[Path, List[ClassInfo]]:
        """Plan how to organize classes into stub files"""
        style = StubzenConfig().stub_style
        if style == "inline":
            return self._plan_inline(classes_by_module)
        elif style == "module":
            return self._plan_module_level(classes_by_module)
        elif style == "package":
            return self._plan_package_level(classes_by_module)
        else:
            raise ValueError(f"Unknown stub_style: {style}")

    def _plan_inline(self, classes_by_module: Dict[str, List[ClassInfo]]) -> Dict[Path, List[ClassInfo]]:
        """Plan inline stub files (next to .py files)"""
        stub_plan = {}
        for module_path, class_infos in classes_by_module.items():
            if class_infos:
                stub_file_path = self._get_inline_stub_path(module_path)
                stub_plan[stub_file_path] = class_infos
        return stub_plan

    def _plan_module_level(self, classes_by_module: Dict[str, List[ClassInfo]]) -> Dict[Path, List[ClassInfo]]:
        """Plan module-level stub files (stubs/path/file.pyi)"""
        stub_plan = {}
        for module_path, class_infos in classes_by_module.items():
            if class_infos:
                stub_file_path = self._get_module_stub_path(module_path)
                stub_plan[stub_file_path] = class_infos
        return stub_plan

    def _plan_package_level(self, classes_by_module: Dict[str, List[ClassInfo]]) -> Dict[Path, List[ClassInfo]]:
        """Plan package-level stub files (stubs/package.pyi)"""
        by_package = {}
        for module_path, class_infos in classes_by_module.items():
            package = module_path.split('.')[0]
            if package not in by_package:
                by_package[package] = []
            by_package[package].extend(class_infos)

        stub_plan = {}
        for package, class_infos in by_package.items():
            if class_infos:
                stub_file_path = Path('stubs') / f"{package}.pyi"
                stub_plan[stub_file_path] = class_infos
        return stub_plan

    def _get_module_stub_path(self, module_path: str) -> Path:
        """Get stub file path preserving directory structure"""
        module_parts = module_path.split('.')
        file_path = Path('stubs')
        for part in module_parts[:-1]:
            file_path = file_path / part
        file_path = file_path / f"{module_parts[-1]}.pyi"
        return file_path

    def _get_inline_stub_path(self, module_path: str) -> Path:
        """Get inline stub path (next to .py files)"""
        module_parts = module_path.split('.')
        file_path = Path('')
        for part in module_parts[:-1]:
            file_path = file_path / part
        file_path = file_path / f"{module_parts[-1]}.pyi"
        return file_path