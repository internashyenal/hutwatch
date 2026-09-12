from __future__ import annotations

import importlib

from hutwatch.providers.base import Provider


def load_provider(name: str) -> Provider:
    """Dynamically import hutwatch.providers.<name> as a Provider module."""
    module = importlib.import_module(f"hutwatch.providers.{name}")
    return module  # type: ignore[return-value]  # duck-typed against Provider Protocol
