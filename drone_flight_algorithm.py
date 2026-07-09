from djitellopy import Tello
from ultralytics import YOLO
import cv2
import time
import numpy as np
import math
import threading
import queue
import os
from datetime import datetime
from resource_path import model_path, app_dir

# --- 상수 설정 ---
BALL_CLASS_ID = 32
PERSON_CLASS_ID = 0
YOLO_W, YOLO_H = 320, 256
BALL_CONF_TH = 0.5
HOLDER_TIMEOUT_SEC = 20
CENTER_TOL_RATIO = 0
MAX_YAW = 100

# --- 제어 상수 (각도용과 픽셀용 분리) ---
Kp_angle = 0.8  # 호모그래피 각도 오차 기반 (단위: degree)
Kp_pixel = 60.0  # 화면상 픽셀 오차 기반 (단위: ratio -1.0~1.0)

# --- 녹화 설정 ---
RECORDINGS_DIR = os.path.join(app_dir(), "recordings")  # mp4 저장 폴더 (exe 옆)
OUTPUT_FPS = 20  # 저장 mp4의 재생 프레임레이트 (실측 루프 속도에 맞춰 조정 가능)

# 가상 농구장 실제 좌표 매핑
COURT_POINTS = {
    0: (-14, 9.95), 1: (-14, 5.05), 2: (-8.2, 5.05), 3: (-8.2, 9.95),
    4: (-11.01, 14.1), 5: (-11.01, 0.9), 6: (-5.675, 7.5),
    7: (0, 15), 8: (0, 9.3),  # 7, 8번은 중앙점이므로 좌우 판정에서 제외
    9: (5.675, 7.5), 10: (11.01, 0.9), 11: (11.01, 14.1),
    12: (8.2, 9.95), 15: (8.2, 5.05), 13: (14, 9.95), 14: (14, 5.05)
}


# --- 헬퍼 함수 ---
def clip_int(v, lo, hi):
    return int(np.clip(v, lo, hi))


def box_center(box_xyxy):
    x1, y1, x2, y2 = box_xyxy
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def transform_point(pt_screen, H_matrix):
    pt_h = np.array([pt_screen[0], pt_screen[1], 1.0])
    transformed = H_matrix @ pt_h
    if transformed[2] == 0: return np.array([0.0, 0.0])
    return transformed[:2] / transformed[2]


def get_main_ball_box(result):
    boxes = result.boxes
    if boxes is None or len(boxes) == 0: return None, None
    xyxy = boxes.xyxy.cpu().numpy()
    classes = boxes.cls.cpu().numpy()
    confs = boxes.conf.cpu().numpy() if boxes.conf is not None else None
    best_box, best_conf, best_area = None, None, 0.0
    for i, (box, cls_id) in enumerate(zip(xyxy, classes)):
        if int(cls_id) != BALL_CLASS_ID: continue
        x1, y1, x2, y2 = box
        area = float((x2 - x1) * (y2 - y1))
        if area > best_area:
            best_area, best_box, best_conf = area, box, float(confs[i]) if confs is not None else None
    return best_box, best_conf


def get_person_tracks(result, conf_th=0.6):
    out = []
    boxes = result.boxes
    if boxes is None or len(boxes) == 0: return out
    xyxy = boxes.xyxy.cpu().numpy()
    classes = boxes.cls.cpu().numpy()
    confs = boxes.conf.cpu().numpy() if boxes.conf is not None else None
    tids = boxes.id.cpu().numpy().astype(int) if getattr(boxes, "id", None) is not None else None
    for i, (box, cls_id) in enumerate(zip(xyxy, classes)):
        if int(cls_id) != PERSON_CLASS_ID: continue
        c = float(confs[i]) if confs is not None else 0.0
        if c < conf_th: continue
        tid = int(tids[i]) if tids is not None else None
        out.append((box, c, tid))
    return out


def find_person_box_by_id(person_tracks, target_id):
    if target_id is None: return None
    for (box, conf, tid) in person_tracks:
        if tid is not None and int(tid) == int(target_id): return box
    return None


