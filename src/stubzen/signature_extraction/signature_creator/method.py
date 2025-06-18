import inspect
from typing import Type, Optional, Any

from ...constants import VOID_METHODS
from ..dataclasses import SignatureInfo, MissingAnnotation
from .base import SignatureCreator


class MethodSignatureCreator(SignatureCreator):
    """Creates signatures for regular methods with enhanced missing annotation detection"""

    def can_handle(self, obj, context: dict) -> bool:
        return inspect.ismethod(obj) or inspect.isfunction(obj)

    def create_signature(self, name: str, obj, defining_class: Type, context: dict) -> Optional[SignatureInfo]:
        try:
            sig = inspect.signature(obj)
            params = []
            param_types = {}
            missing_annotations = context.get('missing_annotations', [])
            target_class_name = context.get('target_class_name', defining_class.__name__)

            for param_name, param in sig.parameters.items():
                if param_name == 'self':
                    continue

                param_str = param_name

                if param.annotation != inspect.Parameter.empty:
                    try:
                        param_type = param.annotation
                        self.type_resolver.track_type(param_type)
                        param_types[param_name] = param_type
                        param_str += f": {self.type_resolver.format_type(param_type)}"
                    except (TypeError, ValueError) as e:
                        self.logger.warning(f"Skipping problematic type annotation for {name}.{param_name}: {e}")
                        param_types[param_name] = Any
                        param_str += ": Any"
                else:
                    # Track missing parameter annotations
                    missing_annotation = MissingAnnotation(
                        class_name=target_class_name,
                        class_module=defining_class.__module__,
                        member_name=f"{name}.{param_name}",
                        member_type="method_parameter",
                        details=f"parameter in {name}()"
                    )
                    missing_annotations.append(missing_annotation)
                    param_types[param_name] = Any
                    param_str += ": Any"

                if param.default != inspect.Parameter.empty:
                    param_str += self._format_default_value(param.default)

                params.append(param_str)

            # Handle return type
            return_type = None
            return_annotation = ""

            if sig.return_annotation != inspect.Parameter.empty:
                try:
                    return_type = sig.return_annotation
                    self.type_resolver.track_type(return_type)
                    return_annotation = f" -> {self.type_resolver.format_type(return_type)}"
                except (TypeError, ValueError) as e:
                    self.logger.warning(f"Skipping problematic return type annotation for {name}: {e}")
                    return_type = Any
                    return_annotation = " -> Any"
            else:
                # Track missing return type annotations (but only for non-void methods)
                if name not in VOID_METHODS:
                    missing_annotation = MissingAnnotation(
                        class_name=target_class_name,
                        class_module=defining_class.__module__,
                        member_name=name,
                        member_type="method_return",
                        details="missing return type annotation"
                    )
                    missing_annotations.append(missing_annotation)

            params_str = ", ".join(params)
            raw_signature = f"def {name}(self{', ' + params_str if params_str else ''}){return_annotation}: ..."

            return SignatureInfo(
                name=name,
                signature_type="method",
                raw_signature=raw_signature,
                return_type=return_type,
                param_types=param_types
            )

        except Exception as e:
            self.logger.error(f"Error extracting method signature for {name}: {e}")
            return SignatureInfo(
                name=name,
                signature_type="method",
                raw_signature=f"def {name}(self, *args, **kwargs): ...",
                details="extraction error"
            )