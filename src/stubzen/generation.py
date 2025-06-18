"""
Updated stub generation orchestrator with validation and cleanup features
"""
import ast
import logging
from pathlib import Path
from typing import List, Optional

from .config import StubzenConfig
from .discovery import ProjectDiscovery, ClassInfo
from .import_generation import ImportGenerator
from .planning import StubPlanner
from .signature_extraction.extractor import SignatureExtractor

logger = logging.getLogger(__name__)

class StubValidator:
    """Validates stub file content before saving"""

    @staticmethod
    def validate_stub_content(content: str, file_path: Path) -> tuple[bool, List[str]]:
        """
        Validate stub file content for syntax errors
        Returns (is_valid, error_messages)
        """
        errors = []

        try:
            # Parse the content as Python code
            ast.parse(content)

            # Additional stub-specific validations
            lines = content.split('\n')

            # Check for common stub issues
            for i, line in enumerate(lines, 1):
                line = line.strip()

                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue

                # Check for missing ellipsis in method definitions
                if line.startswith('def ') and not line.endswith('...'):
                    if i < len(lines) and not lines[i].strip().endswith('...'):
                        errors.append(f"Line {i}: Method definition missing '...' body")

                # Check for invalid class definitions
                if line.startswith('class ') and ':' not in line:
                    errors.append(f"Line {i}: Class definition missing colon")

            return len(errors) == 0, errors

        except SyntaxError as e:
            errors.append(f"Syntax error at line {e.lineno}: {e.msg}")
            return False, errors
        except Exception as e:
            errors.append(f"Validation error: {str(e)}")
            return False, errors


class StubCleaner:
    """Handles cleanup of stub files"""

    def __init__(self):
        self.project_root = StubzenConfig().project_root

    def find_all_stub_files(self) -> List[Path]:
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

    def clean_all_stubs(self, dry_run: bool = False) -> tuple[int, List[str]]:
        """
        Delete all stub files in the project
        Returns (count_deleted, error_messages)
        """
        stub_files = self.find_all_stub_files()
        deleted_count = 0
        errors = []

        print(f"🔍 Found {len(stub_files)} stub files")

        for stub_file in stub_files:
            try:
                if dry_run:
                    print(f"Would delete: {stub_file}")
                else:
                    stub_file.unlink()
                    print(f"🗑️  Deleted: {stub_file}")
                deleted_count += 1
            except Exception as e:
                error_msg = f"Failed to delete {stub_file}: {e}"
                errors.append(error_msg)
                print(f"❌ {error_msg}")

        return deleted_count, errors

    def clean_stubs_for_modules(self, module_patterns: List[str], dry_run: bool = False) -> tuple[int, List[str]]:
        """
        Delete stub files matching specific module patterns
        Returns (count_deleted, error_messages)
        """
        stub_files = self.find_all_stub_files()
        matching_files = []

        for stub_file in stub_files:
            # Convert file path to module-like pattern for matching
            relative_path = stub_file.relative_to(self.project_root)
            module_path = str(relative_path.with_suffix('')).replace('/', '.').replace('\\', '.')

            if any(pattern in module_path for pattern in module_patterns):
                matching_files.append(stub_file)

        deleted_count = 0
        errors = []

        print(f"🔍 Found {len(matching_files)} matching stub files")

        for stub_file in matching_files:
            try:
                if dry_run:
                    print(f"Would delete: {stub_file}")
                else:
                    stub_file.unlink()
                    print(f"🗑️  Deleted: {stub_file}")
                deleted_count += 1
            except Exception as e:
                error_msg = f"Failed to delete {stub_file}: {e}"
                errors.append(error_msg)
                print(f"❌ {error_msg}")

        return deleted_count, errors


class StubConfig:
    pass