def draw_minimap(frame, line1_m, line3_m, line2_m):
    h, w = frame.shape[:2]
    mw, mh = 280, 150
    margin = 20
    start_x, start_y = w - mw - margin, h - mh - margin
    overlay = frame.copy()
    cv2.rectangle(overlay, (start_x, start_y), (start_x + mw, start_y + mh), (40, 40, 40), -1)
    cv2.rectangle(overlay, (start_x, start_y), (start_x + mw, start_y + mh), (255, 255, 255), 2)
    cv2.line(overlay, (start_x + mw // 2, start_y), (start_x + mw // 2, start_y + mh), (255, 255, 255), 2)
    cv2.circle(overlay, (start_x + mw // 2, start_y + mh // 2), 18, (255, 255, 255), 2)
    cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)

    def m_to_px(mx, my):
        px = int((mx + 14) * 10)
        py = int((15 - my) * 10)
        return start_x + px, start_y + py

    origin_px = m_to_px(0.0, 0.0)

    def draw_line(vector_m, color, thickness=2):
        if vector_m is not None:
            norm = np.linalg.norm(vector_m)
            if norm > 1e-6:
                pt = vector_m / norm * 15.0
                pt_px = m_to_px(pt[0], pt[1])
                cv2.line(frame, origin_px, pt_px, color, thickness)

    draw_line(line1_m, (0, 255, 0), 2)
    draw_line(line3_m, (0, 255, 255), 2)
    draw_line(line2_m, (0, 0, 255), 4)
    cv2.circle(frame, origin_px, 5, (255, 0, 0), -1)


# --- 드론 제어 + AI 분석 컨트롤러 ---
# 기존 main() 루프의 드론 제어 / YOLO 인식 / 호모그래피·Line 알고리즘(yaw 계산)은 그대로 유지한다.
# 화면 표시(cv2.imshow)는 분리되어, 매 프레임의 분석 결과(바운딩 박스·Line 등이 그려진 프레임)를
# 내부 버퍼에 저장하고 외부(Flask)가 get_latest_frame()으로 읽어간다.
#
# 웹 UI 연동을 위해 다음이 추가되었다 (알고리즘 자체는 불변, 제어 흐름/상태 노출만 추가):
#   - 명령 큐: takeoff() / land() / start_recording() / stop_recording() 를 Flask 요청
#     스레드에서 호출하면 루프 스레드가 실행한다.
#     (djitellopy Tello 명령을 한 스레드로 일원화해 충돌 방지)
#   - 자동 이륙 제거: start()는 연결/스트림/분석 루프만 돌리고, 이륙은 takeoff() 명령으로 수행.
#   - 녹화 분리: 이착륙과 별개로 start_recording()/stop_recording() 명령으로 mp4 녹화를
#     시작/중지한다. 녹화는 비행 중일 때만 시작할 수 있고, 착륙하면 자동으로 마무리된다.
#   - 상태 노출: get_status() 로 배터리/연결/비행/녹화/현재 타겟을 제공한다.
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
        # 외부에서 안전하게 읽어가도록 최신 프레임을 락으로 보호하며 저장
        with self._frame_lock:
            self._latest_frame = frame

    def get_latest_frame(self):
        # 최신 분석 결과 프레임의 복사본 반환 (없으면 None)
        with self._frame_lock:
            if self._latest_frame is None:
                return None
            return self._latest_frame.copy()

    # --- 스레드 수명 ---
    def start(self):
        # 이미 실행 중이면 무시
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        # 루프에 종료 신호를 보내고 스레드가 정리(착륙/녹화 마무리/통계)를 마칠 때까지 대기
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
        model_person = YOLO(model_path("yolo11n.pt"))
        model_ball = YOLO(model_path("best.pt"))
        model_points = YOLO(model_path("yolov8n-pose-test4.pt"))

        tello = Tello()
        tello.connect()
        battery = tello.get_battery()
        print("배터리:", battery)
        with self._status_lock:
            self._connected = True
            self._battery = battery

        tello.streamon()
        frame_read = tello.get_frame_read()

        holder_track_id, last_holder_box_small, last_holder_update_t = None, None, 0.0
        yaw_speed_history = self.yaw_speed_history

        # 녹화/폴링 상태 (루프 스레드 전용)
        video_writer = None
        record_path = None
        last_battery_poll = 0.0

        try:
            while not self._stop_event.is_set():
                # --- 명령 처리 (takeoff / land) ---
                try:
                    while True:
                        cmd = self._command_queue.get_nowait()
                        if cmd == "takeoff":
                            if not self._flying:
                                tello.takeoff()
                                time.sleep(1)
                                tello.move_up(250)
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

                # --- 배터리 주기적 폴링 (매 프레임 호출은 부담이라 ~2초마다) ---
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
                if frame is None: continue
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                orig_h, orig_w = frame.shape[:2]
                sx, sy = orig_w / YOLO_W, orig_h / YOLO_H
                small = cv2.resize(frame, (YOLO_W, YOLO_H))

                # 1. 인식 로직
                try:
                    res_p = \
                    model_person.track(source=small, persist=True, verbose=False, conf=0.25, imgsz=(YOLO_H, YOLO_W))[0]
                    person_tracks = get_person_tracks(res_p)
                except:
                    person_tracks = []

                try:
                    res_b = model_ball(small, verbose=False)[0]
                    ball_box_small, ball_conf = get_main_ball_box(res_b)
                except:
                    ball_box_small, ball_conf = None, None

                # 2. 타겟 결정 (기본 픽셀 데이터 준비)
                displayTargetCord = None
                target_ratio = None
                current_target = "없음"
                if ball_box_small is not None and ball_conf >= BALL_CONF_TH:
                    displayTargetCord = box_center(ball_box_small)
                    target_ratio = (displayTargetCord[0] - YOLO_W / 2.0) / (YOLO_W / 2.0)
                    bx1, by1, bx2, by2 = ball_box_small
                    cv2.rectangle(frame, (int(bx1 * sx), int(by1 * sy)), (int(bx2 * sx), int(by2 * sy)), (0, 0, 255), 2)
                    current_target = "농구공"
                else:
                    if holder_track_id is not None:
                        curr_holder = find_person_box_by_id(person_tracks, holder_track_id)
                        if curr_holder is not None: last_holder_box_small = curr_holder
                    if last_holder_box_small is not None and (time.time() - last_holder_update_t) <= HOLDER_TIMEOUT_SEC:
                        displayTargetCord = box_center(last_holder_box_small)
                        target_ratio = (displayTargetCord[0] - YOLO_W / 2.0) / (YOLO_W / 2.0)
                        current_target = "Holder"

                # 현재 추적 대상 상태 기록 (알고리즘에는 영향 없음)
                with self._status_lock:
                    self._target = current_target

                # 3. 제어 계산 및 논리 검증 필터
                yaw_speed = 0
                current_line1_m, current_line2_m, current_line3_m = None, None, None
                use_homography = False

                try:
                    res_pts = model_points(small, verbose=False)[0]
                    if res_pts is not None and len(res_pts.keypoints.xy) > 0:
                        kpts, confs = res_pts.keypoints.xy[0].cpu().numpy(), res_pts.keypoints.conf[0].cpu().numpy()
                        src_pts, dst_pts = [], []
                        L_count, R_count = 0, 0

                        for idx, pt in enumerate(kpts):
                            if idx in COURT_POINTS and confs[idx] > 0.5 and pt[0] > 0:
                                src_pts.append(pt);
                                dst_pts.append(COURT_POINTS[idx])
                                px, py = int(pt[0] * sx), int(pt[1] * sy)
                                cv2.circle(frame, (px, py), 5, (0, 255, 255), -1)
                                cv2.putText(frame, str(idx), (px + 7, py - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255),
                                            1)
                                if 0 <= idx <= 6:
                                    L_count += 1
                                elif 9 <= idx <= 16:
                                    R_count += 1

                        if len(src_pts) >= 4:
                            H, _ = cv2.findHomography(np.array(src_pts, dtype=np.float32),
                                                      np.array(dst_pts, dtype=np.float32), cv2.RANSAC, 5.0)
                            if H is not None and displayTargetCord is not None:
                                ball_m = transform_point(displayTargetCord, H)

                                # [논리 모순 검증] 다수결 원칙
                                is_contradict = False
                                if L_count > R_count and ball_m[0] > 0:
                                    is_contradict = True
                                elif R_count > L_count and ball_m[0] < 0:
                                    is_contradict = True

                                if not is_contradict:
                                    # 정상 상황: 호모그래피 기반 각도 제어 수행
                                    current_line1_m = transform_point((YOLO_W / 2.0, YOLO_H / 2.0), H)
                                    phi_1 = math.atan2(current_line1_m[1], current_line1_m[0])

                                    current_line3_m = ball_m
                                    bx, by = ball_m[0], ball_m[1]
                                    theta_line3 = math.pi / 2.0 if abs(bx) < 1e-6 and abs(by) < 1e-6 else math.atan(
                                        abs(by) / abs(bx))

                                    # --- [수정] 정규화 범위 조정: arctan(3/14) ---
                                    theta_min = math.atan(1.5 / 14.0)
                                    theta_line2 = (theta_line3 / (math.pi / 2.0)) * (
                                                (math.pi / 2.0) - theta_min) + theta_min

                                    phi_2 = theta_line2 if bx >= 0 else math.pi - theta_line2
                                    current_line2_m = np.array([math.cos(phi_2), math.sin(phi_2)])

                                    yaw_error_deg = math.degrees(phi_1 - phi_2)
                                    yaw_speed = clip_int(yaw_error_deg * Kp_angle, -MAX_YAW, MAX_YAW)
                                    use_homography = True
                                else:
                                    print("논리 모순 감지: 호모그래피 중단 및 픽셀 기반 객체 추적 수행")
                except:
                    pass

                # 모순이 발생했거나 점이 부족해 호모그래피를 못 쓴 경우 -> 픽셀 기반 추적
                if not use_homography and target_ratio is not None:
                    yaw_speed = clip_int(target_ratio * Kp_pixel, -MAX_YAW, MAX_YAW)

                # 4. 명령 전송 및 데이터 기록
                yaw_speed_history.append(yaw_speed)
                # [제어 흐름] 비행 중일 때만 드론에 yaw 명령 전송. 착륙 상태면 전송하지 않는다.
                if self._flying:
                    tello.send_rc_control(0, 0, 0, yaw_speed)

                draw_minimap(frame, current_line1_m, current_line3_m, current_line2_m)

                # [화면 표시 분리] cv2.imshow 대신 최신 프레임을 버퍼에 저장 (Flask가 읽어감)
                self._set_latest_frame(frame)

                # [녹화] 비행(=녹화) 중이면 annotated 프레임을 mp4로 기록
                if self._recording and record_path is not None:
                    if video_writer is None:
                        h, w = frame.shape[:2]
                        video_writer = cv2.VideoWriter(
                            record_path, cv2.VideoWriter_fourcc(*"mp4v"), OUTPUT_FPS, (w, h))
                    video_writer.write(frame)

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

            # 통계 출력 (평균, 분산, 표준편차)
            print("\n" + "=" * 45)
            if yaw_speed_history:
                yaw_array = np.array(yaw_speed_history)
                print(f"최종 실험 Yaw Speed 통계 결과")
                print(f"사용한 제어 상수: Kp_angle={Kp_angle}, Kp_pixel={Kp_pixel}")
                print(f"측정 횟수: {len(yaw_array)}")
                print(f"평균(Mean): {np.mean(yaw_array):.4f}")
                print(f"분산(Variance): {np.var(yaw_array):.4f}")
                print(f"표준편차(Std Dev): {np.std(yaw_array):.4f}")
            print("=" * 45)

            try:
                tello.send_rc_control(0, 0, 0, 0)
                tello.land()
                time.sleep(1.5)  # 착륙 명령 전달 대기
            except:
                pass
            tello.end()
            with self._status_lock:
                self._connected = False
                self._flying = False


# --- 단독 실행 ---
# 백그라운드 컨트롤러를 띄우고, 옵션(show_preview)에 따라 기존처럼 로컬 창으로 미리보기를
# 표시한다. Flask 등으로 감쌀 때는 이 블록 대신 app.py에서 DroneController를 사용한다.
# 이륙/착륙/녹화는 이제 명령으로 수행되므로, 단독 실행 시에는 키보드로 트리거한다:
#   t = 이륙, l = 착륙, r = 촬영 시작, s = 촬영 중지, q = 종료
def main(show_preview=True):
    controller = DroneController()
    controller.start()
    try:
        if show_preview:
            while controller.is_running():
                frame = controller.get_latest_frame()
                if frame is not None:
                    cv2.imshow("Tello: Hybrid Mode (Range Expanded)", frame)
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
