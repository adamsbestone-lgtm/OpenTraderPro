# OpenTraderPro.spec
# pyinstaller packaging\OpenTraderPro.spec
from pathlib import Path

block_cipher = None
PROJECT_ROOT = Path(SPECPATH).parent

a = Analysis(
    [str(PROJECT_ROOT / "main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[
        (str(PROJECT_ROOT / "Bots"), "Bots"),
        (str(PROJECT_ROOT / "Plugins"), "Plugins"),
        (str(PROJECT_ROOT / "Workspace"), "Workspace"),
    ],
    hiddenimports=[
        "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets",
        "cryptography.fernet",
    ],
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[],
    noarchive=False, cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="OpenTraderPro",
    debug=False, bootloader_ignore_signals=False, strip=False, upx=True,
    console=False,
    icon=str(PROJECT_ROOT / "packaging" / "opentraderpro.ico") if (PROJECT_ROOT / "packaging" / "opentraderpro.ico").exists() else None,
)

coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=True, upx_exclude=[], name="OpenTraderPro",
)
