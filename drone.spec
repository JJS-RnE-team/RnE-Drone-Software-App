# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller 빌드 설정 파일 (macOS / 맥북 전용, onedir 방식).
# 맥북 터미널에서 다음 한 줄로 앱을 만든다:
#
#     pyinstaller drone.spec
#
# 결과물: dist/DroneApp.app  (맥용 앱. 더블클릭하면 브라우저가 열린다.)
#
# ★ onedir(폴더) 방식이란?
#   예전에는 onefile(파일 하나)로 구웠는데, 그러면 실행할 때마다 앱 안의 수백 MB
#   (torch, ultralytics 등)를 임시폴더에 "압축 해제"하느라 시작이 몇 분씩 걸렸다.
#   onedir 는 그 내용물을 .app 안에 "미리 풀린 상태"로 넣어두므로, 실행할 때 압축을
#   풀 필요가 없어 시작이 훨씬 빠르다. (맥에선 .app 이 원래 폴더라 사용자 눈엔 여전히
#   아이콘 하나로 보인다 → 배포·사용에 불편 없음.)
#
# 소스 파일(.py, *.pt, templates/)은 지워지지 않는다. 빌드 결과만 build/, dist/ 에 새로 생긴다.
# ※ 윈도우 exe는 윈도우에서만, 맥 .app 은 맥에서만 구울 수 있다. 이 파일은 "맥에서" 굽는 용도.

import glob
import os
from PyInstaller.utils.hooks import collect_all

# --- 앱 아이콘 -----------------------------------------------------------------
# 레포 루트에 icon.icns 파일이 있으면 그것을 앱 아이콘으로 쓰고,
# 없으면 None(기본 아이콘)으로 둔다. → 아이콘 파일이 없어도 빌드는 정상 진행된다.
ICON_FILE = "icon.icns" if os.path.exists("icon.icns") else None

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
# av(PyAV): djitellopy 가 드론 영상 스트림(UDP)을 여는 데 쓰는 백엔드로, 내부에 ffmpeg
#   라이브러리를 품고 있다. 이걸 번들에 안 넣으면 .app 에서 get_frame_read() 가 조용히
#   멈춰(영상 안 나오고 무한 로딩) 버린다. 그래서 반드시 함께 수집한다.
# 패키징 오류(모듈/파일 누락)가 나면 대개 이 목록에 패키지를 추가해 해결한다.
for pkg in ("ultralytics", "djitellopy", "av"):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    except Exception as e:
        # 설치 안 된 선택적 패키지면 건너뛴다(빌드를 멈추지 않게).
        print("[drone.spec] collect_all('%s') 건너뜀: %s" % (pkg, e))
        continue
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

# onedir 방식: EXE 에는 실행 파일 알맹이만 넣고(exclude_binaries=True),
# 나머지 라이브러리·데이터(a.binaries, a.datas)는 아래 COLLECT 가 폴더로 모은다.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,    # onedir 의 핵심: 라이브러리를 exe 안에 넣지 않고 폴더에 둔다.
    name="DroneApp",          # 실행 파일명 → DroneApp (맥에는 .exe 확장자가 없다)
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                # 맥에서는 UPX 압축이 실행 파일/서명을 깨뜨리는 경우가 많아 끈다.
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

# 실행 파일 + 라이브러리 + 데이터(.pt, templates)를 하나의 폴더로 모은다.
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="DroneApp",
)

# --- 맥용 .app 번들로 감싸기 ---------------------------------------------------
# 위 COLLECT 결과(폴더)를 더블클릭 가능한 DroneApp.app 으로 포장한다.
app = BUNDLE(
    coll,
    name="DroneApp.app",
    icon=ICON_FILE,                   # icon.icns 가 있으면 그것을, 없으면 기본 아이콘.
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
