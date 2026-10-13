# Bongo Cat 헬퍼 — 구현 설계 (에이전트용)

- 원본 명세: `bongocat_helper_spec.md` (이 문서와 충돌 시 이 문서 우선, 근거 태그는 원본 규칙 사용)
- 폴더 규칙: `docs/md/` = 에이전트 전용(이 문서, 프롬프트). `docs/html/` = 사용자 열람용(`design.html`, `goal/*.png`). 에이전트는 md만 읽고, html은 수정할 때만 연다. 단계 번호는 두 문서 동일하게 유지
- 환경 [Verified 2026-10-12]: Windows 11, Python 3.12.10, Node/npm 없음, Git 저장소 아님
- 진행 규칙: 각 단계 끝의 **게이트**를 통과해야 다음 단계로. 사용자 확인이 필요한 게이트는 🔒 표시.

> **정정 [사용자 2026-10-12]: 선물 아이콘은 좌우 모두 `1000`** (원본 명세의 100/1000은 틀림). 숫자로 종류를 구분하지 않고 **이름표 기준 왼쪽/오른쪽 위치**로 구분한다.
> - 템플릿: `gift_left.png`, `gift_right.png` (그림이 같아도 둘 다 저장, 두 템플릿 히트는 NMS로 합침). 히트의 종류는 템플릿이 아니라 **기하(어느 오프셋에 더 가까운가)** 로 결정
> - 오프셋: `off_left`, `off_right` / 타이머 키: `(이름, left|right)` / 로그 아이콘 열: `L1000`, `R1000`
> - 아래 본문의 `100`/`1000`, `off_100`/`off_1000`, `gift_100`/`gift_1000` 표기는 각각 left/right로 읽을 것

## 진행 상태

| # | 단계 | 상태 |
|---|---|---|
| 0 | Codex로 목표 그림 생성 → 사용자 확인 🔒 | ✅ v4 승인 (2026-10-12) |
| 1 | 프로젝트 골격 + 캡처 + 설정 | ✅ 완료 (단위 11개 통과, capture-test 3모니터 확인) |
| 2 | OCR 모듈 | ✅ 완료 (RapidOCR로 교체, 테스트 32개 통과) |
| 3 | 감지(템플릿 매칭 + 이름 매칭) | ✅ 완료 (합성 화면 테스트 25개 포함 전체 57개 통과) |
| 4 | 보정 `setup` 🔒 | 🟡 구현 완료(테스트 65개 통과), 사용자 실제 게임 실행 대기 |
| 5 | 디버그 `test-ocr` 🔒 | 🟡 구현+실제 화면 검증(이름표/OCR/CPU) 완료, 선물 아이콘 실측은 사용자 보정 후 |
| 6 | 자동 선물 (dry_run → 실제) 🔒 | 🟡 구현 완료(테스트 92개), 실제 아이콘 보정+연습 모드+실제 클릭 1회는 사용자 확인 대기 |
| 7 | 채팅 기록 🔒 | 🟡 구현 완료(테스트 100개), 실제 말풍선 모양은 미관찰 → 사용자 화면 확인 대기 |
| 8 | 제어 패널 GUI 🔒 | ✅ 구현+exe 확인 (테스트 106개), 실제 게임 사용 확인 대기 |
| 9 | 마무리: 최종 exe·점검·문서 | ✅ (2026-10-12) |

---

## 0. Codex 목표 그림 (API 키 없이, ChatGPT OAuth)

사실 확인 [Verified 2026-10-12]:
- CLI: `C:\Users\User\AppData\Local\OpenAI\Codex\bin\2e5e00daee91c61d\codex.exe` (`codex-cli 0.162.0-alpha.17.2`, Codex 데스크톱 앱 동봉. 해시 폴더는 앱 업데이트 시 바뀔 수 있음 → `tools/find_codex.ps1`로 탐색)
- `codex login status` → `Logged in using ChatGPT` (`~/.codex/auth.json`, `auth_mode=chatgpt`, API 키 없음)
- `codex features list` → `image_generation  stable  true`

절차:
1. `tools/codex_image.ps1 -PromptFile docs/md/prompts/prompt_vN.txt -Out docs/html/goal/goal_vN.png` 작성
   - 내부: `codex exec --skip-git-repo-check --sandbox workspace-write -C D:\BongoAutoCat "<프롬프트> ... image_gen 도구로 생성하고 결과 PNG를 docs/html/goal/goal_vN.png 로 저장"`
   - [Hypothesis] image_gen 결과 저장 위치가 `~/.codex/` 하위일 수 있음 → 프롬프트에 복사 지시 포함, 실행 후 파일 존재 확인
2. 프롬프트 원문: `docs/md/prompts/prompt_vN.txt` (아래 §0.1)
3. 생성 결과를 `docs/html/design.html`의 "목표 그림" 칸에 연결(`goal/goal_vN.png`, html 기준 상대경로), 사용자에게 보여줌
4. 🔒 게이트: 사용자가 그림 승인. 수정 요청 시 v(N+1)로 재생성. 승인된 버전을 `docs/md/prompts/APPROVED.txt`에 기록

### 0.1 이미지 프롬프트 v1
```
Windows 데스크톱 유틸리티 UI 목업. 위: 'Bongo Cat' 게임 화면(작업표시줄 위 고양이 3마리 가로 정렬,
각 고양이 아래 흰 이름 태그 '리네','철수','민지', 머리 위 선물 아이콘 '100','1000', 왼쪽 위 흰 말풍선 '야옹 야옹')
위에 디버그 오버레이: 채팅/아이콘/이름 영역을 점선 가로 띠로 표시, 대상 이름과 일치한 선물 아이콘은
초록 박스+매칭점수, 불일치는 빨간 박스. 아래: 작은 tkinter 제어 패널 — 시작/정지(F12)/보정/OCR 테스트 버튼,
dry run 체크박스, 선물 대상 목록, 선물·채팅 카운터, 실시간 로그(시간|아이콘|점수|이름|결과). 플랫하고 깔끔한 스타일, 한국어 라벨.
```

---

## 1. 골격 + 캡처 + 설정

