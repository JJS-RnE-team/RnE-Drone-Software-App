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

    - exe로 실행 중이면: exe 파일이 있는 폴더 (임시 폴더는 종료 시 삭제되므로 여기 쓰면 안 됨).
    - 그냥 python으로 실행 중이면: 현재 작업 폴더.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(".")


def model_path(name):
    """AI 모델(.pt) 파일 경로를 돌려준다.

    - models/ 폴더(개발 시) 또는 exe에 번들된 models/ 안에 파일이 있으면 그 경로를 쓴다.
    - 없으면 이름만 그대로 돌려줘서 ultralytics가 인터넷에서 자동 다운로드하도록 둔다
      (yolov8n.pt, yolo11n.pt 같은 공개 모델용).
    """
    bundled = resource_path(os.path.join("models", name))
    if os.path.exists(bundled):
        return bundled
    return name
