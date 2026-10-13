정적 코드 검토 결과입니다. 파일은 수정하지 않았습니다. 재현 스크립트는 `.venv`가 참조하는 Python 실행 파일을 찾지 못해 실행하지 못했습니다.

1. **high — [cats.py:78](/D:/BongoAutoCat/bongocat_helper/cats.py:78)**: 위치가 가깝거나 새 박스 중심이 기존 박스 안에 있으면 같은 고양이로 간주합니다. 대상 A가 떠난 자리에 비대상 B가 나타나면 A의 확정 이름을 그대로 사용하며, 확정 후에는 OCR도 하지 않습니다(125행).
   **수정:** 이름표 내부의 내용 변경 시 이름·투표를 초기화하고 다시 두 번 확인하세요. 겹친다는 이유만으로 신원을 계승하지 마세요.

2. **high — [cats.py:135](/D:/BongoAutoCat/bongocat_helper/cats.py:135)**: 사라진 태그를 한 번 스캔해도 TTL 전에 화면이 정지하면, 이후 `scanned=[]` 호출이 `last_seen`을 계속 갱신합니다. 사라진 대상이 영구적으로 소유권 후보에 남아 주변 비대상 아이콘을 가져갈 수 있습니다.
   **수정:** 실제 검출 시각과 스캔 시 부재 상태를 분리하고, 부재가 확인된 태그는 즉시 클릭 후보에서 제외하세요.

3. **high — [detect.py:111](/D:/BongoAutoCat/bongocat_helper/detect.py:111), [cats.py:144](/D:/BongoAutoCat/bongocat_helper/cats.py:144)**: 잘린 태그는 후보에서 사라지지만 그 고양이의 선물은 보일 수 있습니다. 비대상 태그가 영역 아래쪽에서 잘리고 그 아이콘이 대상의 예상 위치에서 50px 떨어져 있으면, 기본 `max_dist=60` 안이므로 대상에게 귀속됩니다. 후보가 하나라 모호성 검사도 통과합니다.
   **수정:** 영역 경계의 불완전한 소유권을 명시적으로 거부하고, 클릭에 사용할 태그 전체가 현재 화면에서 확인되도록 하세요.

4. **high — [engine.py:105](/D:/BongoAutoCat/bongocat_helper/engine.py:105), [engine.py:173](/D:/BongoAutoCat/bongocat_helper/engine.py:173)**: 한 캡처로 OCR·채팅 처리와 모든 클릭을 수행합니다. 처리 중 고양이가 이동하거나 첫 클릭이 팝업을 열어도 다음 클릭은 옛 좌표로 실행됩니다.
   **수정:** 실제 클릭 직전에 새 캡처로 아이콘·소유자를 재확인하고, 클릭 후에는 기존 히트 목록을 폐기하세요.

5. **high — [engine.py:47](/D:/BongoAutoCat/bongocat_helper/engine.py:47), [gui.py:211](/D:/BongoAutoCat/bongocat_helper/gui.py:211)**: 엔진의 대상 집합은 생성 시 복사됩니다. 실행 중 GUI에서 대상을 삭제해도 엔진은 계속 그 이름에 선물을 보냅니다. 추가도 반영되지 않습니다.
   **수정:** 대상 편집을 정지 상태로 제한하는 것이 가장 작은 수정입니다.

6. **high — [clicker.py:40](/D:/BongoAutoCat/bongocat_helper/clicker.py:40)**: `SetCursorPos` 성공 여부를 확인하지 않고 DOWN/UP을 전송합니다. 커서 이동이 실패하면 기존 커서 위치를 클릭합니다.
   **수정:** 커서 조회·이동 실패 시 즉시 예외를 발생시켜 클릭을 중단하세요.