파일:
```
bongocat_helper/
  bongo.py        # argparse: setup | run | test-ocr | gui
  config.py       # load/save, 기본값 병합, 경로는 이 폴더 기준
  capture.py      # set_dpi_aware(), grab(monitor) -> np.ndarray(BGR), crop(frame, [x,y,w,h])
  detect.py / cats.py / engine.py / chatlog.py / clicker.py / gui.py   # 3~8단계
  requirements.txt  # mss opencv-python numpy pillow winocr
  tests/
```
- `SetProcessDpiAwareness(2)` 를 **어떤 창/캡처보다 먼저** 호출 (실패 시 `SetProcessDPIAware` 폴백)
- 가상환경: `bongocat_helper/.venv`
- 게이트: `pytest` 통과(config 왕복, crop 범위 검사), `python bongo.py capture-test` 가 PNG 저장

## 2. OCR (`ocr.py`) ✅
**엔진 변경 [Verified 2026-10-12]: Windows OCR(winocr) → RapidOCR 한국어 인식 모델** (사용자 승인 후 모델 다운로드)
- 측정(맑은 고딕 렌더링, 이름 10개 x 크기 3종): Windows OCR 최고 21/30 (전처리 조합 12종 시도, '철수'는 0회). RapidOCR `korean_PP-OCRv5_rec_mobile` 인식 전용 30/30, 평균 34ms. 검출 모델까지 쓰면 1.1s라 사용 안 함
- 모델: `bongocat_helper/models/korean_PP-OCRv5_rec_mobile.onnx` (~12MB, 첫 실행 시 modelscope.cn에서 자동 다운로드). 의존성 `rapidocr`, `onnxruntime`. winocr 제거
- 전제: 호출자가 **이미 잘라낸 박스**(이름표, 말풍선)를 넘긴다 → 검출 단계 불필요 (§3 설계와 일치)
- API
  - `recognize(crop) -> (text, score)` 한 줄. 잉크 영역으로 잘라낸 뒤 글자 높이 x0.25 여백(배경색)을 붙여 정규화 — 여백에 민감해서 필수 (고정 여백 8/16px은 오인식 발생, 비례 여백은 크기 12~36px 50/50)
  - `read_lines(crop, offset) -> [Line{text,x,y,w,h,score,cx,cy}]` 여러 줄: 잉크 행 투영으로 줄 분리 → 줄 단위 인식(음절 단위로 쪼개면 정확도 떨어짐 확인). 모델이 공백을 안 내면 넓은 열 간격 위치에 공백 삽입
  - `ink_mask`(어두운 글자/밝은 글자 자동), `split_lines`, `word_gaps`, `insert_spaces`, `is_numeric`, `normalize`, `ensure_ready()`
  - 엔진 1개 공유 + `threading.Lock` (GUI 작업 스레드에서 호출 가능, asyncio 제약 없음)
- 채팅 문장 벤치(8문장 x 크기 3 x 흰/회색 배경): 정확 46/48, 띄어쓰기만 다름 1, 오인식 1(14px 회색 '최고'→'최괴'), 줄당 34ms
- 게이트 결과: 단위+실제 OCR 테스트 32개 통과. 🔒 실제 게임 글꼴/크기는 5단계에서 확인 (렌더링 테스트는 맑은 고딕 기준)

## 3. 감지 (`detect.py`) + 고양이 목록 (`cats.py`) + 저부하 루프 (`engine.py`)

[사용자 요구 2026-10-12] 고양이 x 위치는 무작위, **높이(y)도 같을 수도 다를 수도 있음**. 고양이별 수동 설정 금지, 자원 적게.
→ 원본 명세의 "가로 띠 3개" 방식은 **폐기**. 고정 y에 의존하지 않는 **이름표 기준점(앵커) 방식**으로 통일. 높이가 같은 경우는 이 방식의 특수한 경우일 뿐, 코드 분기 없음.

### 3.1 핵심 아이디어: 이름표 = 고양이 기준점
- 이름표(흰 박스)는 고양이마다 **항상** 있음 [Verified: 스크린샷 2장] → 고양이 위치의 기준점
- 같은 고양이의 선물 아이콘·숫자칸·말풍선은 이름표에서 **항상 같은 상대 위치(dx, dy)** 에 있음 [Hypothesis, 5단계에서 확인] → setup에서 1마리로 한 번만 측정
  - `off_100 = (icon100.cx - tag.cx, icon100.cy - tag.cy)`, `off_1000`, `off_bubble`(말풍선 꼬리/중심)
- 판별은 x만이 아니라 **2D 거리**: `owner(hit) = argmin_cat ‖hit.c - (cat.tag.c + off[hit.type])‖`, 거리 ≤ `max_dist`일 때만. 1·2위 차이 < `ambiguity_px` 이면 `unmatched`(안 보냄)
  - 고양이끼리 가깝거나 높이가 달라도, 각 아이콘이 "자기 이름표 기준 예상 위치"와 비교되므로 이웃 고양이로 잘못 붙지 않음
- 보너스 검증: 같은 고양이의 100·1000은 서로 `off_1000 - off_100` 만큼 떨어져 있음 → 둘 다 보이면 짝 맞춤으로 신뢰도 상승

### 3.2 고양이 목록(캐시) 유지 — OCR을 거의 안 부르는 구조
`CatRegistry`: `[{id, tag_box, name, last_seen}]`
1. **이름표 후보 찾기 (OCR 없음, 수 ms)**: 감지 영역을 흑백 → 밝은 영역 이진화 → 윤곽선 → setup에서 잰 이름표 높이 ±25%, 가로/세로 비율 범위인 사각형만
   - 숫자칸(`156 758`)도 흰 박스일 수 있음 → 이름표 기준 `off_number` 위치의 박스는 제외 + OCR 결과가 숫자면 제외
   - 말풍선은 크기/모양(둥근 꼬리, 높이 큼)으로 구분 [Hypothesis, 5단계 확인]
2. **이름 OCR은 새 이름표일 때만**: 기존 고양이와 위치가 `move_tol` 이내면 같은 고양이로 보고 캐시된 이름 재사용. 새로 나타났거나 박스 크기가 바뀐 경우에만 그 박스 1개를 OCR
3. 일정 시간(`cat_ttl_sec`) 안 보이면 목록에서 제거

