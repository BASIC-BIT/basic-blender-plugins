"""Run every dependency-free test under branch coverage."""

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
ACTIVE_FEATURE_CORE = ",".join((
    "BASICs_shape_key_manager/core/weight_refit.py",
    "BASICs_shape_key_manager/core/clothing_*.py",
))


def _coverage(*arguments):
    return subprocess.run(
        [sys.executable, "-m", "coverage", *arguments],
        cwd=ROOT,
        check=False,
    ).returncode


def main():
    if _coverage("erase"):
        return 1
    tests = sorted((ROOT / "tests").rglob("test_*.py"))
    for index, path in enumerate(tests):
        arguments = ["run"]
        if index:
            arguments.append("--append")
        arguments.append(str(path))
        if _coverage(*arguments):
            return 1

    print("\nAll Blender-free core coverage (minimum 77.5%):", flush=True)
    if _coverage("report"):
        return 1
    print(
        "\nActively developed feature core (minimum 86.5%):",
        flush=True)
    if _coverage(
            "report", f"--include={ACTIVE_FEATURE_CORE}",
            "--fail-under=86.5"):
        return 1
    return _coverage("xml")


if __name__ == "__main__":
    raise SystemExit(main())
