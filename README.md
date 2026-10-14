# Bongo Cat 자동 선물 헬퍼

선택한 모니터에서 고양이 목록을 만들고, 체크한 고양이에게 선물을 보내는 Windows 프로그램입니다. 한국어·영어 채팅은 SQLite에 기록합니다.

## 사용 순서

1. `release/BongoHelper.exe`를 실행하고 게임 모니터를 선택합니다.
2. **화면 파악**을 누릅니다. 별도 보정은 필요하지 않습니다.
3. 목록에서 이름을 수정하고 **이름·체크 저장**을 누릅니다. 처음 발견한 고양이는 모두 체크 해제 상태입니다.
4. **선택한 고양이 실제 터치 1회**로 위치를 확인합니다. 이 버튼은 연습 모드에서도 실제 클릭합니다.
5. 연습 모드로 **시작**합니다. 선물을 보내려면 정지 후 연습 모드를 해제하고 시작합니다. **F12**로 정지합니다.

말풍선은 한 번 판독하며 3초 동안 추가 기록을 막습니다. 낮은 신뢰도의 문장은 OCR 최선 결과를 그대로 ‘추정’으로, 판독 실패는 ‘실패’로 한 번 기록합니다. 다른 문자체계는 제외하지만 OCR이 한글·영어로 잘못 읽으면 제외되지 않을 수 있습니다.

고유하게 식별한 이동은 이름 수정과 선물 체크를 유지합니다. 사라진 고양이는 삭제하고, 식별이 모호한 새 위치는 체크하지 않습니다. 앱을 다시 열면 다시 체크해야 합니다.

## 개발 및 검증

```powershell
cd D:\BongoCatAutoGift\bongocat_helper
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python bongo.py
.venv\Scripts\python -m pytest -q
```

실행파일 빌드 전 소스의 `selftest`를 실행하면 OCR 모델을 준비합니다.

```powershell
.venv\Scripts\python bongo.py selftest
.venv\Scripts\python -m pip install pyinstaller
.venv\Scripts\python -m PyInstaller BongoHelper.spec --noconfirm --distpath ..\release
..\release\BongoHelper.exe selftest
```

실행파일·OCR 모델 캐시·개인 설정·채팅 DB·화면 캡처는 Git에서 제외합니다. 직접 QA 순서는 로컬 `release/QA_사용법.txt`에 있습니다.

## 설계

- [현재 구현 흐름](docs/diagrams/implemented_v2.mmd)
- [설계 및 검증 기록](docs/md/design.md)
- [원래 명세](bongocat_helper_spec.md)
