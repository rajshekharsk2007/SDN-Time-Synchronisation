#!/usr/bin/env python3
"""
Analyse the Static QoS and Dynamic QoS time-synchronisation experiment results.

Expected project layout:
  Source_Code/final_analysis.py
  Results/Static_QoS/static_fresh_1.csv
  Results/Static_QoS/static_fresh_2.csv
  Results/Static_QoS/static_fresh_3b.csv
  Results/dynamic_fresh_1.csv
  Results/dynamic_fresh_2.csv
  Results/dynamic_fresh_3.csv

Each measurement CSV must contain:
  request, offset_ms, rtt_ms, sync_error_ms

The script writes freshly calculated summaries and comparison graphs to:
  Results/Final_Comparison/Generated_Analysis/

Install plotting dependency with:
  python -m pip install matplotlib

Run from the project root or any directory:
  python Source_Code/final_analysis.py
"""

import argparse
import csv
import statistics
from pathlib import Path

TRIAL_FILES = {
    "Static QoS": [
        Path("Results/Static_QoS/static_fresh_1.csv"),
        Path("Results/Static_QoS/static_fresh_2.csv"),
        Path("Results/Static_QoS/static_fresh_3b.csv"),
    ],
    "Dynamic QoS": [
        Path("Results/dynamic_fresh_1.csv"),
        Path("Results/dynamic_fresh_2.csv"),
        Path("Results/dynamic_fresh_3.csv"),
    ],
}
METRICS = ("rtt_ms", "sync_error_ms", "offset_ms")


def read_measurements(csv_path):
    """Read successful request measurements from one trial CSV."""
    rows = []
    with csv_path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"request", *METRICS}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(
                f"{csv_path} must contain columns: "
                + ", ".join(sorted(required))
            )

        for line_number, row in enumerate(reader, start=2):
            try:
                rows.append({
                    "request": int(row["request"]),
                    "offset_ms": float(row["offset_ms"]),
                    "rtt_ms": float(row["rtt_ms"]),
                    "sync_error_ms": float(row["sync_error_ms"]),
                })
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid measurement in {csv_path}, line {line_number}"
                ) from exc

    if not rows:
        raise ValueError(f"No measurements found in {csv_path}")
    return rows


def mean_or_zero(values):
    return statistics.mean(values) if values else 0.0


def analyse_project(project_root, expected_requests):
    trial_rows = []
    scenario_trials = {}

    for scenario, relative_paths in TRIAL_FILES.items():
        scenario_trials[scenario] = []
        for index, relative_path in enumerate(relative_paths, start=1):
            csv_path = project_root / relative_path
            if not csv_path.is_file():
                raise FileNotFoundError(f"Required trial file not found: {csv_path}")

            measurements = read_measurements(csv_path)
            successful = len(measurements)
            if successful > expected_requests:
                raise ValueError(
                    f"{csv_path} has {successful} rows, exceeding "
                    f"--expected-requests {expected_requests}"
                )

            values = {
                metric: [item[metric] for item in measurements]
                for metric in METRICS
            }
            record = {
                "scenario": scenario,
                "trial": f"{scenario.split()[0]} Trial {index}",
                "requests": expected_requests,
                "successful": successful,
                "failed": expected_requests - successful,
                "success_rate_percent": successful / expected_requests * 100,
                "average_rtt_ms": mean_or_zero(values["rtt_ms"]),
                "average_sync_error_ms": mean_or_zero(values["sync_error_ms"]),
                "average_offset_ms": mean_or_zero(values["offset_ms"]),
                "source_file": relative_path.as_posix(),
            }
            trial_rows.append(record)
            scenario_trials[scenario].append(record)

    scenario_rows = []
    for scenario, records in scenario_trials.items():
        rtt_means = [record["average_rtt_ms"] for record in records]
        error_means = [record["average_sync_error_ms"] for record in records]
        total_requests = sum(record["requests"] for record in records)
        total_successful = sum(record["successful"] for record in records)

        scenario_rows.append({
            "scenario": scenario,
            "trials": len(records),
            "total_requests": total_requests,
            "average_rtt_ms": statistics.mean(rtt_means),
            "rtt_sd_ms": statistics.stdev(rtt_means) if len(rtt_means) > 1 else 0.0,
            "average_sync_error_ms": statistics.mean(error_means),
            "sync_error_sd_ms": statistics.stdev(error_means) if len(error_means) > 1 else 0.0,
            "success_rate_percent": (
                total_successful / total_requests * 100 if total_requests else 0.0
            ),
        })

    return trial_rows, scenario_rows


def write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def create_graphs(output_dir, scenario_rows):
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError(
            "Matplotlib is required to generate graphs. Install it using: "
            "python -m pip install matplotlib"
        ) from exc

    labels = [row["scenario"] for row in scenario_rows]
    charts = [
        ("average_rtt_ms", "Average RTT (ms)", "average_rtt_comparison.png"),
        (
            "average_sync_error_ms",
            "Average synchronisation error (ms)",
            "sync_error_comparison.png",
        ),
        (
            "success_rate_percent",
            "Successful requests (%)",
            "success_rate_comparison.png",
        ),
    ]

    output_dir.mkdir(parents=True, exist_ok=True)
    for metric, y_label, filename in charts:
        values = [row[metric] for row in scenario_rows]
        fig, ax = plt.subplots(figsize=(7, 4.5))
        bars = ax.bar(labels, values)
        ax.set_title(y_label + " — Static QoS vs Dynamic QoS")
        ax.set_ylabel(y_label)
        ax.grid(axis="y", linestyle="--", alpha=0.35)
        ax.set_axisbelow(True)
        ax.bar_label(bars, fmt="%.3f")
        fig.tight_layout()
        fig.savefig(output_dir / filename, dpi=160)
        plt.close(fig)


def main():
    parser = argparse.ArgumentParser(
        description="Analyse Static QoS and Dynamic QoS experiment CSV files."
    )
    parser.add_argument(
        "--expected-requests",
        type=int,
        default=20,
        help="Expected requests in each trial (default: 20, as used in the report).",
    )
    args = parser.parse_args()
    if args.expected_requests < 1:
        parser.error("--expected-requests must be at least 1")

    project_root = Path(__file__).resolve().parent.parent
    output_dir = project_root / "Results" / "Final_Comparison" / "Generated_Analysis"

    trial_rows, scenario_rows = analyse_project(project_root, args.expected_requests)

    trial_fields = [
        "scenario", "trial", "requests", "successful", "failed",
        "success_rate_percent", "average_rtt_ms",
        "average_sync_error_ms", "average_offset_ms", "source_file",
    ]
    scenario_fields = [
        "scenario", "trials", "total_requests", "average_rtt_ms",
        "rtt_sd_ms", "average_sync_error_ms", "sync_error_sd_ms",
        "success_rate_percent",
    ]

    write_csv(output_dir / "trial_summary.csv", trial_rows, trial_fields)
    write_csv(output_dir / "scenario_summary.csv", scenario_rows, scenario_fields)
    create_graphs(output_dir, scenario_rows)

    print("Analysis completed.")
    print(f"Output folder: {output_dir}")
    for row in scenario_rows:
        print(
            f'{row["scenario"]}: mean RTT={row["average_rtt_ms"]:.4f} ms, '
            f'mean sync error={row["average_sync_error_ms"]:.4f} ms, '
            f'success rate={row["success_rate_percent"]:.1f}%'
        )
    print(
        "\nNote: the measurement CSV files contain successful exchanges only. "
        "Failed requests are estimated as expected requests minus recorded rows."
    )


if __name__ == "__main__":
    main()
