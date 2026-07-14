from djitellopy import Tello
from ultralytics import YOLO
import cv2
import time
import numpy as np
import threading
import queue
import os
import logging
from datetime import datetime
from resource_path import model_path, app_dir

log = logging.getLogger(__name__)

# =============================================================================
# [테스트용 알고리즘] 사람(person) 인식 → 화면 중심 대비 좌우 오차 비례(P) 제어로 yaw 회전.
#
# 이 파일은 최종 exe를 먼저 "쉬운 알고리즘"으로 검증하기 위한 것이다.
# 인터페이스(공개 메서드/상태 dict)는 drone_flight_algorithm.py 의 DroneController 와
# 완전히 동일하므로, app.py 의 import 한 줄만 바꾸면 그대로 교체된다:
#
#     from drone_flight_test import DroneController        # ← 테스트 (사람 추적)
#     from drone_flight_algorithm import DroneController   # ← 실제 (농구 촬영)
#
# 알고리즘 자체(YOLO 사람 인식 + 비례 제어)는 원본 코드 그대로이며,
# 화면 표시(cv2.imshow) 분리 / 명령 큐(이착륙·녹화) / 상태 노출만 추가되었다.
# =============================================================================

# --- 인식/제어 상수 (원본 코드와 동일) ---
PERSON_CLASS_ID = 0
YOLO_W, YOLO_H = 320, 240
YOLO_EVERY_N_FRAMES = 3         # N프레임마다 한 번 YOLO
CENTER_TOL_RATIO = 0.06         # 중앙 ±6% 안이면 회전 안 함
Kp = 60                         # 사람 중심이 100% 치우치면 yaw 60 정도로 회전
MAX_YAW = 80                    # Tello rc yaw 속도 최대 절대값

# --- 녹화 설정 (알고리즘 버전과 동일) ---
RECORDINGS_DIR = os.path.join(app_dir(), "recordings")   # mp4 저장 폴더 (exe 옆)
OUTPUT_FPS = 20                 # 저장 mp4의 재생 프레임레이트


# --- 헬퍼 함수 (원본 코드 그대로) ---
def get_main_person_center_x(result):
    """YOLO 결과에서 person(class 0)들 중 가장 큰 사람의 x 중심(축소 프레임 기준). 없으면 None."""
    boxes = result.boxes
    if boxes is None or len(boxes) == 0:
        return None

    xyxy = boxes.xyxy.cpu().numpy()
    classes = boxes.cls.cpu().numpy()

    main_center_x = None
    main_area = 0
    for box, cls_id in zip(xyxy, classes):
        if int(cls_id) != PERSON_CLASS_ID:
            continue
        x1, y1, x2, y2 = box
        area = (x2 - x1) * (y2 - y1)
        center_x = (x1 + x2) / 2
        if area > main_area:
            main_area = area
            main_center_x = center_x
    return main_center_x


