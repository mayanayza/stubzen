"""
Generate command for creating stub files
"""

import ast
import logging
from pathlib import Path
from typing import List

from ..config import StubzenConfig
from ..discovery import ProjectDiscovery, ClassInfo
from ..import_generation import ImportGenerator
from ..planning import StubPlanner
from ..signature_extraction.extractor import SignatureExtractor

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

class StubGenerateCommand:
    """Command to generate stub files"""

    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root).resolve()
        self.signature_extractor = SignatureExtractor(log_missing_types=StubzenConfig().log_missing_types)
        self.validator = StubValidator()

        # Get base and mixin classes
        self.base_classes = StubzenConfig().get_base_class_objects()
        self.mixin_classes = StubzenConfig().get_mixin_class_objects()

        if not self.base_classes and not self.mixin_classes:
            logger.warning("No base classes or mixin classes found. Please check your config")

    def execute(self, module_patterns: List[str] = None) -> bool:
        """Execute the generate command"""
        try:
            logger.info(f"🔍 Discovering classes in {self.project_root}")

            # Step 1: Discover all target classes
            discovery = ProjectDiscovery()
            classes_by_module = discovery.discover_target_classes()

            if not classes_by_module:
                logger.error("❌ No target classes found")
                return False

            if module_patterns:
                filtered_classes = {}
                for module_path, class_infos in classes_by_module.items():
                    if any(pattern in module_path for pattern in module_patterns):
                        filtered_classes[module_path] = class_infos
                classes_by_module = filtered_classes

            total_classes = sum(len(classes) for classes in classes_by_module.values())
            logger.info(f"✅ Found {total_classes} target classes in {len(classes_by_module)} modules")

            # Step 2: Plan stub file organization
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
                    if self._generate_single_stub_file(stub_file_path, class_infos):
                        success_count += 1
                    else:
                        validation_errors += 1
                except Exception as e:
                    logger.error(f"❌ Failed to generate {stub_file_path}: {e}")

            logger.info(f"✅ Successfully generated {success_count}/{len(stub_plan)} stub files")
            if validation_errors > 0:
                logger.warning(f"⚠️  {validation_errors} files had validation errors and were not saved")

            # Step 4: Report missing annotations
            if self.signature_extractor.missing_annotations:
                logger.info(self.signature_extractor.get_missing_annotations_report())

            return success_count == len(stub_plan)

        except Exception as e:
            logger.error(f"❌ Stub generation failed: {e}")
            return False

    def _generate_single_stub_file(self, stub_file_path: Path, class_infos: List[ClassInfo]) -> bool:
        """Generate a single stub file with validation"""
        self.signature_extractor.clear_state()

        # Extract package name and class names being defined in this file
        if StubzenConfig().stub_style == 'package':
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

                    # Add signatures with source comments (including self)
                    for source_class, source_signatures in signatures_by_source.items():
                        # Always add source comment, even for the class itself
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
            logger.error(f"❌ Validation failed for {stub_file_path}:")
            for error in validation_errors:
                logger.error(f"   • {error}")
            logger.error(f"   File not saved due to validation errors.")
            return False

        # Write file only if validation passes
        stub_file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(stub_file_path, 'w') as f:
            f.write(stub_content)

        logger.info(f"Generated: {stub_file_path}")
        return True