"""Build-time data pipeline for durable MLB snapshots."""

from .schema import AppearanceRecord, FetchStateRecord, GameRecord, Snapshot

__all__ = ["AppearanceRecord", "FetchStateRecord", "GameRecord", "Snapshot"]
