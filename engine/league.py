"""The fictional league: ten clubs with original names, colours, formations and hidden strengths.

Squads are generated from a seed. Names come from invented first name and surname
pools, so no real player or club is represented.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from engine.models import Club, Player, PlayerTraits, Position, TeamTruth
from engine.rng import Generator, SeedTree

LEAGUE_SEED = 2026

# Hidden strengths are set like a real league table: two contenders, a mid-table pack and
# strugglers, with styles that vary (Northvale is strong but patient, Westholt cautious).
# club_id, name, primary, secondary, formation, truth (attack, defence, press, tempo) or None
_CLUBS: list[tuple[str, str, str, str, str, tuple[float, float, float, float] | None]] = [
    ("KR", "Kingsport Rovers", "#FF5A3C", "#111111", "4-3-3", (0.70, 0.62, 0.74, 0.64)),
    ("AV", "Ashford Vale", "#F5C542", "#111111", "4-4-2", (0.52, 0.56, 0.58, 0.46)),
    ("NA", "Northvale Athletic", "#3DDC97", "#0B2A1C", "4-2-3-1", (0.72, 0.68, 0.45, 0.50)),
    ("BF", "Bramley Forge", "#E84A8A", "#FFFFFF", "4-4-2", (0.38, 0.42, 0.45, 0.48)),
    ("CC", "Castlemere City", "#7FD1FF", "#0B1B2A", "4-3-3", (0.64, 0.58, 0.68, 0.70)),
    ("EA", "Eastwick Albion", "#F2F2F2", "#C81E3A", "3-5-2", (0.55, 0.50, 0.52, 0.55)),
    ("RU", "Redmarsh United", "#C81E3A", "#F2F2F2", "4-2-3-1", (0.58, 0.52, 0.60, 0.62)),
    ("TW", "Thornwick Wanderers", "#9B7BFF", "#111111", "4-3-3", (0.42, 0.40, 0.55, 0.58)),
    ("WH", "Westholt", "#FF9F1C", "#1A1A1A", "4-1-4-1", (0.46, 0.48, 0.40, 0.42)),
    ("SM", "Saltmoor Athletic", "#2EC4B6", "#FFFFFF", "4-4-2", (0.50, 0.60, 0.50, 0.44)),
]

# Squad numbers by position. The first ones listed start, in formation order.
_NUMBERS: dict[Position, list[int]] = {
    "GK": [1, 13],
    "DF": [2, 3, 4, 5, 12, 15],
    "MF": [6, 8, 10, 14, 16, 18],
    "FW": [7, 9, 11, 19],
}
_POSITION_ORDER: list[Position] = ["GK", "DF", "MF", "FW"]

_FIXED_NAMES = {
    ("KR", 10): "Rafael Okafor",
    ("KR", 9): "Dani Mensah",
    ("KR", 6): "Ike Salazar",
    ("KR", 4): "Jonah Pryce",
    ("AV", 9): "Tobias Brandt",
    ("AV", 5): "Marek Holm",
    ("AV", 8): "Callum Hale",
}

_FIRST = (
    "Aaron Abel Ade Amir Anton Arlo Ben Bruno Caio Cal Dario Deniz Eli Emil Ezra Felix Femi Gael Hugo Idris "
    "Ilan Ivo Jonas Jude Kai Kofi Lars Leon Luca Malik Mateo Milan Nico Noah Obi Oren Otto Pavel Quinn Rafa "
    "Remy Rio Sami Santi Seb Taro Teo Theo Toby Udo Vito Wes Yann Yusuf Zane Zeki"
).split()
_LAST = (
    "Achterberg Adeyemi Alcott Amberley Asante Bakker Barros Bellweather Brodie Calloway Castellan Corrigan "
    "Dalgaard Delacroix Duarte Eastman Ekwueme Fairlie Falconer Ferreira Gallard Gunnarsen Haddad Halloran "
    "Hartwell Ibarra Ingram Jansen Jovanic Kallis Kerrigan Kowal Lachance Lindqvist Lowther Madsen Marchetti "
    "Mbeki Mercer Moreau Nakamura Navarro Nwosu Oduya Okoro Orsini Pellegrin Quaresma Radley Renner Rossiter "
    "Sandoval Seddon Silvane Sorensen Talbot Tavares Thorne Ueda Vance Varga Vesely Whitlock Wynter Yilmaz "
    "Zamora Zielinski"
).split()

_TRAIT_MEANS: dict[Position, tuple[float, float, float, float]] = {
    # pace, passing, finishing, stamina
    "GK": (0.35, 0.48, 0.08, 0.60),
    "DF": (0.56, 0.55, 0.28, 0.62),
    "MF": (0.60, 0.68, 0.48, 0.66),
    "FW": (0.70, 0.58, 0.70, 0.58),
}


@dataclass(frozen=True)
class League:
    clubs: dict[str, Club]
    squads: dict[str, list[Player]]

    def player(self, player_id: str) -> Player:
        for squad in self.squads.values():
            for p in squad:
                if p.player_id == player_id:
                    return p
        raise KeyError(player_id)


def formation_lines(formation: str) -> list[int]:
    """Outfield players per line, back to front. "4-2-3-1" gives [4, 2, 3, 1]."""
    lines = [int(n) for n in formation.split("-")]
    if sum(lines) != 10:
        raise ValueError(f"formation {formation} does not have 10 outfield players")
    return lines


def _clip(v: float) -> float:
    return float(min(max(v, 0.05), 0.98))


def _truth(gen: Generator, fixed: tuple[float, float, float, float] | None) -> TeamTruth:
    if fixed is None:
        fixed = tuple(round(float(v), 2) for v in gen.uniform(0.32, 0.78, size=4))  # type: ignore[assignment]
    attack, defence, press, tempo = fixed
    return TeamTruth(attack=attack, defence=defence, press=press, tempo=tempo)


def _squad(club: Club, gen: Generator, used_names: set[str]) -> list[Player]:
    players: list[Player] = []
    quality = (club.truth.attack + club.truth.defence) / 2 - 0.5
    for position in _POSITION_ORDER:
        for number in _NUMBERS[position]:
            name = _FIXED_NAMES.get((club.club_id, number))
            if name is None:
                while name is None or name in used_names:
                    name = f"{gen.choice(_FIRST)} {gen.choice(_LAST)}"
                used_names.add(name)
            means = _TRAIT_MEANS[position]
            pace, passing, finishing, stamina = (
                _clip(m + 0.25 * quality + gen.normal(0, 0.11)) for m in means
            )
            players.append(
                Player(
                    player_id=f"{club.club_id}{number:02d}",
                    club_id=club.club_id,
                    name=name,
                    number=number,
                    position=position,
                    traits=PlayerTraits(
                        pace=round(pace, 3),
                        passing=round(passing, 3),
                        finishing=round(finishing, 3),
                        stamina=round(stamina, 3),
                    ),
                )
            )
    return players


@lru_cache(maxsize=4)
def build_league(seed: int = LEAGUE_SEED) -> League:
    tree = SeedTree(seed).child("league")
    used = set(_FIXED_NAMES.values())
    clubs: dict[str, Club] = {}
    squads: dict[str, list[Player]] = {}
    for club_id, name, primary, secondary, formation, fixed in _CLUBS:
        gen = tree.generator(club_id)
        club = Club(
            club_id=club_id,
            name=name,
            short=club_id,
            primary=primary,
            secondary=secondary,
            formation=formation,
            truth=_truth(gen, fixed),
        )
        clubs[club_id] = club
        squads[club_id] = _squad(club, gen, used)
    return League(clubs=clubs, squads=squads)
