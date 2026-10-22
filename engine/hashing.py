"""Stable fingerprints of engine output, used by the determinism tests."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from pydantic import BaseModel


def stable_hash(items: Iterable[BaseModel]) -> str:
    """SHA-256 over the JSON of each item, in order. Same items give the same hash on any machine."""
    digest = hashlib.sha256()
    for item in items:
        digest.update(item.model_dump_json().encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()
