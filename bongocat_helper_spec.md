# Bongo Cat 헬퍼 — 개발 명세서 (지정 이름 자동 선물 + 채팅 기록)

> 이 문서는 다른 작업 환경(코딩 에이전트)에 넘겨 구현하기 위한 명세입니다.
> 대상 OS: **Windows 10/11**, 언어: **Python 3.10+**, 사용자: 본인 1명 (배포 X).

---

## 0. 전제와 근거 표기

- [Verified] = 실제 확인됨 / [Static] = 자료·코드 읽기만으로 판단 / [Hypothesis] = 추정, 실행 환경에서 확인 필요
- 게임(Steam 『Bongo Cat』)에는 채팅/선물용 **공개 API가 확인되지 않음** → 화면 캡처 + OCR + 마우스 클릭 방식으로 구현. [Hypothesis]

## 1. 사용자가 제공한 화면에서 관찰된 것 [Verified: 스크린샷 2장 육안 확인]

스크린샷 1 (평상시):
- 고양이 머리 위 좌/우에 **타이머 말풍선** 2개 (`03:29`)
- 고양이 아래: 숫자 칸 (`156 758`) + 메뉴 버튼(`≡`)
- 맨 아래: **이름 태그** (흰 박스, 예: `리네`)

스크린샷 2 (선물 가능 상태 + 채팅):
- 타이머 자리 2곳이 **선물 아이콘**으로 바뀜: 왼쪽 아이콘 + `100`, 오른쪽 아이콘 + `1000`
- 고양이 왼쪽 위에 **채팅 말풍선** (흰 둥근 박스, 예: `야옹 야옹`)
- 숫자 칸 값이 바뀜 (`155 235`) → 숫자는 OCR 대상에서 제외해야 함

확인하지 못한 것 (구현 시 실제 화면으로 확인):
- 로비에서 여러 고양이가 **같은 높이로 한 줄 정렬**되는지 [Hypothesis — 설계의 핵심 가정]
- 선물 아이콘 클릭 1번으로 선물이 끝나는지, 확인 팝업이 뜨는지
- 채팅 말풍선이 몇 초간 유지되는지, 여러 줄로 줄바꿈되는지

## 2. 기능 요구사항

### F1. 지정 이름에게만 자동 선물
1. 화면에서 선물 아이콘(100, 1000 **둘 다**)을 찾는다.
2. 그 아이콘이 속한 고양이의 **이름 태그**를 OCR로 읽는다.
3. 이름이 `targets` 목록과 **정확히 일치**하면 아이콘을 클릭한다. 불일치/애매하면 클릭하지 않고 로그만 남긴다.

### F2. 채팅 기록 저장
1. 채팅 말풍선 텍스트를 OCR로 읽는다.
2. 말풍선과 가장 가까운 이름(가로 위치 기준)을 화자로 붙인다.
3. 새로 나타난 채팅만 `logs/chat_YYYY-MM-DD.txt`에 `HH:MM:SS<TAB>화자<TAB>내용` 형식으로 추가한다.

## 3. 기술 스택

| 용도 | 라이브러리 | 비고 |
|---|---|---|
| 화면 캡처 | `mss` | 빠름, 멀티모니터 지원 |
| 아이콘 찾기 | `opencv-python`, `numpy` | `cv2.matchTemplate` |
| OCR (한글) | `winocr` (Windows 내장 OCR 래퍼) | Tesseract보다 한글 인식이 나은 편 [Hypothesis] |
| 클릭 | `ctypes` (`SetCursorPos`, `SendInput`) | 외부 의존성 없이 |
| 설정 | `json` 또는 `tomllib` | |

```
pip install mss opencv-python numpy pillow winocr
```

### winocr 사용법 [Static: winocr 0.0.15 소스 직접 확인]
- `winocr.recognize_pil_sync(pil_img, lang='ko')` → dict 반환 (WinRT 객체를 snake_case dict로 변환)
- 구조: `result['lines'][i]['text']`, `result['lines'][i]['words'][j]['bounding_rect'] = {x, y, width, height}`
- **라인에는 bbox가 없음** → 단어 bbox들의 합집합으로 라인 bbox를 계산할 것
- 한국어 OCR 언어팩 필요. 없으면 `assert` 실패. 관리자 PowerShell:
  ```
  Add-WindowsCapability -Online -Name "Language.OCR~~~ko-KR~0.0.1.0"
  ```