### 3.3 매 주기 처리 순서 (비용 낮은 것부터)
비용: 캡처 ≪ 차이 비교 ≪ 윤곽선/템플릿 매칭 ≪ OCR(수십~수백 ms)
1. 캡처: setup에서 지정한 **감지 영역 1개**(고양이가 나타날 수 있는 범위 전체)만 `mss.grab(region)`
2. 변화 감지: 1/4 축소 흑백을 64px 타일로 나눠 이전 프레임과 평균 절대차 → **바뀐 타일만** 이후 처리. 하나도 안 바뀌면 이번 주기 종료
3. 바뀐 타일에서: 이름표 후보 갱신(§3.2), 선물 템플릿 매칭(흑백·0.5배, 바뀐 타일 합집합 영역만)
4. 선물 히트 → 주인 판별(§3.1) → 대상이면 클릭/dry_run
5. 말풍선 후보가 새로 생긴 경우에만 그 박스를 OCR → 화자 = `off_bubble` 기준 2D 최근접 고양이
6. 적응형 주기: 변화 없으면 `interval_sec`→`idle_interval_sec`(1s→2s), 변화 생기면 즉시 원복
7. 계측: 단계별 ms 기록, `test-ocr`에서 평균/최대 출력
목표 [Hypothesis, 5단계 측정]: 평상시 CPU 1~2% 이하, 선물 이벤트 1회 처리 < 300ms

### 3.4 실패 시 대체
- 이름표 윤곽선 검출이 불안정하면: 이름표 테두리 일부를 템플릿으로 저장해 템플릿 매칭으로 교체(setup에서 이미 잘라둠)
- 아이콘은 보이는데 이름표 매칭 실패 → `unmatched` 로그, 보내지 않음 (오발송 < 누락)

### 3.5 구현 결과 ✅ (2026-10-12)
- `detect.py`: `Box`, `Hit`, `nms`, `find_templates(img, templates, threshold, scale=0.5, offset)`, `find_tag_boxes(img, tag_h, tol, min_aspect, max_aspect, min_fill=0.85, bright=220)`, `assign_owner(point, anchors, offsets, max_dist, ambiguity_px) -> Owner{index, side, dist}`, `ChangeDetector(tile=64, factor=4, threshold=8).feed(img) -> [rect]`(첫 프레임은 전체), `merge_rects`, `pad_rect`
  - 이름표: 밝은 영역(>220) 외곽선 중 높이 tag_h±25%, 가로/세로 1.2~10, 사각형 채움률 ≥0.85 (흰 고양이 몸통은 채움률로 걸러짐). 찾은 박스는 테두리 포함하도록 2px 확장
  - 모호성: 1위와 **다른 고양이** 2위의 거리 차가 ambiguity_px 미만이면 None (같은 고양이 좌/우끼리는 모호성 아님)
- `cats.py`: `CatRegistry(read=read_tag, move_tol=8, ttl=10)` — `update(boxes, frame, now, scanned=None)`, `cats()`, `owner_of(point, offsets, max_dist, ambiguity_px) -> CatOwner{cat, side, dist}`
  - 새 박스만 OCR. 숫자/저신뢰 박스는 `name=None`으로 기억해 재OCR 안 함. scanned 영역 밖 고양이는 유지(화면 변화 없음), 안쪽에서 사라진 고양이만 ttl 후 제거
- 테스트(`tests/scene.py` 합성 화면: 파란 노이즈 배경 + 흰 반타원 몸통 + 테두리 이름표 + 같은 그림 1000 아이콘 좌우): 같은 높이 / 높이 다름 / 가깝고 엇갈림 3배치 x (아이콘 6개 검출, 이름표 검출, 주인 판별, 실제 OCR로 이름 읽기), 모호/먼 히트 거부, NMS, 변화 감지, 재OCR 안 함
- 측정(1920x500 영역, 고양이 6마리): 변화 감지 2.1ms, 이름표 검출 1.6ms, 아이콘 검출 11.9ms, 캐시된 고양이 갱신 0.01ms, 첫 등록 6마리 OCR 1.1s(모델 로딩 포함 1회)
- 남은 것: 말풍선 박스 검출 `find_bubble_boxes`는 7단계(채팅)에서. 이 단계의 모든 검증은 합성 화면 기준 → 실제 게임의 이름표 모양/밝기/고양이 몸통과의 접촉 여부는 🔒 5단계에서 확인 (실패 시 §3.4 tag_edge 템플릿 대안)

## 4. 보정 `setup` 🔒
고양이 1마리 기준으로 한 번만. 큰 화면은 축소 표시 후 좌표 역변환.
1. **감지 영역** 드래그: 고양이가 나타날 수 있는 범위 전체(가장 높은 고양이의 말풍선 ~ 작업표시줄)
2. 선물이 떠 있는 고양이 1마리에서 차례로 드래그: 100 아이콘 → 1000 아이콘 → 이름표 → (있으면) 말풍선 → (선택) 숫자칸
3. 자동 계산·저장: `templates/gift_100.png`, `templates/gift_1000.png`, `templates/tag_edge.png`, 이름표 높이/비율, `off_100`, `off_1000`, `off_bubble`, `off_number`, monitor, region
- 말풍선이 그때 없으면 나중에 `python bongo.py setup --bubble`로 추가
- 구현 ✅ (2026-10-12): `calib.py` — `STEPS`(6개, 5·6 선택), `compute(frame, rects) -> SetupResult{region, offsets, tag{height=흰 내부 높이, aspect}, templates}`, `verify(frame, res, read) -> Report{tags, icons, owned, names, image}`, `apply(cfg, res, monitor, templates_dir)`, `select_rects`(감지 영역 지정 후 다음 단계는 영역만 최대 3배 확대 표시, 한글 안내 띠는 PIL로), `show`
  - `bongo.py setup [--monitor N] [--delay 3] [--image PNG]`: 모니터 선택(입력) → 카운트다운 캡처 → 드래그 → 검증 결과 출력+창 표시 → Y면 `templates/*.png`, `config.json` 저장. `logs/setup_frame.png`, `logs/setup_check.png` 남김
  - 이름표 높이는 사용자가 그린 박스 안의 Otsu 밝은 영역 = `find_tag_boxes`가 비교하는 값과 같은 기준
  - 테스트: 오프셋/높이 계산, zone 좌표 독립성, 말풍선 선택 오프셋, 검증 오류 3종, 새 설정으로 3마리·6아이콘·6주인 검증, UI 좌표 역변환(selectROI 모킹, zone 확대 포함)
  - 미검증: 실제 OpenCV 창에서 드래그 조작(에이전트가 네이티브 창을 조작할 수 없음) → 사용자 실행으로 확인
