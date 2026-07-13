# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller 빌드 설정 파일 (macOS / 맥북 전용).
# 맥북 터미널에서 다음 한 줄로 앱을 만든다:
#
#     pyinstaller drone.spec
#
# 결과물: dist/DroneApp.app  (맥용 앱 하나. 더블클릭하면 브라우저가 열린다.)
#         dist/DroneApp       (터미널에서 실행하면 로그가 보이는 실행 파일. .app 안에도 같이 들어간다.)
# 소스 파일(.py, *.pt, templates/)은 지워지지 않는다. 빌드 결과만 build/, dist/ 에 새로 생긴다.
#
# ※ 윈도우 exe는 윈도우에서만, 맥 .app 은 맥에서만 구울 수 있다. 이 파일은 "맥에서" 굽는 용도.

import glob
from PyInstaller.utils.hooks import collect_all

# --- 앱 안에 함께 넣을 파일들 -------------------------------------------------
# 프로젝트 루트의 모든 .pt 모델을 앱 안 루트에 그대로 넣는다.
# (best.pt, yolov8n-pose-test4.pt 등 루트에 있는 .pt 는 전부 포함)
model_datas = [(p, ".") for p in glob.glob("*.pt")]

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
    name="DroneApp",          # 실행 파일명 → DroneApp (맥에는 .exe 확장자가 없다)
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                # 맥에서는 UPX 압축이 실행 파일/서명을 깨뜨리는 경우가 많아 끈다.
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,             # 터미널에서 실행하면 로그(배터리, 오류 등)가 보인다.
    disable_windowed_traceback=False,
    argv_emulation=False,
    # target_arch=None → 지금 맥북의 CPU에 맞춰 빌드한다.
    #   • 애플 실리콘(M1~M4) 맥에서 구우면 애플 실리콘용,
    #   • 인텔 맥에서 구우면 인텔용 앱이 나온다.
    #   두 CPU 모두에서 도는 앱을 원하면 "universal2" 로 바꾼다(단, 설치된 파이썬도 universal2 여야 함).
    target_arch=None,
    codesign_identity=None,   # 애플 개발자 서명 없이 만든다(개인·팀 내부 배포용).
    entitlements_file=None,
)

# --- 맥용 .app 번들로 감싸기 ---------------------------------------------------
# 위 EXE 는 터미널에서 돌리는 실행 파일이고, 아래 BUNDLE 이 이를 더블클릭 가능한
# DroneApp.app 으로 포장한다. (윈도우의 DroneApp.exe 에 해당하는 것)
app = BUNDLE(
    exe,
    name="DroneApp.app",
    icon=None,                        # 아이콘(.icns)이 있으면 여기에 경로를 넣는다.
    bundle_identifier="com.rne.droneapp",
    info_plist={
        "CFBundleName": "DroneApp",
        "CFBundleDisplayName": "Drone App",
        "CFBundleShortVersionString": "1.0.0",
        "NSHighResolutionCapable": True,
        # 드론 영상/명령은 로컬 네트워크(드론 wifi)로 오가므로, macOS 가 첫 실행 때
        # "로컬 네트워크 접근 허용?" 을 물어볼 때 보여줄 설명 문구.
        "NSLocalNetworkUsageDescription":
            "드론과 통신하고 영상을 받아오기 위해 로컬 네트워크를 사용합니다.",
    },
)
