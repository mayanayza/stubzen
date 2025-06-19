#!/usr/bin/env python3
"""
Minimal CLI tool for the stub generator
Configuration is handled via config.py variables
"""
import argparse
import logging
import sys
from pathlib import Path

from .commands.install import StubInstallCommand
from .utils.logging import configure_logging

from .commands.generate import StubGenerateCommand
from .commands.clean import StubCleanCommand
from .commands.watch import StubWatchCommand

def main():
    from .config import StubzenConfig
    StubzenConfig().load_config(Path.cwd())

    parser = argparse.ArgumentParser(
        description="Generate Python stub files for better type checking",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate stubs (uses config.py settings)
  python tools/stubzen/cli.py generate

  # Clean up all stub files (dry run first)
  python tools/stubzen/cli.py clean --dry-run
  python tools/stubzen/cli.py clean

  # Clean up stubs for specific modules
  python tools/stubzen/cli.py clean --modules common services

  # Watch for changes and auto-regenerate stubs
  python tools/stubzen/cli.py watch

Configuration is handled via config.py - modify BASE_CLASSES, MIXIN_CLASSES, etc.
        """
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )

    parser.add_argument(
        "--project-root",
        default=".",
        help="Project root directory (default: current directory)"
    )

    # Create subparsers for different commands
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # install command
    install_parser = subparsers.add_parser('install', help='Generate and install stubs as PEP 561 package')
    install_parser.add_argument(
        "--modules",
        nargs="*",
        help="Only generate stubs for modules matching these patterns"
    )
    install_parser.add_argument(
        "--package-name",
        help="Name for the stub package (default: PROJECT_NAME-stubs)"
    )

    # Generate command
    generate_parser = subparsers.add_parser('generate', help='Generate stub files')
    generate_parser.add_argument(
        "--modules",
        nargs="*",
        help="Only generate stubs for modules matching these patterns"
    )

    # Clean command
    clean_parser = subparsers.add_parser('clean', help='Clean up stub files')
    clean_parser.add_argument(
        "--modules",
        nargs="*",
        help="Only clean stubs for modules matching these patterns (if not specified, cleans all)"
    )
    clean_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting"
    )

    # Watch command
    watch_parser = subparsers.add_parser('watch', help='Watch files and auto-regenerate stubs')

    # Parse arguments
    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose or StubzenConfig.verbose_logging else logging.INFO
    configure_logging(log_level)

    logger = logging.getLogger(__name__)

    # If no command specified, default to generate
    if args.command is None:
        args.command = 'generate'

    try:
        if args.command == 'generate':
            logger.info("🚀 Starting stub generation...")
            command = StubGenerateCommand(args.project_root)
            success = command.execute()

            if success:
                logger.info("🎉 Stub generation completed successfully!")
                logger.info(f"💡 Generated stubs using '{StubzenConfig.stub_style}' style")
                if StubzenConfig.stub_style == "inline":
                    logger.info("📁 Stub files are now next to your .py files (.pyi)")
                    logger.warning("⚠️  Note: inline stubs can cause import issues where .pyi overrides .py imports")
                    logger.info("💡 Consider using 'module' style (set STUB_STYLE='module' in config.py)")
                elif StubzenConfig.stub_style == "module":
                    logger.info("📁 Stub files are in stubs/ directory")
                    logger.info("💡 Add 'mypy_path = \"stubs\"' to your pyproject.toml [tool.mypy] section")
                logger.info("🔧 Your IDE should now provide better type checking and autocomplete")
                sys.exit(0)
            else:
                logger.error("💥 Stub generation completed with errors")
                sys.exit(1)

        elif args.command == 'install':
            logger.info("🚀 Generating and installing stub package...")
            command = StubInstallCommand(args.project_root)
            success = command.execute(
                module_patterns=getattr(args, 'modules', None),
                package_name=getattr(args, 'package_name', None)
            )

            if success:
                logger.info("🎉 Stub package installed successfully!")
                sys.exit(0)
            else:
                logger.error("💥 Stub package installation failed")
                sys.exit(1)

        elif args.command == 'clean':
            logger.info("🧹 Starting stub cleanup...")
            command = StubCleanCommand(args.project_root)
            success = command.execute(getattr(args, 'modules', None), getattr(args, 'dry_run', False))

            if success:
                if getattr(args, 'dry_run', False):
                    logger.info("🎉 Cleanup preview completed successfully!")
                else:
                    logger.info("🎉 Stub cleanup completed successfully!")
                sys.exit(0)
            else:
                logger.error("💥 Stub cleanup completed with errors")
                sys.exit(1)

        elif args.command == 'watch':
            logger.info("👀 Starting file watcher for automatic stub regeneration...")
            command = StubWatchCommand(args.project_root)
            success = command.execute()

            if success:
                logger.info("🎉 File watcher completed successfully!")
                sys.exit(0)
            else:
                logger.error("💥 File watcher failed to start")
                sys.exit(1)

    except KeyboardInterrupt:
        logger.warning(f"\n⚠️  {args.command.title()} interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"💥 Unexpected error during {args.command}: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()