from __future__ import annotations

"""Central configuration package for field-driven metadata."""

from app.config.field_registry import FieldSpec, get_field_spec, has_field

__all__ = [
    "FieldSpec",
    "get_field_spec",
    "has_field",
]
