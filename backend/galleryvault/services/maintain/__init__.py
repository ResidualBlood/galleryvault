"""Maintenance service domain package.

Holds the gallery-updates pipeline (normalization, detection, finalize) and the
favorites duplicates scan.  Leaf modules must not import the legacy
``updates_worker`` / ``favorites_worker`` facades.
"""