# --- 드론 제어 + AI 분석 컨트롤러 ---
# drone_flight_algorithm.DroneController 와 동일한 공개 인터페이스를 제공한다:
#   start() / stop() / is_running()
#   takeoff() / land() / start_recording() / stop_recording()
#   get_latest_frame() / get_status() / get_last_recording_path()
class DroneController:
    def __init__(self):
        self._thread = None
        self._stop_event = threading.Event()
        self._frame_lock = threading.Lock()
        self._latest_frame = None
        self.yaw_speed_history = []

        # 명령 큐 (Flask 요청 스레드 -> 루프 스레드)
        self._command_queue = queue.Queue()

        # 상태 (get_status로 노출, 락으로 보호)
        self._status_lock = threading.Lock()
        self._connected = False
        self._battery = None
        self._flying = False
        self._recording = False
        self._target = "없음"
        self._last_recording_path = None

    # --- 프레임 버퍼 ---
    def _set_latest_frame(self, frame):
        with self._frame_lock:
            self._latest_frame = frame

    def get_latest_frame(self):
        with self._frame_lock:
            if self._latest_frame is None:
                return None
            return self._latest_frame.copy()

    # --- 스레드 수명 ---
    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join()

    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    # --- 외부 명령 (Flask에서 호출) ---
    def takeoff(self):
        self._command_queue.put("takeoff")

    def land(self):
        self._command_queue.put("land")

    def start_recording(self):
        # 비행 중일 때만 실제로 시작된다(루프 스레드에서 _flying 확인).
        self._command_queue.put("start_record")

    def stop_recording(self):
        self._command_queue.put("stop_record")

    # --- 상태 조회 ---
    def get_status(self):
        with self._status_lock:
            return {
                "connected": self._connected,
                "battery": self._battery,
                "flying": self._flying,
                "recording": self._recording,
                "target": self._target,
                "last_recording": (os.path.basename(self._last_recording_path)
                                   if self._last_recording_path else None),
            }

    def get_last_recording_path(self):
        with self._status_lock:
            return self._last_recording_path

    # --- 메인 루프 (백그라운드 스레드에서 실행) ---
    def _run(self):
        # --- 시작 단계 (진단 로그 포함) ----------------------------------------
        # 지금까지는 이 구간에서 예외가 나면(모델 로딩 실패·드론 연결 실패 등) 데몬 스레드가
        # '조용히' 죽어버려서, .app 에서는 원인이 전혀 안 보였다(UI만 뜨고 영상/연결 안 됨).
        # 그래서 각 단계에 로그를 남기고, 예외를 잡아 전체 traceback을 기록한 뒤 종료한다.
        try:
            # 디텍션 모델. 요청한 이름의 .pt 가 번들/폴더에 있으면 그것을 쓰고,
            # 없으면 ultralytics가 '인터넷에서 자동 다운로드'를 시도한다.
            # → 드론(TELLO) wifi 는 인터넷이 없으므로, 파일이 번들에 없으면 여기서 멈추거나 실패한다.
            requested = "yolov8n.pt"
            resolved = model_path(requested)
            log.info("① YOLO 모델 로딩 시작: 요청=%s → 실제경로=%s "
                     "(경로가 요청이름 그대로면 = 번들에 없어서 인터넷 다운로드 시도 중이라는 뜻)",
                     requested, resolved)
            model = YOLO(resolved)
            log.info("① YOLO 모델 로딩 완료")

            tello = Tello()
            log.info("② tello.connect() 시작 — 로컬 네트워크(UDP)로 드론에 연결 시도")
            tello.connect()
            battery = tello.get_battery()
            log.info("② 드론 연결 완료 · 배터리=%s%%", battery)
            with self._status_lock:
                self._connected = True
                self._battery = battery

            log.info("③ tello.streamon() — 영상 스트림 시작")
            tello.streamon()
            log.info("③ get_frame_read() 호출 — 영상 디코더(PyAV/ffmpeg)로 스트림 여는 중 "
                     "(여기서 오래 멈추면: av가 번들에 없거나, 영상 UDP(11111)가 안 들어오는 것)")
            frame_read = tello.get_frame_read()
            log.info("③ 스트림 준비 완료 — 프레임 수신/분석 루프 진입")
        except Exception:
            log.exception("‼️ 시작 단계에서 예외 발생 — 백그라운드 스레드를 종료한다. "
                          "이것이 'UI는 뜨지만 영상 안 나오고 드론 연결 안 됨'의 직접 원인이다.")
            return

        # 사람 중심 정보 (프레임 간 유지)
        last_person_center_ratio = None
        frame_count = 0

        # 녹화/폴링 상태 (루프 스레드 전용)
        video_writer = None
        record_path = None
        last_battery_poll = 0.0

        yaw_speed_history = self.yaw_speed_history

        try:
            while not self._stop_event.is_set():
                # --- 명령 처리 (takeoff / land / start_record / stop_record) ---
                try:
                    while True:
                        cmd = self._command_queue.get_nowait()
                        if cmd == "takeoff":
                            if not self._flying:
                                tello.takeoff()
                                time.sleep(3)
                                with self._status_lock:
                                    self._flying = True
                        elif cmd == "land":
                            if self._flying:
                                try:
                                    tello.send_rc_control(0, 0, 0, 0)
                                    tello.land()
                                except:
                                    pass
                                # 착륙 시 녹화 중이면 자동으로 마무리 (지상에서는 녹화하지 않음)
                                if video_writer is not None:
                                    video_writer.release()
                                    video_writer = None
                                with self._status_lock:
                                    self._flying = False
                                    if self._recording:
                                        self._recording = False
                                        if record_path is not None:
                                            self._last_recording_path = record_path
                        elif cmd == "start_record":
                            # 이착륙과 분리된 녹화 시작 (비행 중일 때만)
                            if self._flying and not self._recording:
                                os.makedirs(RECORDINGS_DIR, exist_ok=True)
                                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                record_path = os.path.join(RECORDINGS_DIR, f"flight_{stamp}.mp4")
                                # 실제 writer는 첫 프레임에서 크기를 알고 나서 연다
                                video_writer = None
                                with self._status_lock:
                                    self._recording = True
                        elif cmd == "stop_record":
                            if self._recording:
                                if video_writer is not None:
                                    video_writer.release()
                                    video_writer = None
                                with self._status_lock:
                                    self._recording = False
                                    if record_path is not None:
                                        self._last_recording_path = record_path
                except queue.Empty:
                    pass

                # --- 배터리 주기적 폴링 (~2초마다) ---
                now = time.time()
                if now - last_battery_poll > 2.0:
                    try:
                        b = tello.get_battery()
                        with self._status_lock:
                            self._battery = b
                    except:
                        pass
                    last_battery_poll = now

                frame = frame_read.frame
                if frame is None:
                    continue
                # djitellopy 프레임은 RGB이므로 OpenCV(BGR)에 맞게 변환
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                h, w = frame.shape[:2]
                frame_center_x = w / 2

                # 원본 프레임은 건드리지 않고 복사본에 그린 뒤 송출
                annotated_frame = frame.copy()

                # 3프레임마다 한 번씩 YOLO. 아니면 이전 결과 재사용
                person_center_ratio = last_person_center_ratio

                if frame_count % YOLO_EVERY_N_FRAMES == 0:
                    small = cv2.resize(frame, (YOLO_W, YOLO_H))
                    try:
                        result = model(small, verbose=False)[0]
                        person_center_x_small = get_main_person_center_x(result)

                        if person_center_x_small is not None:
                            center_ratio = (person_center_x_small - YOLO_W / 2) / (YOLO_W / 2)
                            person_center_ratio = center_ratio
                            last_person_center_ratio = center_ratio
                        else:
                            person_center_ratio = None

                        # 디버깅용: 축소 프레임 위 박스를 우측 상단에 미니맵처럼 표시
                        annotated_small = result.plot()
                        sh, sw = annotated_small.shape[:2]
                        annotated_frame[0:sh, w - sw:w] = annotated_small
                    except Exception as e:
                        print("YOLO 추론 중 오류:", e)

                # --- 사람 위치에 따라 yaw 속도 결정 ---
                yaw_speed = 0
                current_target = "없음"

                if person_center_ratio is not None:
                    current_target = "사람"
                    # 화면 중앙선
                    cv2.line(annotated_frame, (int(frame_center_x), 0),
                             (int(frame_center_x), h), (0, 255, 0), 1)
                    # 사람 x 위치 표시
                    px = int((person_center_ratio * (w / 2)) + frame_center_x)
                    cv2.circle(annotated_frame, (px, h // 2), 8, (0, 0, 255), -1)

                    if abs(person_center_ratio) > CENTER_TOL_RATIO:
                        yaw_speed = int(person_center_ratio * Kp)
                        yaw_speed = int(np.clip(yaw_speed, -MAX_YAW, MAX_YAW))
                        cv2.putText(annotated_frame, f"TRACKING yaw={yaw_speed}", (10, 40),
                                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
                    else:
                        cv2.putText(annotated_frame, "CENTERED", (10, 40),
                                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
                else:
                    cv2.putText(annotated_frame, "NO PERSON", (10, 40),
                                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)

                # 현재 추적 대상 상태 기록
                with self._status_lock:
                    self._target = current_target

                # --- 명령 전송 및 기록 ---
                yaw_speed_history.append(yaw_speed)
                # 비행 중일 때만 yaw 명령 전송. 착륙 상태면 전송하지 않는다.
                if self._flying:
                    try:
                        tello.send_rc_control(0, 0, 0, yaw_speed)
                    except Exception as e:
                        print("send_rc_control 오류:", e)

                # [화면 표시 분리] cv2.imshow 대신 최신 프레임을 버퍼에 저장 (Flask가 읽어감)
                self._set_latest_frame(annotated_frame)

                # [녹화] 녹화 중이면 annotated 프레임을 mp4로 기록
                if self._recording and record_path is not None:
                    if video_writer is None:
                        fh, fw = annotated_frame.shape[:2]
                        video_writer = cv2.VideoWriter(
                            record_path, cv2.VideoWriter_fourcc(*"mp4v"), OUTPUT_FPS, (fw, fh))
                    video_writer.write(annotated_frame)

                frame_count += 1

        except KeyboardInterrupt:
            print("\n실행 중지")
        finally:
            # 종료 시 녹화 마무리
            if video_writer is not None:
                video_writer.release()
                with self._status_lock:
                    self._recording = False
                    if record_path is not None:
                        self._last_recording_path = record_path

            try:
                tello.send_rc_control(0, 0, 0, 0)
                tello.land()
                time.sleep(1.5)
            except:
                pass
            try:
                tello.streamoff()
            except:
                pass
            tello.end()
            with self._status_lock:
                self._connected = False
                self._flying = False


# --- 단독 실행 ---
# 백그라운드 컨트롤러를 띄우고, show_preview면 로컬 창으로 미리보기를 표시한다.
# Flask 등으로 감쌀 때는 이 블록 대신 app.py에서 DroneController를 사용한다.
# 이륙/착륙/녹화는 명령으로 수행되므로, 단독 실행 시에는 키보드로 트리거한다:
#   t = 이륙, l = 착륙, r = 촬영 시작, s = 촬영 중지, q = 종료
def main(show_preview=True):
    controller = DroneController()
    controller.start()
    try:
        if show_preview:
            while controller.is_running():
                frame = controller.get_latest_frame()
                if frame is not None:
                    cv2.imshow("Tello + Fast YOLO Person Tracking", frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('t'):
                    controller.takeoff()
                elif key == ord('l'):
                    controller.land()
                elif key == ord('r'):
                    controller.start_recording()
                elif key == ord('s'):
                    controller.stop_recording()
        else:
            while controller.is_running():
                time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n실행 중지")
    finally:
        controller.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
