"""
Clean command for removing stub files
"""

import logging
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

class StubCleanCommand:
    """Command to clean up stub files"""

    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root).resolve()

    def execute(self, module_patterns: List[str] = None, dry_run: bool = False) -> bool:
        """Execute the clean command"""
        try:
            if module_patterns:
                deleted_count, errors = self._clean_stubs_for_modules(module_patterns, dry_run)
            else:
                deleted_count, errors = self._clean_all_stubs(dry_run)

            action = "Would delete" if dry_run else "Deleted"
            logger.info(f"🧹 {action} {deleted_count} stub files")

            if errors:
                logger.error(f"❌ {len(errors)} errors occurred during cleanup")
                for error in errors:
                    logger.error(f"   • {error}")
                return False

            if dry_run and deleted_count > 0:
                logger.info("💡 Run without --dry-run to actually delete the files")

            return True

        except Exception as e:
            logger.error(f"❌ Stub cleanup failed: {e}")
            return False

    def _find_all_stub_files(self) -> List[Path]:
        """Find all .pyi files in the project"""
        stub_files = []

        # Recursively find all .pyi files
        for pyi_file in self.project_root.rglob("*.pyi"):
            # Skip files in virtual environments and common excluded directories
            path_parts = pyi_file.parts
            exclude_dirs = {'.venv', 'venv', 'env', '.env', 'node_modules', '.git', '__pycache__'}

            if not any(exclude_dir in path_parts for exclude_dir in exclude_dirs):
                stub_files.append(pyi_file)

        return stub_files

    def _clean_all_stubs(self, dry_run: bool = False) -> tuple[int, List[str]]:
        """
        Delete all stub files in the project
        Returns (count_deleted, error_messages)
        """
        stub_files = self._find_all_stub_files()
        deleted_count = 0
        errors = []

        logger.info(f"🔍 Found {len(stub_files)} stub files")

        for stub_file in stub_files:
            try:
                if dry_run:
                    logger.debug(f"Would delete: {stub_file}")
                else:
                    stub_file.unlink()
                    logger.debug(f"🗑️  Deleted: {stub_file}")
                deleted_count += 1
            except Exception as e:
                error_msg = f"Failed to delete {stub_file}: {e}"
                errors.append(error_msg)
                logger.error(f"❌ {error_msg}")

        return deleted_count, errors

    def _clean_stubs_for_modules(self, module_patterns: List[str], dry_run: bool = False) -> tuple[int, List[str]]:
        """
        Delete stub files matching specific module patterns
        Returns (count_deleted, error_messages)
        """
        stub_files = self._find_all_stub_files()
        matching_files = []

        for stub_file in stub_files:
            # Convert file path to module-like pattern for matching
            relative_path = stub_file.relative_to(self.project_root)
            module_path = str(relative_path.with_suffix('')).replace('/', '.').replace('\\', '.')

            if any(pattern in module_path for pattern in module_patterns):
                matching_files.append(stub_file)

        deleted_count = 0
        errors = []

        logger.info(f"🔍 Found {len(matching_files)} matching stub files")

        for stub_file in matching_files:
            try:
                if dry_run:
                    logger.debug(f"Would delete: {stub_file}")
                else:
                    stub_file.unlink()
                    logger.debug(f"🗑️  Deleted: {stub_file}")
                deleted_count += 1
            except Exception as e:
                error_msg = f"Failed to delete {stub_file}: {e}"
                errors.append(error_msg)
                logger.error(f"❌ {error_msg}")

        return deleted_count, errors