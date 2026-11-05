"""Immutable one-day class schedules, expressed in minutes from midnight."""
from dataclasses import dataclass
import math
from numbers import Real
import re


def finite_number(value, name: str, *, minimum: float = 0,
                  strictly_positive: bool = False) -> float:
    """Validate numeric configuration without accepting bools or numeric strings."""
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f'{name} must be a finite number')
    number = float(value)
    if number < minimum or (strictly_positive and number <= 0):
        raise ValueError(f'{name} must be {"positive" if strictly_positive else f">= {minimum}"}')
    return number


def parse_time(value: str | int | float) -> float:
    """Accept HH:MM or numeric minutes, including 24:00 as the day endpoint."""
    if isinstance(value, str):
        if not re.fullmatch(r'\d{2}:\d{2}', value):
            raise ValueError(f'Invalid time {value!r}; use HH:MM')
        hour, minute = map(int, value.split(':'))
        if minute >= 60 or hour > 24 or (hour == 24 and minute != 0):
            raise ValueError(f'Invalid time {value!r}; expected 00:00 through 24:00')
        return float(hour * 60 + minute)
    number = finite_number(value, 'time')
    if number > 1440:
        raise ValueError('time must be between 0 and 1440 minutes')
    return number


@dataclass(frozen=True)
class ClassSession:
    destination: str
    start_minute: float
    end_minute: float
    course: str = ''

    def __post_init__(self):
        if not isinstance(self.destination, str) or not self.destination.strip():
            raise ValueError('Class destination must be a nonempty node code')
        if not isinstance(self.course, str):
            raise ValueError('Course label must be a string')
        start = finite_number(self.start_minute, 'class start')
        end = finite_number(self.end_minute, 'class end')
        if not 0 <= start < end <= 1440:
            raise ValueError('Class requires 0 <= start < end <= 1440')
        object.__setattr__(self, 'start_minute', start)
        object.__setattr__(self, 'end_minute', end)


def validate_schedule(entries: list[ClassSession]) -> tuple[ClassSession, ...]:
    if not isinstance(entries, (list, tuple)) or any(not isinstance(e, ClassSession) for e in entries):
        raise ValueError('Schedule must be a list of ClassSession records')
    ordered = tuple(sorted(entries, key=lambda e: e.start_minute))
    if any(a.end_minute > b.start_minute for a, b in zip(ordered, ordered[1:])):
        raise ValueError('Student classes must not overlap')
    return ordered
