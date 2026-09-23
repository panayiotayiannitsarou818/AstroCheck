from dataclasses import dataclass, field, asdict
from typing import Optional

@dataclass
class Point:
    code: str
    name: str
    sign: str
    degree: int
    minute: int
    second: int
    absolute: float
    house: Optional[int] = None
    retrograde: bool = False
    kind: str = "planet"

@dataclass
class Aspect:
    first: str
    second: str
    aspect: str
    orb: float
    orb_text: str
    weight: str
    source: str
    applying: Optional[bool] = None

@dataclass
class Chart:
    name: str = ""
    date: str = ""
    time: str = ""
    place: str = ""
    house_system: str = ""
    points: list[Point] = field(default_factory=list)
    cusps: list[Point] = field(default_factory=list)
    aspects: list[Aspect] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)

