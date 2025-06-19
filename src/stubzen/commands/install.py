"""
Install command for creating and installing PEP 561 stub packages
"""
import logging
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path
from typing import List, Optional

from .generate import StubGenerateCommand

logger = logging.getLogger(__name__)


class StubInstallCommand:
    """Command to generate and install stub packages"""

    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root).resolve()
        self.generate_command = StubGenerateCommand(project_root)

    def execute(self, module_patterns: List[str] = None, package_name: str = None) -> bool:
        """Generate stubs and install as PEP 561 package"""
        try:
            # Step 1: Generate stubs
            logger.info("🔧 Generating stubs...")
            self.generate_command.execute()

            stubs_dir = self.project_root / "stubs"
            if not stubs_dir.exists():
                logger.error("❌ No stubs directory found after generation")
                return False

            # Step 2: Determine package name
            if not package_name:
                # Try to infer from project structure
                package_name = self._infer_package_name()

            logger.info(f"📦 Installing as package: {package_name}")

            # Step 3: Create and install stub package
            return self._install_stub_package(stubs_dir, package_name)

        except Exception as e:
            logger.error(f"❌ Stub installation failed: {e}")
            return False

    def _infer_package_name(self) -> str:
        """Infer package name from project structure"""
        # Try to find pyproject.toml and extract name
        pyproject_path = self.project_root / "pyproject.toml"
        if pyproject_path.exists():
            try:
                import tomllib
                with open(pyproject_path, 'rb') as f:
                    data = tomllib.load(f)
                    project_name = data.get('project', {}).get('name')
                    if project_name:
                        return f"{project_name}-stubs"
            except Exception:
                pass

        # Fallback to directory name
        return f"{self.project_root.name}-stubs"

    def _install_stub_package(self, stubs_dir: Path, package_name: str) -> bool:
        """Create and install the stub package"""
        import tempfile

        temp_dir = tempfile.mkdtemp()
        temp_path = Path(temp_dir)

        logger.info(f"🔍 Debug: Using temp directory: {temp_path}")

        try:
            # Copy stubs to temp directory
            stubs_dest = temp_path / "stubs"
            shutil.copytree(stubs_dir, stubs_dest)

            # Create pyproject.toml
            # Create pyproject.toml with correct package configuration
            pyproject_content = f'''[build-system]
            requires = ["setuptools>=45", "wheel"]
            build-backend = "setuptools.build_meta"

            [project]
            name = "{package_name}"
            version = "0.1.0"
            description = "Type stubs for {package_name.replace('-stubs', '')}"
            classifiers = ["Typing :: Stubs Only"]

            [tool.setuptools]
            # Explicitly list the package
            packages = ["stubs"]
            include-package-data = true

            [tool.setuptools.package-data]
            # Include all .pyi files and py.typed
            stubs = ["*.pyi", "**/*.pyi", "py.typed"]
            '''
            pyproject_file = temp_path / "pyproject.toml"
            pyproject_file.write_text(pyproject_content)

            # Uninstall old version
            subprocess.run([
                sys.executable, "-m", "pip", "uninstall", package_name, "-y"
            ], capture_output=True)

            # Use regular install instead of editable install
            logger.info(f"🔍 Installing from {temp_path}")
            result = subprocess.run([
                sys.executable, "-m", "pip", "install", str(temp_path)
            ], capture_output=True, text=True)

            if result.returncode != 0:
                logger.error(f"❌ Installation failed: {result.stderr}")
                logger.error(f"❌ Installation stdout: {result.stdout}")
                return False

            logger.info(f"✅ Installed {package_name} successfully!")

            # Verify installation
            self._verify_installation_detailed(package_name)

            return True

        except Exception as e:
            logger.error(f"❌ Installation failed: {e}")
            return False
        finally:
            # Clean up temp directory
            shutil.rmtree(temp_path, ignore_errors=True)

    def _verify_installation_detailed(self, package_name: str):
        """Detailed verification of stub package installation"""

        logger.info("🔍 Starting verification...")

        try:
            # Simple pip show check
            result = subprocess.run([
                sys.executable, "-m", "pip", "show", package_name
            ], capture_output=True, text=True, timeout=10)

            if result.returncode == 0:
                logger.info("📋 Package found by pip")
            else:
                logger.warning("⚠️  Package not found by pip")

            # Direct site-packages check
            import site
            site_packages = site.getsitepackages()[0]
            logger.info(f"🔍 Checking site-packages: {site_packages}")

            # Look for package directories
            for item in Path(site_packages).iterdir():
                if package_name.replace('-', '_') in item.name.lower():
                    logger.info(f"✅ Found package directory: {item}")
                    if (item / "stubs").exists():
                        logger.info(f"✅ Stubs directory found in {item}")
                        logger.info(f"   Stubs contents: {list((item / 'stubs').iterdir())[:3]}")
                        return True

            logger.warning("⚠️  No stub package directory found")
            return False

        except subprocess.TimeoutExpired:
            logger.error("❌ Verification timed out")
            return False
        except Exception as e:
            logger.error(f"❌ Verification failed: {e}")
            return False