# PyInstaller spec for VDAS-Insight (one-file, windowed).
# Build from the repo root:  pyinstaller packaging/vdas-insight.spec
import os

from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))  # noqa: F821 (SPECPATH is injected)

# Ship the demo data so the "同梱サンプルを一括登録" button works out of the box.
datas = []
sample = os.path.join(ROOT, "sample_data")
if os.path.isdir(sample):
    datas.append((sample, "sample_data"))

# pyqtgraph does a lot of lazy importing; pull its submodules in explicitly,
# but skip examples/tests (importing them needs a display and aborts the build).
hiddenimports = collect_submodules(
    "pyqtgraph",
    filter=lambda name: ".examples" not in name and ".tests" not in name,
)

a = Analysis(
    [os.path.join(ROOT, "desktop", "main.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "streamlit", "playwright", "pytest",
              # not used by the app; avoids pulling a network/crypto stack
              "cryptography", "urllib3", "requests", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="VDAS-Insight",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,          # GUI app — no console window
    disable_windowed_traceback=False,
    argv_emulation=False,   # set True only if you want macOS file-open events
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
