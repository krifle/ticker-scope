# -*- mode: python ; coding: utf-8 -*-
# ruff: noqa: F821

from PyInstaller.utils.hooks import collect_all


datas = [("app.py", ".")]
binaries = []
hiddenimports = []
excluded_submodule_markers = (
    ".tests",
    ".testing",
    ".conftest",
    ".hello",
)


def should_collect_submodule(name):
    return not any(marker in name for marker in excluded_submodule_markers)


for package in (
    "streamlit",
    "prophet",
    "cmdstanpy",
    "plotly",
    "yfinance",
    "holidays",
    "fear_greed",
):
    package_datas, package_binaries, package_hiddenimports = collect_all(
        package,
        filter_submodules=should_collect_submodule,
        exclude_datas=["**/tests/**", "**/testing/**", "**/conftest.py"],
    )
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports


a = Analysis(
    ["standalone.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "_pytest"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="TickerScope",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
