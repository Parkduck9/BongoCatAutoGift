# PyInstaller build: .venv\Scripts\pyinstaller BongoHelper.spec --noconfirm
# One-file console exe. The OCR model is bundled; config/templates/logs are created next to the exe.
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = collect_all("rapidocr")
datas += [("models/korean_PP-OCRv5_rec_mobile.onnx", "models")]

a = Analysis(
    ["bongo.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["pytest", "tkinter.test", "matplotlib", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="BongoHelper",
    console=True,
    upx=False,
)
