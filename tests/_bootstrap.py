import atexit
import os
import shutil
import tempfile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

TEST_TEMP_ROOT = ROOT / ".test-tmp"
TEST_TEMP_ROOT.mkdir(exist_ok=True)

os.environ["TEMP"] = str(TEST_TEMP_ROOT)
os.environ["TMP"] = str(TEST_TEMP_ROOT)
tempfile.tempdir = str(TEST_TEMP_ROOT)


def _cleanup_test_temp_root() -> None:
    if TEST_TEMP_ROOT.exists():
        shutil.rmtree(TEST_TEMP_ROOT, ignore_errors=True)


atexit.register(_cleanup_test_temp_root)
