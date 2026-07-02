import csv
import json
import math
import statistics
from pathlib import Path


INPUT = Path("/input/data.csv")
OUTPUT = Path("/output/statistics.json")
MAX_ROWS = 100_000
MAX_COLUMNS = 256
MAX_CELL_CHARACTERS = 16_384


def analyze_csv(input_path: Path, output_path: Path) -> None:
    with input_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if (
            not reader.fieldnames
            or len(reader.fieldnames) > MAX_COLUMNS
            or any(not name for name in reader.fieldnames)
            or len(set(reader.fieldnames)) != len(reader.fieldnames)
        ):
            raise ValueError("invalid_columns")
        columns = {name: {"values": [], "missingCount": 0} for name in reader.fieldnames}
        row_count = 0
        for row in reader:
            row_count += 1
            if row_count > MAX_ROWS:
                raise ValueError("too_many_rows")
            if None in row:
                raise ValueError("invalid_row")
            for name in reader.fieldnames:
                value = row.get(name)
                if value is None or len(value) > MAX_CELL_CHARACTERS:
                    raise ValueError("invalid_cell")
                if not value.strip():
                    columns[name]["missingCount"] += 1
                    continue
                try:
                    number = float(value)
                except ValueError:
                    continue
                if math.isfinite(number):
                    columns[name]["values"].append(number)

    summary = {}
    for name, state in columns.items():
        values = state["values"]
        statistics_payload = {
            "missingCount": state["missingCount"],
            "numericCount": len(values),
        }
        if values:
            quartiles = statistics.quantiles(values) if len(values) >= 3 else [min(values), statistics.median(values), max(values)]
            statistics_payload.update({
                "min": min(values),
                "max": max(values),
                "mean": statistics.fmean(values),
                "median": statistics.median(values),
                "sampleStandardDeviation": statistics.stdev(values) if len(values) >= 2 else None,
                "quartiles": quartiles,
            })
        summary[name] = statistics_payload
    payload = {"schemaVersion": "1.0", "rowCount": row_count, "columns": summary}
    output_path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def main() -> None:
    analyze_csv(INPUT, OUTPUT)


if __name__ == "__main__":
    main()