- 🔒 게이트: 사용자가 실제 게임 화면에서 실행 성공

## 5. 디버그 `test-ocr` 🔒
- 출력: 찾은 고양이 목록(이름표 박스, 읽은 이름), 아이콘 히트와 점수·주인, 말풍선과 화자, 단계별 ms
- `debug.png`: 감지 영역(점선), 이름표(초록=대상/빨강=비대상), 각 이름표 기준 예상 아이콘 위치(작은 십자), 실제 히트 박스, 히트→이름표 연결선
### 5.1 실제 게임 화면 관찰 [Verified 2026-10-12, release/logs/setup_frame.png, 모니터2 2560x1440]
- 고양이가 작업표시줄이 아니라 화면 중간에 떠 있음, 세로로 겹쳐 쌓임 → 위치 무작위(높이 포함) 가정 확인
- **내 고양이**(검은 박쥐): 이름표 없음, 숫자칸 `157 444`(계속 증가하는 카운터) + 정사각형 `≡` 버튼
- **다른 사람 고양이**(보라): 이름표 `리네` — 연회청색 박스(회색값 ~223), 1~2px 검은 테두리, 연회색 글자(높이 ~10px), 박스 약 105x24px
- 고양이 주변에 하트/반짝이 파티클, 고양이 발 두드림 애니메이션의 갈색 동작선이 이름표 위를 지나감
- 이번 캡처엔 선물 아이콘이 없었음 → 아이콘 매칭 점수/오프셋은 사용자 보정 때 실측 필요

### 5.2 실제 화면에서 발견해 고친 것
| 문제 | 원인(측정) | 수정 |
|---|---|---|
| 이름표 신뢰도 0.75 | 테두리 포함 → Otsu가 테두리 vs 나머지로 나눔 | `cats.tag_interior`: 테두리 3px 제외 → 0.999 |
| 박스 밝기 223이 임계 220에 걸침 | 실제 이름표가 순백 아님 | `find_tag_boxes(bright=200)` |
| `155580\|`가 이름으로 등록 | 숫자 필터가 OCR 잡문자에 약함 | `is_numeric`: 한글/영숫자 외 문자 제거 후 숫자만이면 숫자 |
| 같은 이름표를 `우리네`(0.93)/`리네오`(0.81)로 오독 | 발 애니메이션 선이 겹친 프레임 | 신뢰도 ≥0.97로 **같은 이름 2회** 읽혀야 확정, 미확정은 선물 대상 아님. 숫자는 ≥0.6 |
| 애니메이션 멈추면 영원히 미확정 | 변화 없는 영역은 다시 안 읽음 | 미확정 이름표는 화면 변화와 무관하게 0.5초마다 현재 프레임으로 재판독 |
| 같은 고양이 중복 등록 | 스캔 영역 경계에 잘린 반쪽 이름표 | 이미지 경계에 닿은 박스 버림 + 기존 이름표 안에 중심이 있으면 같은 고양이 |
| **CPU 64.6%** | onnxruntime 기본 스레드가 호출 뒤 대기 중 스핀(1회 호출 후 3초간 CPU 8.6초) | intra/inter 스레드 1개: 호출 35ms, 대기 CPU 0 |
| (안전) 미확정 이웃 고양이 아이콘이 확정 고양이에 붙을 수 있음 | 주인 후보에서 미확정 제외했었음 | 주인 판별 후보에 미확정 포함, 미확정이 이기면 None |
| (안전) 단색 영역을 아이콘으로 지정 | 평평한 템플릿은 아무 데나 매칭됨(가짜 템플릿으로 7곳 매칭 확인) | setup에서 흐림 후 표준편차 <12면 거부 |

### 5.3 구현
- `debug.py`: `analyze(zone, tag_h, templates, offsets, threshold, max_dist, ambiguity_px, targets, read)` → `Analysis{cats, ignored, pending, hits[HitInfo], timings, image}` (setup 검증도 이걸 사용, 1프레임이라 votes=1), `draw`(PIL 한글 라벨: 대상 초록/비대상 빨강/숫자 회색/미확정 파랑, 예상 아이콘 위치 주황 십자, 히트→이름표 선), `load_templates`, `watch(grab, cfg, templates, seconds)` (변화 감지→변한 영역+48px만 처리, 통계)
- `bongo.py test-ocr [--image PNG] [--watch SEC]`, 메뉴 3번 = test-ocr --watch 30. 보정 전이면 안내 후 종료
- 실측(모니터2 실제 화면, 고양이 2마리): 1회 평균 14.5ms / 최대 61ms, 40초에 OCR 4회, **CPU 0.4%(1코어 기준, 32스레드 PC)**, 인식 `리네` 1마리
- 고정 회귀 테스트: `tests/fixtures/real_zone_rine.png`(실제 화면 300x320) — 이름표+숫자칸 2개 검출, `리네` 확정, 숫자칸 무시. 전체 테스트 79개 통과
- exe 재빌드(메뉴 4개), 깨끗한 폴더에서 셀프 테스트·디버그 메뉴 확인

- 🔒 게이트: (a) 높이가 같은 상황과 다른 상황 각각에서 박스·연결선이 맞는지 (b) `match_threshold`, `max_dist` 확정 (c) 평상시 CPU 측정

## 6. 자동 선물 🔒
- `clicker.py`: `SetCursorPos` → `SendInput` DOWN/UP(30~60ms 랜덤) → 커서 복귀. 좌표 = monitor left/top + 로컬
- 루프: 정확히 일치 + 쿨다운(±r px, `click_cooldown_sec`) → click 또는 dry_run 로그
- `logs/actions_YYYY-MM-DD.txt`: `시간 | 아이콘 | 점수 | 이름 | clicked/skipped/unmatched/dry_run/cooldown`
- 비상 정지: `GetAsyncKeyState(VK_F12)` 폴링 → 즉시 루프 종료

### 6.1 선물 재생성 카운트다운 [사용자 정보 2026-10-12: 선물 누르면 30분 뒤 다시 생김]
- `gift_timer.py`: `GiftTimers(cooldown_sec=1800)` — 키 `(이름, 아이콘종류)`, 값 `next_ready_at`
  - 클릭(또는 dry_run 시 "클릭했을 것") 성공 시 `next_ready_at = now + cooldown`
  - `remaining(name, type)`, `upcoming() -> [(name, type, 남은초)]` 남은 시간 순
  - `data/chat.db`의 `gift(ts, name, type, result)` 테이블에 기록 → 재시작해도 카운트다운 복원