class StubGenerator:
    """Main stub generator that orchestrates the entire process"""

    def __init__(self):
        self.project_root = StubzenConfig().project_root

        # Initialize components
        self.discovery = ProjectDiscovery()
        self.planner = StubPlanner()
        self.signature_extractor = SignatureExtractor(log_missing_types=True)
        self.validator = StubValidator()
        self.cleaner = StubCleaner()

    def generate_stubs(self, module_patterns=None) -> bool:
        """Generate stub files for the entire project"""
        if module_patterns is None:
            module_patterns = []
        try:
            print(f"🔍 Discovering classes in {self.project_root}")

            # Step 1: Discover all target classes
            classes_by_module = self.discovery.discover_target_classes()

            if not classes_by_module:
                print("❌ No target classes found")
                return False

            if module_patterns:
                filtered_classes = {}
                for module_path, class_infos in classes_by_module.items():
                    if any(pattern in module_path for pattern in module_patterns):
                        filtered_classes[module_path] = class_infos
                classes_by_module = filtered_classes

            total_classes = sum(len(classes) for classes in classes_by_module.values())
            print(f"✅ Found {total_classes} target classes in {len(classes_by_module)} modules")

            # Step 2: Plan stub file organization
            print("📋 Planning stub file organization")
            stub_plan = self.planner.plan_stub_files(classes_by_module)

            print(f"📝 Will generate {len(stub_plan)} stub files")

            # Step 3: Generate stub files
            print("🔧 Generating stub files")
            success_count = 0
            validation_errors = 0

            for stub_file_path, class_infos in stub_plan.items():
                try:
                    if self._generate_single_stub_file(stub_file_path, class_infos):
                        success_count += 1
                    else:
                        validation_errors += 1
                except Exception as e:
                    print(f"❌ Failed to generate {stub_file_path}: {e}")

            print(f"✅ Successfully generated {success_count}/{len(stub_plan)} stub files")
            if validation_errors > 0:
                print(f"⚠️  {validation_errors} files had validation errors and were not saved")

            # Step 4: Report missing annotations
            if self.signature_extractor.missing_annotations:
                print(self.signature_extractor.get_missing_annotations_report())

            return success_count == len(stub_plan)

        except Exception as e:
            print(f"❌ Stub generation failed: {e}")
            return False

    def _generate_single_stub_file(self, stub_file_path: Path, class_infos: List[ClassInfo]) -> bool:
        """Generate a single stub file with validation"""
        self.signature_extractor.clear_state()

        # Extract package name and class names being defined in this file
        if getattr(self.config, 'package_level_stubs', False):
            package_name = stub_file_path.stem
            defined_class_names = {class_info.name for class_info in class_infos}
        else:
            package_name = None
            defined_class_names = set()

        all_signatures = []
        class_contents = []

        # Process each class
        for class_info in class_infos:
            try:
                # Extract signatures using simplified logic
                signatures = self.signature_extractor.extract_class_signature(
                    class_info.class_obj,
                    include_inherited=True
                )

                if signatures:
                    all_signatures.extend(signatures)

                    # Generate class definition
                    class_content = f"class {class_info.name}:\n"

                    # Group signatures by source for better organization
                    signatures_by_source = {}
                    for sig in signatures:
                        source = sig.source_class or class_info.name
                        if source not in signatures_by_source:
                            signatures_by_source[source] = []
                        signatures_by_source[source].append(sig)

                    # Add signatures with source comments
                    for source_class, source_signatures in signatures_by_source.items():
                        if source_class != class_info.name:
                            class_content += f"    # From {source_class}\n"

                        for sig in source_signatures:
                            class_content += f"    {sig.raw_signature}\n"

                        class_content += "\n"

                    class_contents.append(class_content.rstrip() + "\n")
                else:
                    # Empty class
                    class_contents.append(f"class {class_info.name}:\n    pass\n")

            except Exception as e:
                logger.warning(f"Could not process {class_info.name}: {e}")
                class_contents.append(f"class {class_info.name}:\n    pass\n")

        # Generate imports
        import_generator = ImportGenerator(self.signature_extractor.type_resolver)
        if package_name:
            import_generator.set_current_package(package_name)

        defined_class_names = {class_info.name for class_info in class_infos}
        import_generator.set_defined_classes(defined_class_names)

        imports = import_generator.generate_imports(all_signatures)

        # Combine everything
        stub_content = imports + "\n" + "\n\n".join(class_contents)

        # Validate the content before saving
        is_valid, validation_errors = self.validator.validate_stub_content(stub_content, stub_file_path)

        if not is_valid:
            print(f"❌ Validation failed for {stub_file_path}:")
            for error in validation_errors:
                print(f"   • {error}")
            print(f"   File not saved due to validation errors.")
            return False

        # Write file only if validation passes
        stub_file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(stub_file_path, 'w') as f:
            f.write(stub_content)

        print(f"Generated: {stub_file_path}")
        return True

    def clean_stubs(self, module_patterns: List[str] = None, dry_run: bool = False) -> bool:
        """Clean up stub files"""
        if module_patterns:
            deleted_count, errors = self.cleaner.clean_stubs_for_modules(module_patterns, dry_run)
        else:
            deleted_count, errors = self.cleaner.clean_all_stubs(dry_run)

        action = "Would delete" if dry_run else "Deleted"
        print(f"🧹 {action} {deleted_count} stub files")

        if errors:
            print(f"❌ {len(errors)} errors occurred during cleanup")
            for error in errors:
                print(f"   • {error}")
            return False

        return True


def generate_stubs(project_root: str,
                  config: Optional[StubConfig] = None,
                  module_patterns: Optional[List[str]] = None) -> bool:
    """Convenience function to generate stubs"""
    generator = StubGenerator()
    return generator.generate_stubs(module_patterns or [])


def clean_stubs(project_root: str,
                module_patterns: Optional[List[str]] = None,
                dry_run: bool = False) -> bool:
    """Convenience function to clean up stub files"""
    cleaner = StubCleaner(project_root)
    if module_patterns:
        deleted_count, errors = cleaner.clean_stubs_for_modules(module_patterns, dry_run)
    else:
        deleted_count, errors = cleaner.clean_all_stubs(dry_run)

    action = "Would delete" if dry_run else "Deleted"
    print(f"🧹 {action} {deleted_count} stub files")

    if errors:
        print(f"❌ {len(errors)} errors occurred")
        for error in errors:
            print(f"   • {error}")
        return False

    return True