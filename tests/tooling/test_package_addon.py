import importlib.util
from pathlib import Path
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "package_addon", ROOT / "scripts" / "package_addon.py"
)
PACKAGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACKAGE)


with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    source = root / "addon"
    cache = source / "__pycache__"
    cache.mkdir(parents=True)
    (source / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (cache / "module.pyc").write_bytes(b"compiled")
    archive = root / "addon.zip"

    PACKAGE.create_zip(source, archive)

    with zipfile.ZipFile(archive) as result:
        names = result.namelist()
    assert names == ["addon/module.py"], names

print("package addon tests passed")
