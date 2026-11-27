"""Shared MongoDB document helpers."""

from bson import ObjectId
from app.core.exceptions import NotFoundError


def parse_object_id(raw_id: str, resource_name: str = "Resource") -> ObjectId:
    """Validate and convert a hex string into a MongoDB ObjectId."""
    if not ObjectId.is_valid(raw_id):
        raise NotFoundError(f"{resource_name} not found.")
    return ObjectId(raw_id)
