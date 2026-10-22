"""Seeded randomness. Every random draw in the engine goes through this module.

A SeedTree hands out named, independent random streams. The same root seed and
the same name always give the same stream, whatever order streams are asked for
in. That keeps matches reproducible even when new random features are added.
"""

from __future__ import annotations

import hashlib
from typing import Any

import numpy as np

# The one generator type the engine uses. Import it from here, not from numpy.random.
Generator = np.random.Generator


def _name_key(name: str) -> int:
    """Stable 32 bit key for a stream name. Python's hash() is salted, so it is not used."""
    return int.from_bytes(hashlib.sha256(name.encode("utf-8")).digest()[:4], "little")


class SeedTree:
    """A root seed plus a path of named branches."""

    def __init__(self, seed: int, path: tuple[int, ...] = ()) -> None:
        if seed < 0:
            raise ValueError("seed must be non-negative")
        self.seed = seed
        self.path = path

    def _sequence(self, name: str) -> np.random.SeedSequence:
        return np.random.SeedSequence(self.seed, spawn_key=self.path + (_name_key(name),))

    def generator(self, name: str) -> np.random.Generator:
        """An independent random stream for one named purpose, such as "passes"."""
        return np.random.Generator(np.random.PCG64(self._sequence(name)))

    def child(self, name: str) -> SeedTree:
        """A sub-tree, for example one per match inside a season."""
        return SeedTree(self.seed, self.path + (_name_key(name),))

    def forks(self, n: int) -> list[SeedTree]:
        """n independent sub-trees, for running alternative continuations of a match."""
        return [self.child(f"fork-{i}") for i in range(n)]


def rng_state(generator: np.random.Generator) -> dict[str, Any]:
    """The full state of a generator, as plain data that can be saved with a match snapshot."""
    return generator.bit_generator.state


def restore_rng(state: dict[str, Any]) -> np.random.Generator:
    """A generator that continues exactly where the saved one stopped."""
    bit_generator = np.random.PCG64()
    bit_generator.state = state
    return np.random.Generator(bit_generator)
