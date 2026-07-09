# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller 빌드 설정 파일.
# 윈도우에서 다음 한 줄로 exe를 만든다:
#
#     pyinstaller drone.spec
#
# 결과물: dist/DroneApp.exe  (파일 하나. 더블클릭하면 브라우저가 열린다.)
# 소스 파일(.py, models/, templates/)은 지워지지 않는다. 빌드 결과만 build/, dist/ 에 새로 생긴다.

import glob
from PyInstaller.utils.hooks import collect_all

# --- exe 안에 함께 넣을 파일들 ------------------------------------------------
# models/ 폴더의 모든 .pt 모델을 exe 안 models/ 위치에 그대로 넣는다.
# (best.pt, yolov8n-pose-test4.pt, yolo11n.pt, yolov8n.pt 등 넣어둔 건 전부 포함)
model_datas = [(p, "models") for p in glob.glob("models/*.pt")]

# HTML/정적 템플릿도 templates/ 위치에 넣는다.
template_datas = [(p, "templates") for p in glob.glob("templates/*")]

datas = model_datas + template_datas
binaries = []
hiddenimports = []

# ultralytics(YOLO), djitellopy 는 부속 데이터 파일·숨은 import 가 많아 통째로 수집한다.
# 패키징 오류(모듈/파일 누락)가 나면 대개 이 목록에 패키지를 추가해 해결한다.
for pkg in ("ultralytics", "djitellopy"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden


a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name="DroneApp",          # 결과 파일명 → DroneApp.exe
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,             # 검은 콘솔 창을 함께 띄워 로그(배터리, 오류 등)를 보여준다.
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
