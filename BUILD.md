# 드론 앱 만들기 — 맥북에서 할 일 (순서대로)

이 문서대로 하면 **더블클릭 한 번으로 켜지고, 브라우저에 드론 영상·버튼이 뜨는 맥용 앱 하나**(`DroneApp.app`)가 만들어진다.
앱을 만드는 건 반드시 **맥에서** 해야 한다 (맥용 앱은 맥에서만 구울 수 있음. 윈도우 exe와는 별개).

AI 모델(`best.pt`, `yolov8n-pose-test4.pt`)은 이미 레포에 정상적으로 올라와 있으니,
따로 준비할 파일은 없다. 아래 순서만 따라 하면 된다.

---

## 0단계 — 준비물 확인
- 맥북 (애플 실리콘 M1~M4 또는 인텔 맥, 아무거나 ✅)
- 파이썬 3 (아래 1단계에서 확인/설치)
- 텔로 드론, 충전된 배터리 (검증할 때 필요)

## 1단계 — 파이썬 3 확인 (없으면 설치)
1. **터미널**을 연다 (Spotlight에서 `terminal` 검색 → 엔터).
2. 아래를 입력해 파이썬이 있는지 본다:
   ```
   python3 --version
   ```
   - `Python 3.10` 이상이 뜨면 OK, 3단계로.
   - `command not found` 가 뜨면 파이썬이 없는 것 → 아래로.
