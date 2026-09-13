"""Verdant Conclave social-deduction game package.

Keep package import lightweight: the pure engine can be tested without the
PostgreSQL/Discord runtime dependencies.
"""
from . import engine

__all__ = ["engine"]
