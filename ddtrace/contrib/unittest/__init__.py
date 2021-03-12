from ...utils.importlib import require_modules


required_modules = ["unittest"]

with require_modules(required_modules) as missing_modules:
    if not missing_modules:
        from .patch import patch

        __all__ = ["patch", "unpatch"]
