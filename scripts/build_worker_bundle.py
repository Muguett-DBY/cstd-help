import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DESTINATION = ROOT / ".worker-build"

ROOT_FILES = ("worker_entry.py",)
PACKAGE_FILES = {
    "analysis": ("__init__.py", "analyzer.py", "coach_contract.py", "evidence_contract.py"),
    "api": ("__init__.py", "normalization.py"),
}


def _copy_file(root, destination, relative_path):
    source = root / relative_path
    if not source.is_file():
        raise FileNotFoundError(f"Worker bundle source is missing: {source}")
    target = destination / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def build_worker_bundle(root=ROOT, destination=DEFAULT_DESTINATION):
    root = Path(root).resolve()
    destination = Path(destination).resolve()
    staging = destination.with_name(f"{destination.name}.tmp")

    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    try:
        for filename in ROOT_FILES:
            _copy_file(root, staging, Path(filename))

        for path in sorted((root / "worker").rglob("*.py")):
            if "__pycache__" not in path.parts:
                _copy_file(root, staging, path.relative_to(root))

        for package, filenames in PACKAGE_FILES.items():
            for filename in filenames:
                _copy_file(root, staging, Path(package) / filename)

        for path in sorted((root / "analysis" / "rules").glob("*.json")):
            _copy_file(root, staging, path.relative_to(root))

        if destination.exists():
            shutil.rmtree(destination)
        staging.replace(destination)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise

    return destination


if __name__ == "__main__":
    output = build_worker_bundle()
    print(f"Worker bundle ready: {output}")