3. (파이썬이 없을 때) 가장 쉬운 방법은 [python.org](https://www.python.org/downloads/macos/) 에서
   macOS용 최신 3.x 설치 파일을 받아 더블클릭 설치. 설치 후 터미널을 껐다 켜고 `python3 --version` 다시 확인.

## 2단계 — 코드 내려받기
1. GitHub에서 이 브랜치(`claude/drone-control-macos-package-9tfpgx`)를 **Code → Download ZIP** 으로 받는다.
2. ZIP을 원하는 곳에 압축 해제한다. 예: `~/Desktop/drone-app/`
3. 그 폴더 안에 이런 파일들이 있어야 한다 (모델 2개 포함):
   ```
   app.py
   drone_flight_test.py
   drone_flight_algorithm.py
   resource_path.py
   drone.spec
   requirements.txt
   best.pt                      ← AI 모델 (공/농구 관련), 약 5MB
   yolov8n-pose-test4.pt        ← AI 모델 (자세), 약 7MB
   templates/index.html
   ```
   > `best.pt`, `yolov8n-pose-test4.pt` 크기가 몇 MB인지 확인. 몇 바이트밖에 안 되면 잘못 받아진 것이니 다시 ZIP 받기.

## 3단계 — 폴더로 이동 + 필요한 부품(라이브러리) 설치
터미널에서 아래를 **순서대로** 입력한다. (`~/Desktop/drone-app` 은 방금 압축 푼 폴더 경로로 바꾼다)
```
cd ~/Desktop/drone-app
python3 -m venv .venv            # 이 프로젝트 전용 파이썬 환경을 만든다
source .venv/bin/activate        # 그 환경을 켠다 (앞에 (.venv) 가 붙으면 성공)
pip install -r requirements.txt  # 필요한 라이브러리를 전부 설치
```
- flask, djitellopy, ultralytics, opencv, numpy, **pyinstaller** 가 모두 설치된다.
- 시간이 좀 걸린다(특히 ultralytics/torch). 끝날 때까지 기다린다.
- 터미널을 껐다 켠 뒤 다시 작업할 땐 `cd ...` 로 폴더에 들어간 다음 `source .venv/bin/activate` 만 다시 해주면 된다.

## 4단계 — (권장) 앱으로 굽기 전에 먼저 그냥 실행해보기
앱으로 만들기 전에, 파이썬으로 바로 돌려서 잘 되는지 먼저 확인하면 문제 원인 찾기가 쉽다.
1. 드론 전원을 켜고, 맥북 wifi를 **드론 wifi(TELLO-xxxx)** 에 연결한다.
2. 터미널에 입력(`(.venv)` 가 켜져 있어야 함):
   ```
   python3 app.py
   ```
   - 맥이 처음 실행할 때 **"'DroneApp'이(가) 로컬 네트워크의 기기에 접속하려 합니다"** 창을 띄우면 **허용**을 누른다 (드론과 통신하려면 필요).
3. 잠시 뒤 브라우저가 자동으로 열리고 `http://127.0.0.1:5001` 에 영상과 버튼이 보이면 성공.
   - 배터리 숫자가 뜨고, 이륙/착륙/촬영 버튼이 눌리는지 확인.
   - **폰 브라우저 테스트**: 맥과 폰이 같은 네트워크일 때, 폰 브라우저 주소창에
     `http://<맥IP>:5001` 입력. (맥 IP는 **시스템 설정 → Wi‑Fi → 세부사항 → IP 주소**, 또는 터미널에서 `ipconfig getifaddr en0`)
   - ⚠️ 포트가 **5001** 이다. 맥은 5000번을 시스템 기능(AirPlay 수신)이 쓰고 있어서 5001번으로 바꿨다.
4. 끄려면 터미널에서 `Control + C`.
   > 여기서 문제가 나면 앱으로 넘어가지 말고, 화면에 뜬 오류 메시지를 나한테 그대로 보내줘.

## 5단계 — 앱 만들기 (패키징)
터미널에 아래 한 줄을 입력하고 엔터(`(.venv)` 가 켜져 있어야 함):
```
pyinstaller drone.spec
```
- 몇 분 걸린다. 끝나면 폴더에 `build/` 와 `dist/` 가 새로 생긴다.
- **원래 파일(.py, .pt, templates)은 그대로 남아 있다.** 앱만 옆에 새로 생기는 것.
- 완성된 실행 앱: **`dist/DroneApp.app`**

## 6단계 — 앱 실행해보기
1. 드론 켜고 맥북을 드론 wifi에 연결.
2. Finder에서 `dist/DroneApp.app` 을 연다.
   - ⚠️ **처음 열 때** 맥이 *"확인되지 않은 개발자"* 라며 막을 수 있다(개발자 서명을 안 했기 때문, 정상).
     이때는 **아이콘을 마우스 우클릭(또는 Control+클릭) → 열기 → 다시 열기** 를 누르면 실행된다.
     (한 번만 이렇게 하면 다음부터는 더블클릭으로 바로 열린다.)
   - 처음 실행 때 뜨는 **"로컬 네트워크 접속 허용?"** 창은 **허용**.
3. 잠시 뒤 브라우저가 자동으로 열려 영상·버튼이 보이면 성공.
4. 이 `DroneApp.app` 하나만 복사하면 다른 맥에서도 (파이썬 설치 없이) 돌아간다.
   단, **같은 종류의 CPU** 여야 한다 — 애플 실리콘 맥에서 구운 앱은 애플 실리콘 맥에서,
   인텔 맥에서 구운 앱은 인텔 맥에서 돈다. (두 종류 다 지원하려면 `drone.spec` 설명의 `universal2` 참고)
   - 녹화한 mp4는 `DroneApp.app` 이 있는 폴더 안 `recordings/` 에 저장된다.

> **로그(배터리·오류)를 보고 싶으면**: `.app` 을 더블클릭하면 검은 터미널 창이 안 뜬다.
> 대신 터미널에서 앱 안의 실행 파일을 직접 돌리면 로그가 다 보인다:
> ```
> ./dist/DroneApp.app/Contents/MacOS/DroneApp
> ```

## 7단계 — 테스트용 ↔ 실제(농구 촬영) 알고리즘 바꾸기
지금 앱은 **테스트용(사람 추적)** 으로 설정돼 있다. 실제 알고리즘으로 바꾸려면:
1. `app.py` 를 연다.
2. 위쪽의 이 줄을:
   ```python
   from drone_flight_test import DroneController        # 테스트용
   ```
   아래처럼 바꾼다:
   ```python
   from drone_flight_algorithm import DroneController   # 실제 (농구 촬영)
   ```
   (`app.py` 안 주석에 설명 있음.)
3. 다시 `pyinstaller drone.spec` 실행 → 새 `dist/DroneApp.app` 완성.
   > 실제 알고리즘은 `best.pt`, `yolov8n-pose-test4.pt` 를 쓰는데, 둘 다 이미 폴더에 있으니 그대로 되면 된다.

---

## 문제가 생기면 (자주 나는 경우)
패키징은 한 번에 안 되는 게 정상이다. 아래처럼 대처:

- **"확인되지 않은 개발자" 라며 앱이 안 열림** → 6단계처럼 아이콘 **우클릭 → 열기**. (더블클릭 대신 이 방법으로 한 번만 열면 됨)
- **앱을 열었더니 잠깐 뜨다 꺼진다 / 반응이 없다** → 위의 "로그 보고 싶으면" 방법으로 터미널에서 직접 실행해
  빨간 오류 메시지(특히 `ModuleNotFoundError`, `FileNotFoundError` 줄)를 **그대로 복사해서 나한테 보내줘.**
  대부분 `drone.spec` 의 `collect_all(...)` 목록에 빠진 패키지를 추가하면 해결된다.
- **`FileNotFoundError: best.pt` 같은 모델 오류** → `.pt` 파일이 프로젝트 폴더 맨 위에 있는지 확인.
- **드론 연결 안 됨 / 영상 안 나옴** → ① 맥북 wifi가 드론(TELLO-xxxx)에 연결됐는지, ② 첫 실행 때 "로컬 네트워크 허용"을 눌렀는지 확인.
  (허용을 안 눌렀다면 **시스템 설정 → 개인정보 보호 및 보안 → 로컬 네트워크** 에서 DroneApp 을 켜준다.)
- **브라우저가 자동으로 안 열림** → 브라우저 주소창에 직접 `http://127.0.0.1:5001` 입력. (5000 아님, **5001**)
- **`pyinstaller: command not found`** → `(.venv)` 가 켜져 있는지 확인. 안 켜져 있으면 `source .venv/bin/activate` 먼저.

오류 메시지를 그대로 주면 내가 코드/spec을 고쳐서 다시 브랜치에 올려줄게. 그럼 다시 ZIP 받아서 5단계부터 반복하면 된다.
