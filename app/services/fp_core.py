"""
Functional Programming core: Result ADT (Ok | Err).

    Ok[T]           — success wrapper
    Err[E]          — failure wrapper
    Result[T, E]    — tagged union (discriminated by isinstance)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar, Union

T = TypeVar("T")
E = TypeVar("E")


@dataclass(frozen=True)
class Ok(Generic[T]):
    """Success branch of Result."""
    value: T


@dataclass(frozen=True)
class Err(Generic[E]):
    """Failure branch of Result."""
    error: E


Result = Union[Ok[T], Err[E]]
