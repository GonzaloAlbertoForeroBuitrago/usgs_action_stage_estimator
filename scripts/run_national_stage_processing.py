"""Run resumable national USGS stage processing with v0.3.1."""

from pathlib import Path
import sys
import time

from usgs_action_stage_estimator.national_stage_processing import (
    PROCESSING_PARAMETERS,
    discover_stage_sources,
    process_stage_inventory,
)

import usgs_stage_peaks


def main():
    root = Path.home() / "Documents/usgs_mrms_research"

    source_root = root / "data/stage_data"
    output_root = root / "outputs/national_stage_peaks_v031"

    if usgs_stage_peaks.__version__ != "0.3.1":
        raise RuntimeError("Expected usgs-stage-peaks v0.3.1")

    if PROCESSING_PARAMETERS["baseflow_alpha"] != 0.987:
        raise RuntimeError("Unexpected filtering alpha.")

    inventory = discover_stage_sources(source_root)

    assert len(inventory) == 8615
    assert int((inventory["source_status"] == "ready").sum()) == 8550
    assert int((inventory["source_status"] == "empty_input").sum()) == 65

    print("=" * 70, flush=True)
    print("P00 — NATIONAL USGS STAGE PROCESSING", flush=True)
    print("Package:", usgs_stage_peaks.__version__, flush=True)
    print("Alpha:", PROCESSING_PARAMETERS["baseflow_alpha"], flush=True)
    print("Source:", source_root, flush=True)
    print("Output:", output_root, flush=True)
    print("Stations:", len(inventory), flush=True)
    print("=" * 70, flush=True)

    start = time.perf_counter()

    results = process_stage_inventory(
        inventory,
        output_root,
    )

    print("\n=== FINAL STATUS ===", flush=True)
    print(results["status"].value_counts(dropna=False), flush=True)

    print(
        "Total elapsed hours:",
        round((time.perf_counter() - start) / 3600, 2),
        flush=True,
    )

    failures = results.loc[
        ~results["status"].isin([
            "completed",
            "already_completed",
            "empty_input",
        ])
    ]

    if not failures.empty:
        print("\nStations requiring review:", len(failures))
        print(failures.to_string(index=False))
        sys.exit(1)

    print("\nNATIONAL PROCESSING COMPLETED", flush=True)


if __name__ == "__main__":
    main()
