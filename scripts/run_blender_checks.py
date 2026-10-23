"""Build, install, and test the extension in an isolated Blender profile."""

import argparse
import os
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _run(blender, arguments, environment, expected=()):
    command = [str(blender), *map(str, arguments)]
    print("RUN", subprocess.list2cmdline(command), flush=True)
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
    )
    print(result.stdout, end="")
    if result.returncode:
        raise RuntimeError(
            f"Blender exited with {result.returncode}: "
            f"{subprocess.list2cmdline(command)}")
    missing = [marker for marker in expected if marker not in result.stdout]
    if missing:
        raise RuntimeError("Blender output missed markers: " + ", ".join(missing))
    return result.stdout


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--blender", required=True, type=Path)
    parser.add_argument("--expected-version", default="5.1.2")
    args = parser.parse_args(argv)
    blender = args.blender.resolve()
    if not blender.is_file():
        raise FileNotFoundError(blender)

    with tempfile.TemporaryDirectory(prefix="basic-blender-checks-") as temp:
        temporary = Path(temp)
        environment = os.environ.copy()
        user_resources = temporary / "user"
        user_resources.mkdir()
        environment["BLENDER_USER_RESOURCES"] = str(user_resources)
        for variable, directory in (
            ("BLENDER_USER_CONFIG", "config"),
            ("BLENDER_USER_SCRIPTS", "scripts"),
            ("BLENDER_USER_DATAFILES", "datafiles"),
        ):
            path = user_resources / directory
            path.mkdir()
            environment[variable] = str(path)
        archive = temporary / "basics_shape_key_manager.zip"

        _run(
            blender, ["--version"], environment,
            (f"Blender {args.expected_version}",))
        _run(blender, [
            "--factory-startup", "--command", "extension", "build",
            "--source-dir", ROOT / "BASICs_shape_key_manager",
            "--output-filepath", archive,
        ], environment)
        _run(blender, [
            "--command", "extension", "install-file",
            "-r", "user_default", "-e", archive,
        ], environment)
        _run(blender, [
            "--background", "--factory-startup", "--python-exit-code", "9",
            "--python", SCRIPTS / "verify_blender_factory_import.py",
        ], environment, ("BASIC_FACTORY_IMPORT_SMOKE_PASS",))
        _run(blender, [
            "--background", "--python-exit-code", "9",
            "--python", SCRIPTS / "verify_blender_registration.py",
        ], environment, ("BASIC_PLUGIN_STARTUP_SMOKE_PASS",))
        _run(blender, [
            "--background", "--python-exit-code", "9",
            "--python", SCRIPTS / "verify_weight_refit_blender.py",
            "--", "--installed-extension",
        ], environment, ("WEIGHT_REFIT_BLENDER_PASS",))
        for script, marker, installed in (
            ('verify_clothing_export_blender.py', 'CLOTHING_EXPORT_OK', True),
            ('verify_clothing_geometry_blender.py', 'CLOTHING_GEOMETRY_OK', True),
            ('verify_clothing_policy_blender.py', 'CLOTHING_POLICY_OK', True),
            ('verify_clothing_ik_blender.py', 'CLOTHING_IK_OK', True),
            ('verify_clothing_shoulders_blender.py', 'CLOTHING_SHOULDERS_OK', True),
            ('verify_clothing_checks_blender.py', 'CLOTHING_SESSION_OK', True),
            ('verify_clothing_session_regressions.py', 'CLOTHING_SESSION_REVIEW_OK', True),
            ('verify_clothing_inactive_sources.py', 'CLOTHING_INACTIVE_SOURCE_REOPEN_OK', True),
        ):
            arguments = ['--background', '--factory-startup', '--python-exit-code', '9',
                         '--python', SCRIPTS / script]
            if installed:
                arguments.extend(['--', '--installed-extension'])
            if script == 'verify_clothing_export_blender.py':
                arguments.extend(['--output-dir', temporary / 'export-fixture'])
            _run(blender, arguments, environment, (marker,))
    print("ALL_BLENDER_INTEGRATION_CHECKS_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
