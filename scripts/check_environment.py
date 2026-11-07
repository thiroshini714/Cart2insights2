"""Check that the Python packages and database tools the project needs are really available.

Run from anywhere:   python scripts/check_environment.py

Why this exists: the project folder `streamlit/` (required by the brief) can shadow the real
`streamlit` package when Python is started in the project root, so a plain `import streamlit`
can "succeed" without the library being installed. This script removes the project root from
the import path, then verifies each package is a real installed distribution.
"""
from __future__ import annotations

import importlib.metadata as md
import importlib.util
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (import name, pip distribution name, required?)
PACKAGES = [
    ("pandas", "pandas", True), ("numpy", "numpy", True), ("scipy", "scipy", True),
    ("sqlalchemy", "SQLAlchemy", True), ("dotenv", "python-dotenv", True),
    ("matplotlib", "matplotlib", True), ("seaborn", "seaborn", True),
    ("plotly", "plotly", True), ("streamlit", "streamlit", True),
    ("pymysql", "PyMySQL", False),   # only needed when DB_BACKEND=mysql
    ("pptx", "python-pptx", False),  # only needed for scripts/build_presentation.py
    ("pytest", "pytest", False), ("jupyter", "jupyter", False),
]


def _without_project_root() -> None:
    """Drop the project root and the current directory from sys.path (shadowing guard)."""
    bad = {str(ROOT), str(Path.cwd()), "", "."}
    sys.path[:] = [p for p in sys.path if p not in bad and Path(p or ".").resolve() != ROOT]


def check_package(import_name: str, dist_name: str) -> tuple[bool, str]:
    spec = importlib.util.find_spec(import_name)
    if spec is None:
        return False, "not installed"
    origin = Path(spec.origin).resolve() if spec.origin else None
    if origin is None or ROOT in origin.parents:
        return False, f"found only a project folder at {origin or 'namespace path'}, not a real package"
    try:
        return True, md.version(dist_name)
    except md.PackageNotFoundError:
        return False, f"module found at {origin} but no installed distribution '{dist_name}'"


def main() -> int:
    _without_project_root()
    print(f"Python {sys.version.split()[0]} at {sys.executable}\n")
    missing_required, missing_optional = [], []
    for import_name, dist, required in PACKAGES:
        ok, info = check_package(import_name, dist)
        tag = "required" if required else "optional"
        print(f"  {'OK     ' if ok else 'MISSING'} {dist:<14} ({tag}) {info}")
        if not ok:
            (missing_required if required else missing_optional).append(dist)

    print("\nDatabase backend")
    backend = os.getenv("DB_BACKEND")
    if backend is None:
        env_file = ROOT / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.strip().startswith("DB_BACKEND="):
                    backend = line.split("=", 1)[1].strip()
    backend = (backend or "sqlite").lower()
    print(f"  DB_BACKEND = {backend}")
    print(f"  .env file  = {'present' if (ROOT / '.env').exists() else 'missing (copy .env.example)'}")
    try:
        import sqlite3
        print(f"  sqlite3 module: OK (SQLite {sqlite3.sqlite_version}; window functions need >= 3.25)")
    except ImportError:
        print("  sqlite3 module: MISSING")
    mysql_cli = shutil.which("mysql")
    print(f"  mysql client: {mysql_cli or 'not on PATH (optional: only for inspecting MySQL by hand)'}")

    raw = ROOT / "data" / "raw"
    n_raw = len(list(raw.glob("*.csv"))) if raw.exists() else 0
    print(f"\nData: {n_raw} CSV file(s) in data/raw (the pipeline needs the 9 dataset files)")

    if missing_required:
        print(f"\nMissing required packages: {', '.join(missing_required)}")
        print("Install with:  pip install -r requirements.txt")
        return 1
    print("\nAll required packages are installed." + (
        f" Optional missing: {', '.join(missing_optional)}." if missing_optional else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