- 자원 절약에 활용: 대상 고양이 아이콘이 카운트다운 중이면 그 고양이 주변 템플릿 매칭 생략, 남은 시간 `wake_before_sec`(예 15초) 전부터 다시 검사. 모든 대상이 대기 중이면 루프 주기 크게 늘림(예 5초)
- 검증 [Hypothesis]: 게임 타이머 말풍선(`MM:SS`)과 계산값 비교 — `test-ocr`에서만 타이머 OCR해 차이 출력. 평소 루프에서는 OCR 안 함
- 예정 시각이 지났는데 아이콘이 `late_grace_sec` 이상 안 보이면 로그 `late`(게임 쪽 타이머가 다를 가능성 → 값 조정 안내)
- 실제 클릭 확인: 클릭 후 수 초 안에 그 아이콘이 사라졌는지 확인해 `clicked_ok` / `clicked_no_change` 구분 (사라지지 않으면 타이머 시작 안 함)
- GUI: 왼쪽 열에 **다음 선물** 목록 `리네 100 · 12:34 남음` (1초마다 갱신, 준비되면 초록 '준비됨'), 선택 시 Windows 토스트 알림 옵션(기본 끔)
- config: `gift_cooldown_sec: 1800`, `wake_before_sec: 15`, `late_grace_sec: 60`
- 게이트: 단위 테스트(시간 주입: 클릭→남은시간, 재시작 복원, 대기 중 검사 생략 판단). 🔒 실제 30분 후 재생성 시각 확인
- 🔒 게이트: (a) dry_run에서 대상일 때만 dry_run 로그 (b) 사용자 승인 후 `dry_run=false` 실제 1회, 확인 팝업 유무 기록 → 팝업 있으면 처리 단계 추가 설계

### 6.2 구현 결과 (2026-10-12)
- `gift_timer.py` `GiftTimers(cooldown)`: `start/remaining/cooling/ready_at/upcoming/restore` — 키 (이름, left|right)
- `store.py` `Store(data/bongo.db)` (설계의 chat.db 대신 bongo.db 하나에 gift, 7단계에서 chat 테이블 추가): `add_gift`, `recent_gifts`, `count_gifts`. 스레드 락
- `clicker.py`: `Clicker.click(x, y)` SetCursorPos→SendInput DOWN/UP(30~60ms)→커서 복귀, `INPUT` 구조체 40바이트 확인. `stop_pressed()` = F12
- `engine.py` `Engine(cfg, grab, clicker, store, templates, read, clock, monitor)`, `tick() -> [Event]`, `format_event` → `HH:MM:SS | L1000 | 0.93 | 리네 | dry_run`
  - 순서: 변화 감지 → 이름표/고양이 갱신(미확정 재판독) → 클릭 확인(1.5초 뒤 아이콘 사라졌으면 clicked_ok+타이머, 그대로면 clicked_no_change, 타이머 없음) → 아이콘 검색 → 판단
  - 판단: 주인 없음 unmatched / 대상 아님 skipped / 카운트다운 중 cooldown / 확인 대기·같은 위치 5초 내 재클릭 금지 / dry_run이면 타이머 시작+기록 / 실제면 클릭
  - 아이콘 검색 생략: 미확정 고양이 없음 + 화면의 모든 대상 고양이 양쪽이 `wake_before_sec`(15초) 넘게 남음 + 확인 대기 없음
  - 전체 영역 검색: 5초마다 또는 새 고양이 확정 시 (움직이지 않는 아이콘 대비). 그 외엔 변한 영역+48px만
  - late: 준비 시각+60초 지나도 그 키 아이콘이 안 보이면 1회 경고(타이머 재시작 시 초기화)
  - 같은 비클릭 판단은 1분에 1번만 기록
- `bongo.py run [--live]` (연습 모드 기본, `--live`는 yes 입력 확인), `targets [--add] [--remove]`(대화형 가능). 로그 `logs/actions_YYYY-MM-DD.txt`, 30초마다 "다음 선물" 카운트다운 출력, 재시작 시 DB에서 타이머 복원
- exe 메뉴 7개: 1 보정 · 2 캡처 테스트 · 3 디버그 · 4 셀프 테스트 · 5 선물 대상 편집 · 6 실행(연습) · 7 실행(실제 클릭)
- 테스트: 연습 모드 대상만/비대상 skipped/클릭 없음, 연습 모드 반복 없음, 실제 클릭 화면 좌표(모니터 원점+영역) + clicked_ok, 효과 없는 클릭은 타이머 없이 5초 후 재시도, 미확정 고양이 무시, 모든 대상 대기 중 템플릿 검색 0회→30분 후 재개, 재시작 타이머 복원, 로그 형식, late 1회
- 실제 화면 배선 확인(연습 모드 12초, 가짜 템플릿=≡ 버튼): unmatched 1회 기록, 클릭 0회, F12 종료
- **실제 화면에서 발견**: 고정 0.5배 축소에서 22x24 템플릿이 **전혀 매칭 안 됨** → `find_templates(scale=None)` 자동: 축소 후 최소 20px 유지 (회귀 테스트 추가). 실제 선물 아이콘도 작을 것이므로 중요
- exe 수정: 메뉴의 `—` 문자가 cp949 파이프 출력에서 크래시 → 문자 교체 + stdout/stderr `errors="replace"`
- 🔒 남은 확인: (a) 아이콘 떠 있을 때 보정 (b) 연습 모드로 대상만 dry_run 찍히는지 (c) 실제 클릭 1회: 선물 전송 여부, 확인 팝업 유무 → 팝업 있으면 처리 단계 추가

## 7. 채팅 기록 🔒
[사용자 결정 2026-10-12: 실행 중 PC 파일에 자동 저장 → 패널에서 열람 → 원할 때 MD로 내보내기]
- 원본 명세의 `logs/chat_*.txt` 직접 기록은 **대체**함
- 저장소: `data/chat.db` (SQLite, 표준 라이브러리 `sqlite3`, 의존성 추가 없음). 꺼지거나 튕겨도 유지
  - 테이블 `chat(id INTEGER PK, ts TEXT ISO, date TEXT, speaker TEXT, text TEXT)`, 인덱스 `(date)`, `(speaker)`
