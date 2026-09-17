"""The contract every refresh layer satisfies (C§5).

Deliberately free of xarray at runtime: the probe job imports this module to read
`REGISTRY` and must not drag the spatial stack in to ask whether a catalogue answers.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, model_validator

from seagarden_dst.artifact.grid import GridSpec
from seagarden_dst.artifact.manifest import LayerProvenance

if TYPE_CHECKING:  # pragma: no cover - typing only
    import xarray as xr


class YearRange(BaseModel):
    """The span a refresh covers (C§10 clause 1), inclusive at both ends."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    start: int
    end: int

    @model_validator(mode="after")
    def _check_end_does_not_precede_start(self) -> YearRange:
        if self.end < self.start:
            raise ValueError(
                f"end year {self.end} precedes start year {self.start}: a refresh "
                "covers an inclusive span, so an inverted range would silently "
                "build nothing"
            )
        return self

    def years(self) -> list[int]:
        return list(range(self.start, self.end + 1))


ProbeStatus = Literal["ok", "absent", "version_drift", "unreachable"]


class ProbeResult(BaseModel):
    """One layer's answer to 'do you still exist, at the version we publish?' (C§8.2).

    `reachable` was the whole answer while the probe was an HTTP HEAD: the page
    loaded or it did not. The catalogue probe distinguishes three failures that a
    single boolean flattened into one, and the operator reading a red monthly job
    needs to tell them apart — a retired `dataset_id` is a data-availability
    emergency, a drifted version is a manifest correction, and a network error is
    something to retry.

    `reachable` is kept rather than derived so that C-b's callers and
    `format_probe_report` keep working, and the validator below makes the redundancy
    safe: the two fields cannot disagree.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    status: ProbeStatus
    reachable: bool
    detail: str

    @model_validator(mode="after")
    def _check_status_agrees_with_reachable(self) -> ProbeResult:
        expected = self.status == "ok"
        if self.reachable != expected:
            raise ValueError(
                f"reachable={self.reachable} contradicts status={self.status!r}: "
                f"reachable must be {expected} when status is {self.status!r}. The "
                "two fields are one fact; a result that disagrees with itself would "
                "print green and read red"
            )
        return self


@runtime_checkable
class Layer(Protocol):
    """One layer, one dataset (C§5).

    Five members, not C§5's four. `build` takes the year range (R1) because a refresh
    is named by its span, and `baseline_years` exists (R2) because the window a
    variable rests on cannot be read off its dimensions: `significant_wave_m` has no
    `year` dim and a 2023-2025 window, which is the case C§4.4 calls out by name.

    A layer may ignore the `years` it is given — the wave window is fixed by C§3.2 —
    but it must then say so through `baseline_years`.
    """

    name: str

    def probe(self) -> ProbeResult: ...

    def build(self, grid: GridSpec, years: YearRange, workdir: Path) -> xr.Dataset: ...

    def provenance(self) -> LayerProvenance: ...

    def baseline_years(self) -> dict[str, list[int]]: ...


# The five layers C-c implements. One layer, one dataset (C§5).
LAYER_NAMES: tuple[str, ...] = (
    "copernicus_phy",
    "copernicus_bgc",
    "copernicus_bgc_light",
    "copernicus_wav",
    "emodnet_bathy",
)

# The layers whose coverage the `valid` intersection is taken over (C§3.5).
# `copernicus_bgc_light` is absent because its only output is derived and it shares
# the BGC footprint, so it adds no independent constraint (R4).
COVERAGE_LAYERS: tuple[str, ...] = (
    "copernicus_phy",
    "copernicus_bgc",
    "copernicus_wav",
    "emodnet_bathy",
)
