"""
경로 헬퍼 — PyInstaller로 만든 exe 안에서도 파일을 제대로 찾게 해준다.

onefile(.exe 한 개) 실행 방식은, 실행 순간 exe 안의 내용물을 임시 폴더에 압축 해제한
뒤 그 폴더에서 프로그램을 돌린다. 그래서 코드가 "best.pt" 같은 상대경로로 파일을 찾으면
개발할 때(PyCharm)와 exe로 돌릴 때 위치가 달라져 파일을 못 찾는 문제가 생긴다.

- resource_path(): 모델(.pt), templates 등 "읽기 전용으로 exe에 넣은 부품"의 실제 위치.
- app_dir():      녹화 mp4처럼 "실행 중에 새로 쓰는 파일"을 저장할 폴더(exe 옆).
"""
import os
import sys


def resource_path(relative_path):
    """exe에 포함(번들)된 파일의 실제 경로를 돌려준다.

    - exe로 실행 중이면: PyInstaller가 압축을 푼 임시 폴더(sys._MEIPASS) 기준.
    - 그냥 python으로 실행 중이면: 이 프로젝트 폴더 기준.
    """
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative_path)


def app_dir():
    """실행 중에 새로 만드는 파일(녹화 mp4 등)을 저장할 기준 폴더.

    - 맥 .app 으로 실행 중이면: DroneApp.app 이 놓여 있는 폴더(사용자가 보는 위치).
      실행 파일 자체는 DroneApp.app/Contents/MacOS/ 안에 있는데, 번들 내부에 녹화를
      저장하면 사용자 눈에 보이지 않으므로 .app 이 있는 바깥 폴더에 저장한다.
    - 그 밖의 방식(터미널 실행 파일 등)으로 frozen 상태면: 실행 파일이 있는 폴더.
    - 그냥 python으로 실행 중이면: 현재 작업 폴더.
    """
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        # 맥 .app 번들이면 실행 파일 경로가 .../DroneApp.app/Contents/MacOS/DroneApp 이다.
        macos_marker = os.path.join("Contents", "MacOS")
        if exe_dir.endswith(macos_marker):
            # .../DroneApp.app/Contents/MacOS → .../  (DroneApp.app 이 있는 폴더)
            return os.path.dirname(os.path.dirname(os.path.dirname(exe_dir)))
        return exe_dir
    return os.path.abspath(".")


def model_path(name):
    """AI 모델(.pt) 파일 경로를 돌려준다.

    - 프로젝트 루트(개발 시) 또는 exe에 번들된 위치에 파일이 있으면 그 경로를 쓴다.
      (best.pt, yolov8n-pose-test4.pt 는 레포 루트에 함께 올라와 있다.)
    - 없으면 이름만 그대로 돌려줘서 ultralytics가 인터넷에서 자동 다운로드하도록 둔다
      (yolov8n.pt, yolo11n.pt 같은 공개 모델용).
    """
    bundled = resource_path(name)
    if os.path.exists(bundled):
        return bundled
    return name