- `chatlog.py`:
  - `ChatDedup(gap_sec).observe(speaker, text, now) -> bool` (`last_seen[(speaker, normalize(text))]`)
  - `ChatStore(path)`: `add(ts, speaker, text)`, `query(date=None, speaker=None, keyword=None) -> list`, `dates()`, `speakers(date)`
  - `export_md(rows, path)`: 날짜별 제목, `- **HH:MM:SS** 화자: 내용` 형식, `exports/chat_YYYY-MM-DD[_화자].md`
- 콘솔: `python bongo.py chat show [--date] [--speaker]`, `python bongo.py chat export [--date] [--speaker]`
- 게이트: 단위 테스트(중복 1회, gap 후 재기록, 저장/조회 필터, MD 형식). 🔒 실제 화면에서 화자 매칭 확인

### 7.1 구현 결과 (2026-10-12)
- 저장소: `data/bongo.db`의 `chat(ts, date, speaker, text)` (설계의 chat.db 대신 gift와 같은 DB). `Store.add_chat/query_chat(date, speaker, keyword)/chat_dates/chat_speakers`
- `detect.find_bubble_boxes(img, tag_h, exclude, offset)`: 밝은 덩어리 중 높이 0.9~6x tag_h, 폭 ≥1.5x tag_h 이면서 **폭 ≥1.3x 높이**, 채움률 ≥0.6, **모서리가 둥근 것**(4모서리 중 3개 이상 바깥), 윤곽선 안 글자(어두운 픽셀) 4~50%, 알려진 이름표/숫자칸 박스 안이 아닌 것
  - 이름표와 구분: 이름표는 직각 → `find_tag_boxes`도 둥근 덩어리는 거부 (한 줄 말풍선이 이름표로 잡히던 문제)
  - 고양이 몸통: 윤곽선 **안쪽** 글자 비율로 거부 (bbox 기준이면 배경 모서리가 글자로 계산되던 문제)
  - 실제 데스크톱 전체에서 둥근 도움말 버튼·작업표시줄 아이콘이 걸리던 것 → 폭 ≥1.3x 높이 규칙
- `chatlog.py`: `ChatDedup(gap)`(띄어쓰기 무시 같은 말은 gap 안에선 1번), `BubbleReader`(새 말풍선은 0.5초 안정된 뒤 1번만 OCR, 신뢰도 ≥0.8, 최대 3회 재시도, 2초 안 보이면 삭제; 화자 = 이름표+`offsets.bubble` 기준 최근접, 미보정이면 `?`), `export_md(rows, out_dir, hint)` → `exports/chat_<날짜>[_<끝날짜>][_<필터>].md`, 날짜별 `## YYYY-MM-DD` + `- **HH:MM:SS** 화자: 내용`
- 엔진: 매 tick 이름표 갱신 직후 말풍선 처리(선물 검색 생략 중에도 채팅은 동작), 이벤트 `HH:MM:SS | 채팅 | 리네: 야옹 야옹`
- `setup --bubble`(기본 보정 뒤, 말풍선 떠 있을 때 말풍선+그 이름표 2개 드래그 → `offsets.bubble`), `chat [show|export] [--date] [--speaker] [--search]`(인자 없으면 대화형), `test-ocr`에 말풍선/화자 출력, debug.png에 말풍선 자홍색
- 메뉴: 8 채팅 기록 보기/MD 내보내기 · 9 말풍선 보정
- 확인: 가상 화면(말풍선 2개)에서 test-ocr → 이름 3, 아이콘 4 주인 정확, 말풍선 2개 화자·내용 정확(36ms). chat CLI 조회/필터/내보내기 확인
- 한계: 같은 크기 말풍선에서 글자만 바뀌면 다시 안 읽음(크기가 같으면 같은 말풍선으로 봄). 실제 말풍선 모양/색은 미관찰 [Hypothesis] → 🔒 실제 화면 확인

## 8. 제어 패널 GUI 🔒
- `gui.py` (tkinter, 의존성 추가 없음): 시작/정지, F12, 보정, OCR 테스트, dry_run 체크, 대상 목록 편집(config 저장), 선물/채팅 카운터
- 오른쪽 탭 2개: **판단 로그**(실시간) / **채팅 기록**(날짜 선택, 화자 필터, 검색, `ttk.Treeview` 시간|화자|내용, 새 채팅 실시간 추가, `MD로 내보내기` 버튼 → 현재 필터 결과 저장 후 경로 표시)
- 하단 상태줄: `저장: data/chat.db · 오늘 N건`
- 엔진은 `threading.Thread`, UI 갱신은 `queue.Queue` + `after()` 폴링
- 🔒 게이트: 사용자가 GUI만으로 setup→test→run 전 과정 수행

### 8.1 구현 결과 (2026-10-12)
- `gui.py`: `Runner`(작업 스레드: 스레드 전용 Capturer → `Engine.tick()` → `queue`, F12/정지 감지, 예외는 `error`로 UI 표시), `App`(tk 레이아웃 = v4 그림), `cli_command`(소스/exe 모두 이 프로그램 CLI 실행), `main()`
  - 위: 시작 · 정지(F12) · 보정 · 말풍선 보정 · OCR 테스트(=test-ocr --watch 30) · dry run 체크(기본 켜짐) · 상태 배지(멈춤 / 연습 모드·실행 중 노랑 / 실제 클릭·실행 중 빨강)
  - 보정/말풍선 보정/OCR 테스트는 드래그 창·콘솔 입력이 필요해 **새 콘솔 창**에서 CLI로 실행(`CREATE_NEW_CONSOLE`). 실행 중엔 막음. 시작 때 config를 다시 읽어 다른 창의 보정 반영
  - 왼쪽: 선물 대상(추가/삭제 즉시 config 저장) · 다음 선물(이름 왼쪽/오른쪽 · MM:SS 남음/준비됨 + 진행 막대 = 기다린 비율) · 통계(오늘 선물 수(연습이면 dry_run 수) · 오늘 채팅 수)
  - 오른쪽 탭: 판단 로그(보냄 초록/대상 아님·효과 없음·late 빨강/불명 회색/채팅 파랑, 2000줄 넘으면 앞부분 삭제) · 채팅 기록(날짜/화자 콤보, 검색어 즉시 필터, MD로 내보내기 = 현재 필터 결과)
  - 실제 클릭은 dry run 해제 후 시작 시 확인창에서 '예'
