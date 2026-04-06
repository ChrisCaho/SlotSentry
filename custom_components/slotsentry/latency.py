"""SlotSentry latency profiling system.

Copyright (c) 2026 Chris Caho
SPDX-License-Identifier: MIT
Co-authored by Claude Code (Anthropic) under direction of Chris Caho.

Measures round-trip latency to each lock, maintains per-lock baselines,
and provides latency data to the commit engine for adaptive pacing.

Protocol-agnostic: works with any LockBackend that implements async_ping().
"""

from __future__ import annotations

import asyncio
import logging
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from .const import (
    LATENCY_DEEP_PING_COUNT,
    LATENCY_INTER_PING_DELAY,
    LATENCY_PROFILE_COOLDOWN,
    LATENCY_QUICK_PING_COUNT,
    LATENCY_VARIANCE_THRESHOLD,
)

if TYPE_CHECKING:
    from .lock_backend import LockBackend

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class LatencyProfile:
    """Per-lock latency measurement profile."""

    entity_id: str
    typical_latency: float | None = None  # Seconds, rolling median
    sample_count: int = 0
    last_profiled_at: str | None = None  # ISO 8601
    last_raw_samples: list[float] = field(default_factory=list)
    last_profile_failed: bool = False

    def to_dict(self) -> dict:
        """Serialize for storage."""
        return {
            "typical_latency": self.typical_latency,
            "sample_count": self.sample_count,
            "last_profiled_at": self.last_profiled_at,
            "last_raw_samples": self.last_raw_samples[-20:],  # Cap stored samples
            "last_profile_failed": self.last_profile_failed,
        }

    @classmethod
    def from_dict(cls, entity_id: str, data: dict) -> LatencyProfile:
        """Deserialize from storage."""
        return cls(
            entity_id=entity_id,
            typical_latency=data.get("typical_latency"),
            sample_count=data.get("sample_count", 0),
            last_profiled_at=data.get("last_profiled_at"),
            last_raw_samples=data.get("last_raw_samples", []),
            last_profile_failed=data.get("last_profile_failed", False),
        )


# ---------------------------------------------------------------------------
# LatencyProfiler
# ---------------------------------------------------------------------------


