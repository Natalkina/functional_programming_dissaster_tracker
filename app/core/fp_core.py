"""
result adt is the core building block for error handling without exceptions.

instead of try/except, functions return Ok(value) or Err(reason).
callers compose results via map/flat_map, avoiding manual isinstance
branching at every call site.

we need 4 methods for referential transparency ala:
    Ok(foo)
    .flat_map(parse)
    .map(lambda: ...)
    .map_err(lambda e: ...)
    .unwrap_or((0)

    Ok[T]           — success wrapper
    Err[E]          — failure wrapper
    Result[T, E]    — tagged union (discriminated by match/case)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, TypeVar, Union

# we should NOT use Any, coz we'll lose parametric polymorphism entirely; I.e.
# the type checker will not help us 
T = TypeVar("T")
E = TypeVar("E")
U = TypeVar("U")
F = TypeVar("F")


@dataclass(frozen=True, slots=True)
class Ok(Generic[T]):
    """
    Degenerate product ADT: value AND Nothing (or None, what do you prefer)
    success branch — carries the computed value
    """
    value: T

    # lift a function over the success value, short-circuit on Err
    # i.e. it "cuts the wire" as soon as the result is determined skipping the Err logic
    def map(self, f: Callable[[T], U]) -> Ok[U]:
        return Ok(f(self.value))

    # chain a function that itself returns Result (monadic bind)
    def flat_map(self, f: Callable[[T], Result]) -> Result:
        return f(self.value)

    # in our code errors are str | object, so we can translate without touching success path
    def map_err(self, _f: Callable) -> Ok[T]:
        return self

    def unwrap_or(self, _default: U) -> T:
        return self.value


@dataclass(frozen=True, slots=True)
class Err(Generic[E]):
    """failure branch — carries the error reason"""
    error: E

    def map(self, _f: Callable) -> Err[E]:
        return self

    def flat_map(self, _f: Callable) -> Err[E]:
        return self

    # lift a function over the error value
    def map_err(self, f: Callable[[E], F]) -> Err[F]:
        return Err(f(self.error))

    def unwrap_or(self, default: U) -> U:
        return default


Result = Union[Ok[T], Err[E]] # ADT sum type, either Ok or Err