- `bongo.py`: 인자 없음(=exe 더블클릭) → 콘솔 숨기고 제어 패널. 기존 번호 메뉴는 `menu`
- 실화면 검증 중 고친 것: (1) ttk 버튼 state가 Tcl 객체라 `== "normal"` 비교가 항상 거짓 → 정지가 UI에 반영 안 됨 → `str()` (2) 이름 확정 전 아이콘이 `unmatched`로 6줄 찍힘 → `owner_of`가 미확정 주인도 반환, 엔진은 다음 tick까지 조용히 대기, 말풍선도 화자 확정까지 대기
- 테스트(`tests/test_gui.py`, 숨긴 실제 Tk 창): 대상 추가/삭제 저장, 보정 없으면 시작 거부, 실제 클릭 확인 거절 시 시작 안 함, 연습 실행 4초 → dry_run 4줄·클릭 0·카운트다운 4줄(1700~1800초)·"선물 4 (연습)"·정지 후 "멈춤", 채팅 탭 필터+내보내기
- pytest: fd 캡처에서 Tk 초기화 간헐 실패(`couldn't read file menu.tcl`, 파일 존재, pytest 밖 40회·App 15회 무실패, `--capture=sys` 8/8 통과) → `pytest.ini` `--capture=sys`. 정리 시 작업 스레드 join + 메인 스레드 gc
- `mss.mss` 폐기 예정 경고 → `mss.MSS`
- 스크린샷: `docs/html/shots/gui_log_tab.png`, `gui_chat_tab.png` (가짜 엔진+가상 화면)

## 9. 마무리 (2026-10-12)
- 최종 exe 130MB, 깨끗한 폴더에서: 더블클릭 → 3초 후 제어 패널 'Bongo Cat 헬퍼', `selftest` 통과, `menu` 8번(채팅) 정상. 전체 테스트 106개 통과
- 🔒 사용자 실제 게임 확인 (순서): ① 선물 아이콘 떠 있을 때 [보정] ② 말풍선 떠 있을 때 [말풍선 보정] ③ [OCR 테스트]로 아이콘 점수·주인·말풍선 ④ 연습 모드 시작 → 대상만 dry_run ⑤ dry run 끄고 실제 1회 → 선물 전송·확인 팝업 유무 ⑥ 30분 뒤 재생성 (late 경고 여부)

## 10. Codex 코드 리뷰 1차 (2026-10-12)
- 도구: `D:\BongoAutoCat\ask-codex.ps1` (Codex CLI, ChatGPT 로그인, 읽기 전용 샌드박스, 최종 답만 stdout). 원문: `docs/md/codex_review_1.md`
- 첫 실행은 종료코드 1·빈 답 (stderr 버려서 원인 미상). 따옴표 가설은 실험으로 기각. 같은 요청 재실행은 정상
- 14건 모두 코드와 대조해 **유효** 판정, 각각 재현 테스트(`tests/test_review_fixes.py`, 수정 전 13/13 실패) 작성 후 수정

| # | 지적 | 판정·수정 |
|---|---|---|
| 1 | 같은 자리 다른 고양이가 이름 상속 | 유효. 픽셀 서명으로 구분 시도 → 실측상 불가(애니 가림 0.09~0.15 > 다른 이름 0.04~0.07). **선물 직전 이름표 재판독**(≥0.97 같은 이름만), 다른 이름이면 미확정으로 리셋 (`CatRegistry.reverify`) |
| 2 | 사라진 이름표가 정지 화면에서 영구 생존 | 유효(135~138행). `missing` 상태: 스캔했는데 없으면 missing, 변화 없는 프레임이 살려주지 않음 → TTL 후 삭제. missing은 주인 후보(가림 대비)지만 선물 대상 아님 |
| 3 | 영역 경계에 잘린 이름표 고양이의 아이콘이 대상에 귀속 | 유효. **부분 완화**: `max_dist` 60→30. 잘린 이름표를 경쟁자로 넣는 완전한 해결은 미적용 (보정 시 감지 영역을 넉넉히) |
| 4 | 한 캡처로 여러 번 클릭, 옛 좌표 | 유효. **한 tick에 클릭 1번**, 클릭 직전 새 캡처로 아이콘 재확인, 다음 tick 전체 재검색 |
| 5 | 실행 중 대상 편집이 엔진에 반영 안 됨 | 유효. `Engine.targets`를 cfg에서 매번 읽음 |
| 6 | 커서 이동 실패 시 엉뚱한 곳 클릭 | 유효. `GetCursorPos`/`SetCursorPos` 반환값+이동 후 위치 확인, 실패 시 클릭 안 하고 예외 |
| 7 | tick이 길면 F12 검사 생략 | 유효. 매 주기 시작 + 클릭 직전 `should_stop` 검사 (GUI·CLI) |
| 8 | 고양이 이동/가림에도 clicked_ok | 유효. 확인 시 같은 고양이(id)가 같은 자리(±8px)에 확정 상태여야 함, 아니면 `clicked_unverified`(타이머 없음) |
| 9 | 연습 기록이 실제 모드 선물을 30분 막음 | 유효. 실제 모드는 `clicked_ok`만 복원 |
| 10 | UI가 타이머 순회 중 작업 스레드가 키 추가 → UI 갱신 멈춤 | 유효(실제 RuntimeError 재현). `upcoming`이 복사본 순회 |
| 11 | 종료 시 작업 스레드 안 기다림 | 유효. `Runner.join()` 후 DB/창 닫기 |
| 12 | 템플릿 없어도 조용히 0건 | 유효. `load_templates`가 없음/깨짐에 예외, GUI 시작 전·CLI에서 안내 |
| 13 | 0.5초마다 오늘 채팅 전체 조회 | 유효. `Store.count_chat` |
| 14 | 안 쓰는 `idle_interval_sec`, `tag_edge` | 유효. 삭제 |

- 테스트로 드러난 추가 수정: 클릭 1번/tick 이후 같은 고양이 다른 쪽 아이콘이 최대 5초 늦어짐 → 클릭 후 다음 tick 전체 재검색
- 결과: 테스트 120개 통과(2회), exe 재빌드·깨끗한 폴더 셀프 테스트·제어 패널 실행 확인

