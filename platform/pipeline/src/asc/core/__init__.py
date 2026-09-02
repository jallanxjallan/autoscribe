"""Dependency-safe system-wide helpers.

Modules in this package are deliberately small, broadly reusable primitives.
They must not import from any other ``asc`` package, which keeps them safe to
use from any layer without introducing circular dependencies.
"""