7. **high — [gui.py:83](/D:/BongoAutoCat/bongocat_helper/gui.py:83), [bongo.py:299](/D:/BongoAutoCat/bongocat_helper/bongo.py:299)**: F12는 주기 사이 대기 중에만 검사합니다. `tick()`이 주기보다 오래 걸리면 검사가 아예 생략되고, GUI 정지 요청도 진행 중인 클릭들을 막지 못합니다.
   **수정:** 매 tick 시작과 각 실제 클릭 직전에 정지 여부를 검사하세요.

8. **medium — [engine.py:96](/D:/BongoAutoCat/bongocat_helper/engine.py:96)**: 클릭 성공은 이전 좌표 주변에서 아이콘이 없어졌는지만 봅니다. 클릭이 실패했어도 고양이가 이동하거나 다른 창이 가리면 `clicked_ok`로 기록하고 30분간 차단합니다.
   **수정:** 같은 고양이의 현재 위치에서 해당 선물을 확인하고, 고양이를 찾지 못하면 성공으로 처리하지 마세요.

9. **medium — [gift_timer.py:4](/D:/BongoAutoCat/bongocat_helper/gift_timer.py:4), [engine.py:65](/D:/BongoAutoCat/bongocat_helper/engine.py:65)**: 복원 대상에 `dry_run`이 포함됩니다. 연습 후 실제 모드로 시작하면 보내지 않은 선물이 최대 30분간 쿨다운 처리됩니다.
   **수정:** 실제 모드에서는 `clicked_ok` 기록만 복원하세요.

10. **medium — [gift_timer.py:26](/D:/BongoAutoCat/bongocat_helper/gift_timer.py:26), [gui.py:301](/D:/BongoAutoCat/bongocat_helper/gui.py:301)**: UI가 타이머 딕셔너리를 순회하는 동안 worker가 새 키를 추가할 수 있습니다. `RuntimeError`가 발생하면 `_tick_ui()` 끝의 `after()`가 실행되지 않아 UI 갱신이 멈춥니다.
    **수정:** worker가 큐로 타이머 스냅샷을 전달하도록 하세요.

11. **medium — [gui.py:361](/D:/BongoAutoCat/bongocat_helper/gui.py:361)**: 종료 시 worker를 기다리지 않고 DB와 Tk를 닫습니다. 진행 중인 tick이 닫힌 DB에 접근하거나 종료 요청 이후에도 클릭할 수 있습니다. 테스트 정리에는 `join()`이 있지만 실제 종료에는 없습니다.
    **수정:** 정지 요청 후 worker 종료를 확인한 다음 DB와 Tk를 닫으세요.

12. **medium — [debug.py:129](/D:/BongoAutoCat/bongocat_helper/debug.py:129), [gui.py:54](/D:/BongoAutoCat/bongocat_helper/gui.py:54)**: 템플릿 파일 누락을 조용히 건너뛰며 GUI에는 CLI의 개수 검사도 없습니다. 두 파일이 없어도 실행 중으로 표시되면서 선물 검출은 계속 0건입니다.
    **수정:** 공통 로더에서 필수 파일 존재와 이미지 디코딩 성공을 검사하고 즉시 실패시키세요.

13. **medium — [gui.py:324](/D:/BongoAutoCat/bongocat_helper/gui.py:324)**: 0.5초마다 오늘 채팅 전체를 조회·객체화해 개수를 셉니다. 채팅이 쌓일수록 UI 비용과 DB 잠금 시간이 늘어 worker의 저장도 지연됩니다.
    **수정:** 날짜별 `COUNT(*)` 조회로 바꾸세요.

14. **low — [config.py:19](/D:/BongoAutoCat/bongocat_helper/config.py:19), [calib.py:105](/D:/BongoAutoCat/bongocat_helper/calib.py:105)**: `idle_interval_sec`는 루프에서 사용하지 않고, `tag_edge`는 생성·저장하지만 검출에서 읽지 않습니다.
    **수정:** 사용하지 않는 설정과 생성 경로를 제거해 실제 동작 경로를 명확하게 하세요.
