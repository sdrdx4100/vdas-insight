"""Pytest bootstrap: isolate the metadata DB in a temp dir before importing vdas."""
import os
import tempfile
from pathlib import Path

# Must be set BEFORE any `vdas` import so config picks it up.
_TMP = Path(tempfile.mkdtemp(prefix="vdas_test_"))
os.environ["VDAS_DATA_DIR"] = str(_TMP)
os.environ["VDAS_DB_PATH"] = str(_TMP / "test.duckdb")
