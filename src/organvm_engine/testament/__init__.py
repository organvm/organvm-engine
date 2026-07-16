"""Testament — the system's generative self-portrait.

Every computational function in ORGANVM that transforms data is also a generative
function capable of producing a publishable artifact in its natural medium.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from organvm_engine.testament.catalog import TestamentArtifact
from organvm_engine.testament.iceberg_atlas import (
    AtlasCompileResult,
    IcebergAtlasCompiler,
    ReceiptIdentity,
    compile_iceberg_atlas,
)
from organvm_engine.testament.manifest import ArtifactModality, ArtifactType, OrganOutputProfile

__all__ = [
    "ArtifactModality",
    "ArtifactType",
    "AtlasCompileResult",
    "IcebergAtlasCompiler",
    "OrganOutputProfile",
    "ReceiptIdentity",
    "TestamentArtifact",
    "compile_iceberg_atlas",
    "get_testament_summary",
]


def get_testament_summary(
    registry_path: Path | None = None,
    catalog_dir: Path | None = None,
) -> dict[str, Any]:
    """Return a testament summary dict suitable for API responses.

    Assembles data from multiple testament subsystems into a single
    dict that external consumers (e.g., the stakeholder portal's
    ``/testament/`` route) can use directly.

    Returns:
        Dict with keys:
        - system: high-level system stats (repos, organs, status counts)
        - omega: scorecard data (criteria, met_count, total, met_ratio)
        - densities: per-organ AMMOI density (dict[str, float])
        - sonic: sonic self-portrait summary (voices, bpm, master)
        - catalog: artifact catalog stats (total, by_modality, by_organ, latest)
        - network: feedback network summary (nodes, edges, execution_order)
        - artifact_types: count of registered artifact types
    """
    from organvm_engine.testament.catalog import catalog_summary, load_catalog
    from organvm_engine.testament.manifest import MODULE_SOURCES, all_artifact_types
    from organvm_engine.testament.network import network_summary
    from organvm_engine.testament.renderers.sonic import render_sonic_params
    from organvm_engine.testament.sources import density_data, omega_data, system_summary

    # System summary
    sys_data = system_summary(registry_path)

    # Omega scorecard
    omega = omega_data(registry_path)
    met_ratio = omega["met_count"] / omega["total"] if omega["total"] else 0

    # Density
    dens = density_data(registry_path)

    # Sonic self-portrait (summary only)
    sonic = render_sonic_params(
        organ_densities=dens["organ_densities"],
        met_ratio=met_ratio,
        total_repos=sys_data.get("total_repos", 0),
    )

    # Catalog
    catalog = load_catalog(catalog_dir)
    cat_summary = catalog_summary(catalog)

    # Network
    net_summary = network_summary()

    return {
        "system": {
            "total_repos": sys_data.get("total_repos", 0),
            "total_organs": sys_data.get("total_organs", 0),
            "total_public": sys_data.get("total_public", 0),
            "status_counts": sys_data.get("status_counts", {}),
        },
        "omega": {
            "criteria": omega.get("criteria", []),
            "met_count": omega.get("met_count", 0),
            "total": omega.get("total", 17),
            "met_ratio": round(met_ratio, 4),
        },
        "densities": dens["organ_densities"],
        "sonic": {
            "voices": len(sonic.voices),
            "bpm": sonic.rhythm.bpm if sonic.rhythm else 120,
            "master_amplitude": sonic.master_amplitude,
            "time_signature": sonic.rhythm.time_signature if sonic.rhythm else "4/4",
        },
        "catalog": {
            "total": cat_summary.total,
            "by_modality": cat_summary.by_modality,
            "by_organ": cat_summary.by_organ,
            "latest_timestamp": cat_summary.latest_timestamp,
        },
        "network": {
            "nodes": net_summary["nodes"],
            "feedback_edges": net_summary["feedback_edges"],
            "execution_order": net_summary["execution_order"],
        },
        "artifact_types": len(all_artifact_types()),
        "source_modules": len(MODULE_SOURCES),
    }