- 내부에서 `asyncio.run()` 사용 → 이미 이벤트 루프가 도는 곳(예: 비동기 GUI)에서 호출 금지

## 4. 설계

### 4.1 핵심 가정 [Hypothesis]
봉고캣은 작업표시줄 근처에 붙어 있고, 로비의 고양이들이 **가로 한 줄**로 늘어선다. 그래서 화면을 세 개의 가로 띠로 나눌 수 있다.
- **채팅 띠** — 말풍선이 뜨는 높이
- **아이콘 띠** — 타이머/선물 아이콘 높이
- **이름 띠** — 이름 태그 높이

→ 화자/대상 판별은 **x 좌표가 가장 가까운 이름 태그**로 한다. 이 가정이 틀리면(고양이 높이가 제각각) 4.6의 대안으로 바꿔야 한다.

### 4.2 보정(setup) 모드 — `python bongo.py setup`
실제 화면 기준으로 템플릿과 영역을 잡는다. 스크린샷을 축소해서 템플릿을 만들면 배율이 안 맞으므로 **반드시 사용자 PC에서 직접 캡처**.
1. 선물 아이콘이 떠 있을 때 실행 → 전체 화면 캡처 → `cv2.selectROI`로 사용자가 드래그:
   1. 100 아이콘 (숫자 제외, 아이콘 그림만) → `templates/gift_100.png`
   2. 1000 아이콘 → `templates/gift_1000.png`
   3. **이름 띠** (모든 이름 태그가 들어가는 가로 영역)
   4. **채팅 띠** (말풍선이 뜨는 가로 영역)
   5. **아이콘 띠** (선택, 템플릿 검색 범위를 줄여 속도 향상)
2. 결과를 `config.json`에 저장. 모니터 번호와 좌표도 저장.

### 4.3 메인 루프 — `python bongo.py run`
```
매 interval초:
  frame = 캡처(설정한 모니터)
  names = OCR(이름 띠) → [{text, cx}]          # 숫자/시간 패턴 줄 제외
  # F1 선물
  for 템플릿 in [gift_100, gift_1000]:
      hits = matchTemplate(아이콘 띠, 템플릿) ≥ threshold → NMS로 중복 제거
      for hit:
          owner = names 중 |cx - hit.cx| 최소, 그 거리가 max_dx 이하일 때만
          if owner 없음 / 거리 초과 → 로그 "unmatched", 건너뜀
          if normalize(owner) in targets and 쿨다운 아님:
              click(hit 중심) → 마우스 원위치 → 쿨다운 기록
  # F2 채팅
  chats = OCR(채팅 띠) → 라인들을 말풍선 단위로 묶기(세로로 가까운 라인 합치기)
  for chat: speaker = 가장 가까운 이름(cx)
            key = (speaker, normalize(text))
            if key가 chat_gap초 이상 안 보였으면 → 파일에 기록
            last_seen[key] = now
```

### 4.4 세부 규칙
- `normalize(s)`: 앞뒤 공백 제거, 내부 공백 제거, NFC 정규화.
- **이름 일치는 정확히 일치만.** OCR 오인식(예: `리네`→`리녜`) 때문에 퍼지 매칭은 엉뚱한 사람에게 선물할 위험이 있으므로 쓰지 않는다. 대신 `targets`에 별칭을 여러 개 넣을 수 있게 한다.
- 숫자 필터: `^[\d\s:,.]+$` 에 맞는 줄은 이름/채팅에서 제외 (`156 758`, `03:29`, `100`, `1000`).
- 클릭 쿨다운: 같은 위치(±반경 r px)는 `click_cooldown`초 동안 다시 클릭하지 않음 → 아이콘이 바로 안 사라질 때 연타 방지.
- 채팅 중복: 말풍선이 떠 있는 동안 계속 보이므로 `last_seen` 기반으로 **처음 나타날 때만** 기록. 같은 말을 나중에 다시 하면(`chat_gap` 이후) 다시 기록. OCR 흔들림으로 비슷한 중복이 가끔 생길 수 있음 → 허용.

