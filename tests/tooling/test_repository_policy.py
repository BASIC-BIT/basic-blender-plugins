import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "verify_repository", ROOT / "scripts" / "verify_repository.py"
)
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


def _git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _fixture(lines, baseline=None):
    temporary = tempfile.TemporaryDirectory()
    root = Path(temporary.name)
    _git(root, "init")
    (root / "sample.py").write_text("x\n" * lines, encoding="utf-8")
    policy = {
        "max_lines": 500,
        "warning_lines": 450,
        "oversized_baseline": baseline or {},
        "text_exemptions": [],
    }
    policy_path = root / "repository-policy.json"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    return temporary, root, policy_path


temporary, root, policy = _fixture(500)
try:
    errors, _warnings = VERIFY.check_file_lengths(root, policy)
    assert not errors, errors
finally:
    temporary.cleanup()

temporary, root, policy = _fixture(501)
try:
    errors, _warnings = VERIFY.check_file_lengths(root, policy)
    assert any("exceeds allowed 500" in error for error in errors), errors
finally:
    temporary.cleanup()

temporary, root, policy = _fixture(600, {"sample.py": 600})
try:
    errors, warnings = VERIFY.check_file_lengths(root, policy)
    assert not errors, errors
    assert any("BASELINE sample.py" in warning for warning in warnings), warnings
finally:
    temporary.cleanup()

temporary, root, policy = _fixture(601, {"sample.py": 600})
try:
    errors, _warnings = VERIFY.check_file_lengths(root, policy)
    assert any("exceeds allowed 600" in error for error in errors), errors
finally:
    temporary.cleanup()

temporary, root, policy = _fixture(500, {"sample.py": 600})
try:
    errors, _warnings = VERIFY.check_file_lengths(root, policy)
    assert any("stale oversized baseline" in error for error in errors), errors
finally:
    temporary.cleanup()

print("repository policy tests passed")
