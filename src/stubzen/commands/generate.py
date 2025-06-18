"""
Generate command for creating stub files
"""

import ast
import importlib
import logging
from pathlib import Path
from typing import List, Tuple

from ..config import StubzenConfig
from ..discovery import ProjectDiscovery, ClassInfo
from ..import_generation import ImportGenerator
from ..planning import StubPlanner
from ..signature_extraction.extractor import SignatureExtractor
from ..utils.ast import extract_module_imports

logger = logging.getLogger(__name__)


class StubValidator:
    """Validates stub file content before saving"""

    @staticmethod
    def validate_stub_content(content: str, file_path: Path) -> Tuple[bool, List[str]]:
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


class StubContentGenerator:
    """Handles generating content for classes in stub files"""

    def __init__(self, signature_extractor, logger):
        self.signature_extractor = signature_extractor
        self.logger = logger

    def generate_class_content(self, class_info: ClassInfo, include_inherited: bool = True) -> Tuple[str, List]:
        """Generate content for a class with configurable inheritance handling"""
        try:
            signatures = self.signature_extractor.extract_class_signature(
                class_info.class_obj,
                include_inherited=include_inherited
            )

            if signatures:
                class_content = self._build_class_with_signatures(class_info.name, signatures)
                return class_content, signatures
            else:
                return f"class {class_info.name}:\n    pass\n", []

        except Exception as e:
            self.logger.warning(f"Could not process class {class_info.name}: {e}")
            return f"class {class_info.name}:\n    pass\n", []

    def _build_class_with_signatures(self, class_name: str, signatures) -> str:
        """Build class definition with organized signatures"""
        class_content = f"class {class_name}:\n"

        # Group signatures by source for better organization
        signatures_by_source = {}
        for sig in signatures:
            source = sig.source_class or class_name
            if source not in signatures_by_source:
                signatures_by_source[source] = []
            signatures_by_source[source].append(sig)

        # Add signatures with source comments
        for source_class, source_signatures in signatures_by_source.items():
            class_content += f"    # From {source_class}\n"
            for sig in source_signatures:
                class_content += f"    {sig.raw_signature}\n"
            class_content += "\n"

        return class_content.rstrip() + "\n"


class StubImportGenerator:
    """Handles generating imports for stub files"""

    def __init__(self, type_resolver, logger):
        self.type_resolver = type_resolver
        self.logger = logger

    def generate_imports_for_stub(self, class_infos: List[ClassInfo], all_signatures: List) -> str:
        """Generate complete imports section for a stub file"""
        # Generate imports from signatures
        import_generator = ImportGenerator(self.type_resolver)
        defined_class_names = {class_info.name for class_info in class_infos}
        import_generator.set_defined_classes(defined_class_names)
        signature_imports = import_generator.generate_imports(all_signatures)

        # Add module-level imports if available
        module_imports = self._extract_module_imports(class_infos)

        if module_imports:
            module_import_section = "\n".join(module_imports) + "\n\n"
            return module_import_section + signature_imports
        else:
            return signature_imports

    def _extract_module_imports(self, class_infos: List[ClassInfo]) -> List[str]:
        """Extract imports from the original module using AST utils"""
        if not class_infos:
            return []

        try:
            module_name = class_infos[0].module_path
            module = importlib.import_module(module_name)
            return extract_module_imports(module)

        except Exception as e:
            self.logger.debug(f"Could not extract module imports: {e}")
            return []


