import numpy as np
import pytest

from engine.rng import SeedTree, restore_rng, rng_state


def draws(gen: np.random.Generator, n: int = 8) -> list[float]:
    return gen.random(n).tolist()


def test_same_seed_and_name_give_same_stream():
    assert draws(SeedTree(7).generator("passes")) == draws(SeedTree(7).generator("passes"))


def test_streams_do_not_depend_on_request_order():
    a = SeedTree(7)
    a_passes, a_shots = draws(a.generator("passes")), draws(a.generator("shots"))
    b = SeedTree(7)
    b_shots, b_passes = draws(b.generator("shots")), draws(b.generator("passes"))
    assert a_passes == b_passes
    assert a_shots == b_shots


def test_different_names_and_seeds_give_different_streams():
    tree = SeedTree(7)
    assert draws(tree.generator("passes")) != draws(tree.generator("shots"))
    assert draws(SeedTree(7).generator("passes")) != draws(SeedTree(8).generator("passes"))


def test_child_trees_are_independent_and_reproducible():
    root = SeedTree(7)
    match_1 = root.child("match-1")
    assert draws(match_1.generator("passes")) != draws(root.generator("passes"))
    assert draws(match_1.generator("passes")) == draws(SeedTree(7).child("match-1").generator("passes"))
    assert draws(match_1.generator("passes")) != draws(root.child("match-2").generator("passes"))


def test_forks_are_distinct_and_reproducible():
    forks = SeedTree(7).forks(4)
    streams = [draws(f.generator("sim")) for f in forks]
    assert len({tuple(s) for s in streams}) == 4
    assert streams == [draws(f.generator("sim")) for f in SeedTree(7).forks(4)]


def test_saved_state_continues_exactly():
    gen = SeedTree(7).generator("sim")
    gen.random(100)
    saved = rng_state(gen)
    expected = draws(gen)
    assert draws(restore_rng(saved)) == expected


def test_negative_seed_rejected():
    with pytest.raises(ValueError):
        SeedTree(-1)
