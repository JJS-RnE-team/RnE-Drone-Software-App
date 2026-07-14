import logging
import os
import threading
import time
import webbrowser

import cv2
from flask import Flask, Response, jsonify, render_template, send_file

from resource_path import resource_path, app_dir


def _setup_logging():
    """시작 과정을 콘솔 + 파일에 모두 남긴다 (진단용).

    .app 을 더블클릭하면 콘솔(터미널)이 안 보이므로, 앱 옆(app_dir)에 'droneapp_log.txt'
    파일을 만들어 거기에도 같은 로그를 남긴다. 문제가 나면 이 파일만 열어보면 어느 단계에서
    멈췄는지 알 수 있다.
    """
    log_path = os.path.join(app_dir(), "droneapp_log.txt")
    handlers = [logging.StreamHandler()]  # 콘솔(터미널 실행 시 보임)
    try:
        handlers.append(logging.FileHandler(log_path, mode="w", encoding="utf-8"))
    except Exception:
        pass  # 파일을 못 만들어도(권한 등) 콘솔 로그는 남긴다.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )
    return log_path


LOG_PATH = _setup_logging()
log = logging.getLogger(__name__)
log.info("로그 파일 위치: %s", LOG_PATH)

# ─────────────────────────────────────────────────────────────────────────────
# [알고리즘 교체 지점] 아래 import 한 줄만 바꾸면 드론 제어 알고리즘이 통째로 교체된다.
# 두 모듈의 DroneController 는 공개 인터페이스가 동일하므로 나머지 코드는 그대로 동작한다.
#
#   from drone_flight_test import DroneController        # ← 테스트용 (사람 추적, 지금 사용 중)
#   from drone_flight_algorithm import DroneController   # ← 실제 (농구 촬영 회전 제어)
#
# 최종 exe 검증이 끝나면 위 두 줄의 주석을 서로 바꿔주면 된다.
# ─────────────────────────────────────────────────────────────────────────────
from drone_flight_test import DroneController

# exe(onefile)로 실행될 때도 templates 폴더를 찾도록 절대경로를 지정한다.
app = Flask(__name__, template_folder=resource_path("templates"))

# 웹 서버 주소 (실행 시 브라우저를 여기로 자동으로 연다)
# macOS 는 5000번 포트를 시스템의 AirPlay 수신(AirPlay Receiver)이 이미 쓰고 있어
# 충돌이 나므로 5001번을 쓴다. (윈도우에서는 5000번을 썼음)
HOST = "0.0.0.0"
PORT = 5001

# 드론 제어 + AI 분석 컨트롤러 (백그라운드 스레드에서 동작)
controller = DroneController()


def gen_frames():
    """최신 분석 프레임을 JPEG로 인코딩해 MJPEG 스트림으로 내보낸다."""
    while True:
        frame = controller.get_latest_frame()
        if frame is None:
            # 아직 프레임이 없으면 잠깐 대기
            time.sleep(0.03)
            continue
        ok, buf = cv2.imencode(".jpg", frame)
        if not ok:
            continue
        jpg = buf.tobytes()
        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n")
        time.sleep(0.03)  # 약 30fps로 상한


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/video_feed")
def video_feed():
    return Response(gen_frames(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/api/status")
def api_status():
    return jsonify(controller.get_status())


@app.route("/api/takeoff", methods=["POST"])
def api_takeoff():
    controller.takeoff()
    return jsonify({"ok": True})


@app.route("/api/land", methods=["POST"])
def api_land():
    controller.land()
    return jsonify({"ok": True})


@app.route("/api/start_recording", methods=["POST"])
def api_start_recording():
    controller.start_recording()
    return jsonify({"ok": True})


@app.route("/api/stop_recording", methods=["POST"])
def api_stop_recording():
    controller.stop_recording()
    return jsonify({"ok": True})


@app.route("/api/download")
def api_download():
    path = controller.get_last_recording_path()
    if not path or not os.path.exists(path):
        return jsonify({"ok": False, "error": "녹화 파일이 없습니다."}), 404
    return send_file(path, as_attachment=True,
                     download_name=os.path.basename(path))


def open_browser():
    """서버가 뜬 뒤 기본 브라우저로 화면을 자동으로 연다."""
    url = f"http://127.0.0.1:{PORT}/"
    log.info("브라우저 자동 열기: %s", url)
    webbrowser.open(url)


if __name__ == "__main__":
    # 드론 연결 + 스트림 + 분석 루프 시작 (백그라운드 스레드에서 동작)
    log.info("controller.start() 호출 — 드론/모델 백그라운드 스레드 시작")
    controller.start()
    # 서버가 완전히 뜰 시간을 잠깐 준 뒤 브라우저를 자동으로 연다.
    threading.Timer(1.5, open_browser).start()
    # threaded=True: 영상 스트리밍과 API 요청을 동시에 처리
    # use_reloader=False: 리로더가 프로세스를 두 번 띄워 드론에 중복 연결되는 것을 방지
    log.info("Flask 서버 시작: bind=%s:%s (서버는 여기서 blocking으로 계속 돌아감)", HOST, PORT)
    app.run(host=HOST, port=PORT, threaded=True, use_reloader=False)
