# 드론 앱 exe 만들기 — 윈도우 노트북에서 할 일 (순서대로)

이 문서대로 하면 **더블클릭 한 번으로 켜지고, 브라우저에 드론 영상·버튼이 뜨는 exe 파일 하나**가 만들어진다.
exe를 만드는 건 반드시 **윈도우에서** 해야 한다 (윈도우 exe는 윈도우에서만 구울 수 있음).

---

## ⚠️ 먼저 읽을 것 — 모델 파일 확인

지금 GitHub에 올라온 `models/best.pt`, `models/yolov8n-pose-test4.pt` 는 **내용이 비어 있는 2바이트짜리 껍데기 파일**이다.
(GitHub 웹에서 빈 파일만 만들어진 것으로 보임. 진짜 AI 모델은 보통 수 MB~수십 MB다.)

→ **네 윈도우 노트북에서, PyCharm에서 원래 쓰던 진짜 `best.pt` 와 `yolov8n-pose-test4.pt` 파일로
`models/` 폴더 안의 빈 파일을 덮어써야 한다.** (아래 2단계)

- **테스트용(사람 추적) exe** 는 이 두 파일이 없어도 만들어진다. (인터넷에서 `yolov8n.pt`를 자동으로 받음)
- **실제(농구 촬영) exe** 는 이 두 파일이 반드시 진짜여야 한다.

권장 순서: **먼저 테스트용으로 exe가 잘 만들어지는지 확인 → 그다음 실제 모델로 교체해서 다시 굽기.**

---

## 0단계 — 준비물 확인
- 윈도우 노트북 (있음 ✅)
- PyChram + Python (있음 ✅)
- 텔로 드론, 충전된 배터리 (검증할 때 필요)

---

## 1단계 — 코드 내려받기
1. GitHub에서 이 브랜치(`feature/drone-flask-refactor`)를 **Code → Download ZIP** 으로 받는다.
2. ZIP을 원하는 곳에 압축 해제한다. 예: `C:\Users\내이름\Desktop\drone-app\`
3. 그 폴더 안에 이런 파일들이 있어야 한다:
   ```
   app.py
   drone_flight_test.py
   drone_flight_algorithm.py
   resource_path.py
   drone.spec
   requirements.txt
   templates\index.html
   models\best.pt
   models\yolov8n-pose-test4.pt
   ```

## 2단계 — 진짜 모델 파일로 교체 (실제 알고리즘용, 지금 해두면 편함)
1. `models\` 폴더를 연다.
2. 안에 있는 껍데기 `best.pt`, `yolov8n-pose-test4.pt` 를, **네가 원래 PyCharm에서 쓰던 진짜 파일**로 덮어쓴다.
   (파일 이름은 똑같이 유지 — 이름이 다르면 코드가 못 찾는다.)
3. 파일 크기가 몇 MB 이상으로 바뀌었으면 제대로 된 것.
   > 테스트용 exe만 먼저 만들 거면 이 단계는 건너뛰어도 된다.

## 3단계 — PyCharm에서 폴더 열기
1. PyCharm 실행 → **File → Open** → 위 압축 푼 폴더 선택.
2. PyCharm이 파이썬 환경(인터프리터)을 물어보면 새로 만들거나 기존 것을 고른다.

## 4단계 — 필요한 부품(라이브러리) 설치
PyCharm 아래쪽 **Terminal** 탭을 열고, 아래 한 줄을 입력하고 엔터:
```
pip install -r requirements.txt
```
- flask, djitellopy, ultralytics, opencv, numpy, **pyinstaller** 가 모두 설치된다.
- 시간이 좀 걸린다(특히 ultralytics/torch). 끝날 때까지 기다린다.

## 5단계 — (권장) exe로 굽기 전에 먼저 그냥 실행해보기
exe로 만들기 전에, 파이썬으로 바로 돌려서 잘 되는지 먼저 확인하면 문제 원인 찾기가 쉽다.
1. 드론 전원을 켜고, 노트북 wifi를 **드론 wifi(TELLO-xxxx)** 에 연결한다.
2. Terminal에 입력:
   ```
   python app.py
   ```
3. 잠시 뒤 브라우저가 자동으로 열리고 `http://127.0.0.1:5000` 에 영상과 버튼이 보이면 성공.
   - 배터리 숫자가 뜨고, 이륙/착륙/촬영 버튼이 눌리는지 확인.
   - **폰 브라우저 테스트**: 노트북과 폰이 같은 네트워크일 때, 폰 브라우저 주소창에
     `http://<노트북IP>:5000` 입력. (노트북 IP는 cmd에서 `ipconfig` → IPv4 주소)
4. 끄려면 Terminal에서 `Ctrl + C`.
   > 여기서 문제가 나면 exe로 넘어가지 말고, 화면에 뜬 오류 메시지를 나한테 그대로 보내줘.

## 6단계 — exe 만들기 (패키징)
Terminal에 아래 한 줄을 입력하고 엔터:
```
pyinstaller drone.spec
```
- 몇 분 걸린다. 끝나면 폴더에 `build\` 와 `dist\` 가 새로 생긴다.
- **원래 파일(.py, models, templates)은 그대로 남아 있다.** exe만 옆에 새로 생기는 것.
- 완성된 실행 파일: **`dist\DroneApp.exe`**

## 7단계 — exe 실행해보기
1. 드론 켜고 노트북을 드론 wifi에 연결.
2. `dist\DroneApp.exe` 를 **더블클릭**.
3. 검은 콘솔 창이 뜨고(로그·오류가 여기 보임), 잠시 뒤 브라우저가 자동으로 열리면 성공.
4. 이 `DroneApp.exe` 파일 하나만 복사하면 다른 윈도우 컴퓨터에서도 (파이썬 설치 없이) 돌아간다.
   - 녹화한 mp4는 exe와 같은 폴더의 `recordings\` 안에 저장된다.

## 8단계 — 테스트용 → 실제(농구 촬영) 알고리즘으로 바꾸기
지금 exe는 **테스트용(사람 추적)** 으로 설정돼 있다. 실제 알고리즘으로 바꾸려면:
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
3. 2단계에서 진짜 모델 파일을 넣었는지 다시 확인.
4. 다시 `pyinstaller drone.spec` 실행 → 새 `dist\DroneApp.exe` 완성.

---

## 문제가 생기면 (자주 나는 경우)
패키징은 한 번에 안 되는 게 정상이다. 아래처럼 대처:

- **exe 더블클릭했더니 콘솔 창에 빨간 오류가 뜨고 닫힌다** →
  콘솔 창의 오류 메시지(특히 `ModuleNotFoundError`, `FileNotFoundError` 줄)를 **그대로 복사해서 나한테 보내줘.**
  대부분 `drone.spec` 의 `collect_all(...)` 목록에 빠진 패키지를 추가하면 해결된다.
- **`FileNotFoundError: best.pt` 같은 모델 오류** → 2단계(진짜 모델 파일 교체)를 안 했거나 파일명이 다른 경우.
- **드론 연결 안 됨 / 영상 안 나옴** → 노트북 wifi가 드론(TELLO-xxxx)에 연결됐는지 확인. (exe 문제가 아니라 연결 문제)
- **브라우저가 자동으로 안 열림** → 브라우저 주소창에 직접 `http://127.0.0.1:5000` 입력.

오류 메시지를 그대로 주면 내가 코드/spec을 고쳐서 다시 브랜치에 올려줄게. 그럼 다시 ZIP 받아서 6단계부터 반복하면 된다.