class LatencyProfiler:
    """Orchestrates latency measurement and profile management.

    Protocol-agnostic: calls backend.async_ping() which each backend
    implements with its own mechanism (Z-Wave ping, HTTP, ZCL read, etc.).
    """

    def __init__(self, backends: dict[str, LockBackend]) -> None:
        """Initialize with a mapping of entity_id → LockBackend."""
        self._backends = backends
        self._last_profile_time: float = 0.0
        self._profiling: bool = False

    @property
    def is_profiling(self) -> bool:
        """True if a profiling run is currently active."""
        return self._profiling

    async def async_quick_profile(
        self, entity_id: str, count: int = LATENCY_QUICK_PING_COUNT,
    ) -> list[float]:
        """Run `count` serial pings to one lock and return raw samples.

        Args:
            entity_id: Lock to ping.
            count: Number of pings.

        Returns:
            List of successful latency measurements (may be shorter than
            count if some pings failed).
        """
        backend = self._backends.get(entity_id)
        if backend is None:
            return []

        samples: list[float] = []
        for i in range(count):
            if i > 0:
                await asyncio.sleep(LATENCY_INTER_PING_DELAY)
            latency = await backend.async_ping()
            if latency is not None:
                samples.append(latency)

        return samples

    async def async_deep_profile(
        self, entity_id: str, count: int = LATENCY_DEEP_PING_COUNT,
    ) -> list[float]:
        """Run a deep profiling pass (many pings) and return raw samples."""
        return await self.async_quick_profile(entity_id, count=count)

    async def async_profile_all(
        self,
        profiles: dict[str, LatencyProfile],
    ) -> dict[str, LatencyProfile]:
        """Profile all locks. Quick pass first; deep pass if variance exceeds threshold.

        Locks are profiled serially to avoid mesh congestion.

        Args:
            profiles: Current stored profiles (updated in-place and returned).

        Returns:
            Updated profiles dict.
        """
        if self._profiling:
            _LOGGER.debug("LatencyProfiler: profiling already in progress, skipping")
            return profiles

        # Cooldown check
        now = time.monotonic()
        if now - self._last_profile_time < LATENCY_PROFILE_COOLDOWN:
            _LOGGER.debug(
                "LatencyProfiler: cooldown active (%.0fs remaining)",
                LATENCY_PROFILE_COOLDOWN - (now - self._last_profile_time),
            )
            return profiles

        self._profiling = True
        try:
            return await self._do_profile_all(profiles)
        finally:
            self._profiling = False
            self._last_profile_time = time.monotonic()

    async def _do_profile_all(
        self, profiles: dict[str, LatencyProfile],
    ) -> dict[str, LatencyProfile]:
        """Inner profiling loop."""
        timestamp = datetime.now(tz=timezone.utc).isoformat()

        for entity_id in self._backends:
            profile = profiles.get(entity_id) or LatencyProfile(entity_id=entity_id)

            _LOGGER.info(
                "LatencyProfiler: quick-profiling %s (%d pings)",
                entity_id,
                LATENCY_QUICK_PING_COUNT,
            )
            quick_samples = await self.async_quick_profile(entity_id)

            if not quick_samples:
                # Lock unreachable — preserve existing baseline.
                _LOGGER.warning(
                    "LatencyProfiler: %s unreachable during profiling; "
                    "preserving existing baseline (%.3fs)",
                    entity_id,
                    profile.typical_latency or 0.0,
                )
                profile.last_profile_failed = True
                profile.last_profiled_at = timestamp
                profiles[entity_id] = profile
                continue

            quick_median = statistics.median(quick_samples)
            profile.last_profile_failed = False

            # Check if we need deep profiling.
            needs_deep = False
            if profile.typical_latency is None:
                # First profile — use quick result as baseline.
                _LOGGER.info(
                    "LatencyProfiler: %s first profile — baseline %.3fs",
                    entity_id,
                    quick_median,
                )
            else:
                variance = abs(quick_median - profile.typical_latency) / profile.typical_latency
                if variance > LATENCY_VARIANCE_THRESHOLD:
                    needs_deep = True
                    _LOGGER.info(
                        "LatencyProfiler: %s variance %.0f%% exceeds %.0f%% "
                        "threshold (quick=%.3fs, baseline=%.3fs) — deep profiling",
                        entity_id,
                        variance * 100,
                        LATENCY_VARIANCE_THRESHOLD * 100,
                        quick_median,
                        profile.typical_latency,
                    )
                else:
                    _LOGGER.debug(
                        "LatencyProfiler: %s within tolerance (quick=%.3fs, "
                        "baseline=%.3fs, variance=%.0f%%)",
                        entity_id,
                        quick_median,
                        profile.typical_latency,
                        variance * 100,
                    )

            all_samples = quick_samples
            if needs_deep:
                deep_samples = await self.async_deep_profile(entity_id)
                all_samples = quick_samples + deep_samples
                if not deep_samples:
                    _LOGGER.warning(
                        "LatencyProfiler: %s deep profile failed; "
                        "using quick samples only",
                        entity_id,
                    )

            # Use median (robust to outliers from S0 nonce timeouts).
            new_median = statistics.median(all_samples)

            profile.typical_latency = round(new_median, 4)
            profile.sample_count = len(all_samples)
            profile.last_profiled_at = timestamp
            profile.last_raw_samples = [round(s, 4) for s in all_samples]
            profiles[entity_id] = profile

            _LOGGER.info(
                "LatencyProfiler: %s profile updated — typical=%.3fs "
                "(%d samples, %s)",
                entity_id,
                new_median,
                len(all_samples),
                "deep" if needs_deep else "quick",
            )

            # Brief pause between locks to let the mesh settle.
            await asyncio.sleep(LATENCY_INTER_PING_DELAY)

        return profiles
