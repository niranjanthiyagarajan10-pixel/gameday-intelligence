import pytest

from engine.league import build_league, formation_lines


def test_ten_fictional_clubs_with_unique_codes_names_and_colours():
    league = build_league()
    clubs = list(league.clubs.values())
    assert len(clubs) == 10
    assert len({c.short for c in clubs}) == 10
    assert len({c.name for c in clubs}) == 10
    assert len({c.primary for c in clubs}) == 10


def test_squads_have_18_unique_players_and_a_full_spine():
    league = build_league()
    ids, names = set(), set()
    for club_id, squad in league.squads.items():
        assert len(squad) == 18
        positions = [p.position for p in squad]
        assert positions.count("GK") == 2 and positions.count("FW") == 4
        for p in squad:
            assert p.club_id == club_id and p.player_id.startswith(club_id)
            ids.add(p.player_id)
            names.add(p.name)
    assert len(ids) == 180
    assert len(names) == 180


def test_demo_players_keep_their_names():
    league = build_league()
    assert league.player("KR10").name == "Rafael Okafor"
    assert league.player("AV09").name == "Tobias Brandt"


def test_league_is_reproducible_from_its_seed():
    fresh = build_league.__wrapped__(2026)
    assert fresh.clubs == build_league().clubs
    assert fresh.squads == build_league().squads
    assert build_league.__wrapped__(1).squads != fresh.squads


def test_every_club_has_a_profile_and_derby_rivals_point_at_each_other():
    from engine.league import PROFILES

    league = build_league()
    assert set(PROFILES) == set(league.clubs)
    assert len({p.nickname for p in PROFILES.values()}) == 10
    assert len({p.ground for p in PROFILES.values()}) == 10
    for club_id, p in PROFILES.items():
        if p.rival:
            assert PROFILES[p.rival].rival == club_id


def test_formation_lines():
    assert formation_lines("4-2-3-1") == [4, 2, 3, 1]
    with pytest.raises(ValueError):
        formation_lines("4-4-3")