## 11. Codex 코드 리뷰 2차 (2026-10-13)
- 원문: `docs/md/codex_review_2.md`. 1차 14건 판정: verified 7 (2, 6, 9, 10, 12, 13, 14) / incomplete 7 (1, 3, 4, 5, 7, 8, 11) / wrong 0. 새 지적 B1~B8 — 전부 코드 대조로 유효 확인, `tests/test_review2.py` (수정 전 10/10 실패) 후 수정
- 첫 실행 실패 원인: 새 저장소에 `logs/`가 없어 stderr 리다이렉트가 실패(리뷰 미실행). 폴더 생성 후 재실행
- CLAUDE.md의 Codex 런처 경로가 옛 폴더(`D:\BongoAutoCat\ask-codex.ps1`, `-C $PSScriptRoot` = 옛 폴더를 리뷰)였음 → `D:\BongoCatAutoGift\ask-codex.ps1`로 수정

| # | 지적 | 수정 |
|---|---|---|
| B1 | 재판독이 옛 프레임 기준, 새 캡처는 아이콘만 확인 | `Engine._click`: 새 캡처에서 아이콘 다시 찾기 → **그 프레임으로 이름 재판독** → 그 프레임에서 찾은 중심을 클릭 |
| B2 | 영역 밖으로 잘린 이름표 고양이의 아이콘 귀속 (1차 3번 미해결) | `engine.owner_may_be_cut_off`: 아이콘의 가능한 주인 이름표(아이콘-오프셋 ± max_dist, 긴 이름 이름표 크기 x1.5)가 영역 안에 다 안 들어가면 `edge_unsafe`로 거부. 실제 이름표(105x24) 기준 고양이 좌우 ~100px, 위아래 ~45px 여유 필요 → setup 안내 문구, test-ocr 표시, GUI 빨간 로그 |
| B3 | tick 중 대상 삭제해도 클릭 | 클릭 직전 `self.targets`(실시간) 재확인 |
| B4 | 정지 검사가 클릭보다 이름 / CLI는 F12를 떼면 재개 | 정지 검사를 재판독 뒤·클릭 직전으로 이동 + `Clicker.click(abort=)`로 DOWN 직전에도 검사. CLI `stop_latch` (한 번 누르면 계속 정지) |
| B5 | 성공 판정·채팅 화자가 캐시 이름 사용 | 성공 판정 전 이름 재판독(다르면 `clicked_unverified`), 채팅 기록 전 화자 재판독(다르면 보류) |
| B6 | join 시간 초과 후에도 DB 닫음 | 작업 스레드가 아직 살아 있으면 DB를 닫지 않음(프로세스 종료에 맡김) |
| B7 | 스캔 영역 경계에 걸린 이름표가 missing으로 오판 | 이름표 **전체**가 스캔 영역 안일 때만 "없음" 판정 |
| B8 | 커서 확인 후 20ms 사이 사용자가 마우스 이동 | DOWN 직전 커서 위치 재확인, 다르면 `ClickAborted`(클릭 안 함, 엔진은 `click_aborted` 기록 후 계속) |

- 테스트 변경: 엔진 가상 화면 높이 420→470 (B2 규칙상 맨 아래 고양이에 여유 필요). B5 채팅 테스트가 settle 시간을 안 기다려 아무것도 검사하지 않던 것 수정
- 결과: 테스트 132개 통과(2회)

## 배포: exe [사용자 요구 2026-10-12]
- `bongocat_helper/BongoHelper.spec` → `.venv\Scripts\pyinstaller BongoHelper.spec --noconfirm` → `dist/BongoHelper.exe` (단일 파일, 콘솔, 약 126MB). 사용자용 사본: `D:\BongoAutoCat\release\BongoHelper.exe`
- OCR 모델은 exe 안에 포함(`sys._MEIPASS/models`), 다운로드 불필요. `config.json`/`templates/`/`logs/`는 **exe 옆**에 생성 (`config.BASE_DIR`가 frozen이면 exe 폴더, `RESOURCE_DIR`=번들)
- 더블클릭 = 번호 메뉴(보정/캡처 테스트/셀프 테스트), 끝나면 Enter 대기. 인자 주면 기존 CLI 그대로
- `selftest`: 모델 로딩 + 한글 OCR 4건 + 아이콘 감지. 깨끗한 폴더에서 exe 검증 완료(통과, 첫 실행 약 6초: 단일 파일 압축 해제 + 모델 로딩)
- 코드 바꾼 뒤엔 다시 빌드하고 release로 복사할 것. 단계가 추가될 때마다 메뉴(`bongo.MENU`)에 항목 추가

---

## 결정 기록
- 이름 일치는 정확히 일치만 (퍼지 금지) — 오발송 < 누락
- 처음엔 항상 `dry_run: true`
- GUI는 마지막 단계(콘솔로 검증 후 씌움) — 사용자가 다르게 지시하면 갱신
- OCR은 RapidOCR 한국어 인식 전용 (Windows OCR은 짧은 이름 정확도 부족) (2026-10-12)
- 이름 확정 = 신뢰도 ≥0.97 동일 판독 2회, onnxruntime 스레드 1개 (실제 화면 근거, 2026-10-12)
- 아이콘 템플릿 축소 배율 자동(최소 20px) — 실제 작은 템플릿이 0.5배에서 매칭 실패 (2026-10-12)
- 배포는 PyInstaller 단일 exe, 사용자 데이터는 exe 옆 (2026-10-12)
- 그림 생성은 Codex ChatGPT OAuth 사용, API 키 추가 안 함
- 선물 후 30분 재생성 → 이름·아이콘별 카운트다운, 대기 중엔 검사 생략으로 자원 절약 (2026-10-12)
- 채팅: SQLite 자동 저장 + 패널 열람 + 요청 시 MD 내보내기 (2026-10-12)
- 선물 아이콘은 고양이당 좌 100 / 우 1000 → 이름표 기준 종류별 2D 오프셋으로 주인 판별 (2026-10-12)
- 고양이 x·y 위치 무작위(높이 같을 수도 다를 수도) → 띠 방식 폐기, 이름표 앵커 + 2D 상대 오프셋 + 고양이 목록 캐시 + 변화 타일만 처리 (2026-10-12)
