import os
import time

import cv2
from flask import Flask, Response, jsonify, render_template, send_file

from drone_flight_algorithm import DroneController

app = Flask(__name__)

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


@app.route("/api/download")
def api_download():
    path = controller.get_last_recording_path()
    if not path or not os.path.exists(path):
        return jsonify({"ok": False, "error": "녹화 파일이 없습니다."}), 404
    return send_file(path, as_attachment=True,
                     download_name=os.path.basename(path))


if __name__ == "__main__":
    # 드론 연결 + 스트림 + 분석 루프 시작
    controller.start()
    # threaded=True: 영상 스트리밍과 API 요청을 동시에 처리
    # use_reloader=False: 리로더가 프로세스를 두 번 띄워 드론에 중복 연결되는 것을 방지
    app.run(host="0.0.0.0", port=5000, threaded=True, use_reloader=False)