class StubFileGenerator:
    """Orchestrates the generation of individual stub files"""

    def __init__(self, signature_extractor, validator, logger):
        self.signature_extractor = signature_extractor
        self.validator = validator
        self.logger = logger
        self.content_generator = StubContentGenerator(signature_extractor, logger)
        self.import_generator = StubImportGenerator(signature_extractor.type_resolver, logger)

    def generate_stub_file(self, stub_file_path: Path, class_infos: List[ClassInfo]) -> bool:
        """Generate a stub file with specified discovery mode"""
        self.signature_extractor.clear_state()

        all_signatures = []
        class_contents = []

        for class_info in class_infos:

            include_inherited = class_info.category != 'standard'

            content, signatures = self.content_generator.generate_class_content(
                class_info,
                include_inherited=include_inherited
            )
            class_contents.append(content)
            all_signatures.extend(signatures)

        # Generate imports
        imports = self.import_generator.generate_imports_for_stub(class_infos, all_signatures)

        # Combine everything
        stub_content = imports + "\n" + "\n\n".join(class_contents)

        # Validate and write
        return self._validate_and_write_stub(stub_content, stub_file_path)

    def _validate_and_write_stub(self, stub_content: str, stub_file_path: Path) -> bool:
        """Validate stub content and write to file"""
        is_valid, validation_errors = self.validator.validate_stub_content(stub_content, stub_file_path)

        if not is_valid:
            self.logger.error(f"❌ Validation failed for {stub_file_path}:")
            for error in validation_errors:
                self.logger.error(f"   • {error}")
            return False

        # Write file
        stub_file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(stub_file_path, 'w') as f:
            f.write(stub_content)

        self.logger.info(f"Generated: {stub_file_path}")
        return True


class StubGenerateCommand:
    """Command to generate stub files with configurable discovery modes"""

    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root).resolve()
        self.signature_extractor = SignatureExtractor(log_missing_types=StubzenConfig().log_missing_types)
        self.validator = StubValidator()
        self.file_generator = StubFileGenerator(self.signature_extractor, self.validator, logger)

        # Get base and mixin classes
        self.base_classes = StubzenConfig().get_base_class_objects()
        self.mixin_classes = StubzenConfig().get_mixin_class_objects()

        if not self.base_classes and not self.mixin_classes:
            logger.warning("No base classes or mixin classes found. Please check your config")

    def execute(self) -> bool:
        """
        Execute stub generation
        """

        try:
            logger.info(f"🔍 Discovering classes in {self.project_root}")

            # Step 1: Discover classes
            discovery = ProjectDiscovery()
            classes_by_module = discovery.discover_modules()

            if not classes_by_module:
                logger.error("❌ No classes found")
                return False

            total_classes = sum(len(classes) for classes in classes_by_module.values())
            logger.info(f"✅ Found {total_classes} classes in {len(classes_by_module)} modules")

            # Step 2: Plan stub files
            logger.info("📋 Planning stub file organization")
            planner = StubPlanner()
            stub_plan = planner.plan_stub_files(classes_by_module)
            logger.info(f"📝 Will generate {len(stub_plan)} stub files")

            # Step 3: Generate stub files
            logger.info("🔧 Generating stub files")
            success_count = 0
            validation_errors = 0

            for stub_file_path, class_infos in stub_plan.items():
                try:
                    if self.file_generator.generate_stub_file(stub_file_path, class_infos):
                        success_count += 1
                    else:
                        validation_errors += 1
                except Exception as e:
                    logger.error(f"❌ Failed to generate {stub_file_path}: {e}")

            # Step 4: Create py.typed marker
            self._create_py_typed_marker()

            # Step 5: Report results
            logger.info(f"✅ Successfully generated {success_count}/{len(stub_plan)} stub files")
            if validation_errors > 0:
                logger.warning(f"⚠️  {validation_errors} files had validation errors and were not saved")

            # Step 6: Report missing annotations
            if self.signature_extractor.missing_annotations:
                logger.info(self.signature_extractor.get_missing_annotations_report())

            # Step 7: Provide usage guidance
            self._show_usage_guidance()

            return success_count == len(stub_plan)

        except Exception as e:
            logger.error(f"❌ Stub generation failed: {e}")
            return False

    def _create_py_typed_marker(self):
        """Create py.typed marker file for PEP 561"""
        marker_path = Path('stubs') / 'py.typed'
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.touch()
        logger.info("Created py.typed marker file")

    def _show_usage_guidance(self):
        """Show usage guidance based on generation mode"""
        logger.info("🎉 Complete stub generation finished!")
        logger.info("📁 Stub files are in stubs/ directory")
        logger.info("💡 To use as PEP 561 package:")
        logger.info("   1. Install this package: pip install -e .")
        logger.info("   2. Your IDE should automatically discover the stubs")