### 4.5 좌표/DPI 주의 [Static: Windows 동작 일반 지식]
- 프로그램 시작 시 `ctypes.windll.shcore.SetProcessDpiAwareness(2)` 호출. 안 하면 125%/150% 배율에서 캡처 좌표와 클릭 좌표가 어긋난다.
- `mss` 좌표는 모니터 기준 → 클릭 시 `monitor['left'] + x`, `monitor['top'] + y`로 변환.
- 클릭: `SetCursorPos` → `SendInput`(LEFTDOWN, LEFTUP, 사이 30~60ms) → 원래 커서 위치 복귀.
- 게임이 클릭을 못 받으면(관리자 권한으로 실행된 경우 등) 스크립트도 관리자 권한으로 실행.

### 4.6 가정이 틀릴 때의 대안
고양이 높이가 제각각이면 "띠" 대신 **고양이별 기준점**을 쓴다. 모든 고양이에 공통으로 있는 UI(예: `≡` 버튼)를 템플릿으로 찾고, 거기서 상대 오프셋으로 이름/아이콘/말풍선 영역을 계산한다. 단 다른 사람 고양이에도 `≡`가 있는지는 확인되지 않음 [Hypothesis].

## 5. 설정 파일 예시 (`config.json`)
```json
{
  "monitor": 1,
  "interval_sec": 1.0,
  "targets": ["리네"],
  "dry_run": true,
  "match_threshold": 0.85,
  "max_dx": 120,
  "click_cooldown_sec": 5,
  "chat_gap_sec": 8,
  "regions": {
    "name_band": [0, 0, 0, 0],
    "chat_band": [0, 0, 0, 0],
    "icon_band": [0, 0, 0, 0]
  },
  "templates": {
    "gift_100": "templates/gift_100.png",
    "gift_1000": "templates/gift_1000.png"
  }
}
```
- `regions` 값은 `[x, y, w, h]`, setup 모드가 채움.
- **처음엔 `dry_run: true`** — 클릭 대신 "클릭했을 것" 로그만 출력. 동작이 맞는 걸 확인한 뒤 `false`.

## 6. 파일 구조
```
bongocat_helper/
  bongo.py          # 진입점: setup / run / test-ocr
  capture.py        # mss 캡처, DPI 설정
  detect.py         # 템플릿 매칭 + NMS
  ocr.py            # winocr 래핑, 라인 bbox 계산, 숫자 필터
  clicker.py        # SendInput 클릭, 커서 복귀
  chatlog.py        # 중복 제거 + 파일 기록
  config.json
  templates/
  logs/             # chat_*.txt, actions_*.txt(선물/스킵 기록)
```

## 7. 디버그 기능 (꼭 넣기)
- `python bongo.py test-ocr` : 현재 화면에서 이름 띠/채팅 띠 OCR 결과와 템플릿 매칭 점수를 출력하고, 박스를 그린 `debug.png` 저장.
- `actions_*.txt`에 모든 판단 기록: `시간 | 아이콘종류 | 매칭점수 | 읽은이름 | 결과(clicked/skipped/unmatched/dry_run)`.
- 종료: 콘솔에서 `Ctrl+C`. 추가로 비상 정지 키(예: `F12`, `GetAsyncKeyState`로 감지)를 둘 것.

## 8. 검증 체크리스트 (사용자 PC에서 실행)
- [ ] 한국어 OCR 언어팩 설치 확인 (`test-ocr`에서 assert 없이 한글이 나오는지)
- [ ] 이름 태그가 정확히 읽히는지 (여러 이름으로)
- [ ] 선물 아이콘 매칭 점수 확인 → `match_threshold` 조정
- [ ] 150% 배율 등에서 `debug.png` 박스 위치가 실제와 맞는지
- [ ] `dry_run`으로 대상 이름일 때만 "클릭 예정"이 뜨는지
- [ ] 실제 클릭 1회 후 선물이 정상 전송되는지, 확인 팝업 유무
- [ ] 채팅이 한 번만 기록되는지, 화자가 맞게 붙는지

## 9. 알려진 한계
- OCR은 100% 정확하지 않음 → 이름 인식 실패 시 선물이 **누락**될 수 있음 (오발송보다 누락이 낫도록 설계).
- 게임 업데이트로 UI가 바뀌면 템플릿/영역 재보정 필요.
- 말풍선이 고양이끼리 겹치면 화자 판별이 틀릴 수 있음.
- 자동 클릭 사용에 따른 계정 제재 위험은 사용자 책임.


## 10. 프로토타입을 만들기전 chatgpt, Codex를 활용해 미리보기를 보여준후 그것에 맞게 제작하기. 
- 기능성이 있는 프로그램을 만드는것이 목표
- 실제 활용이 가능하게 만들어야함
