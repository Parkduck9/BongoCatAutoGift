"""Bongo Cat helper entry point.

  python bongo.py capture-test [--monitor N]   save a screenshot to logs/ to check capture
  python bongo.py setup [--monitor N] [--delay S] [--image PNG]
                                              calibrate on one cat (drag boxes), save config
  python bongo.py selftest                     check OCR model + detection work on this PC
  python bongo.py test-ocr [--image PNG] [--watch SEC]
                                              detect once with saved settings -> logs/debug.png;
                                              --watch: run the loop for SEC seconds, report ms/CPU
  python bongo.py targets [--add NAME ...] [--remove NAME ...]   edit gift targets
  python bongo.py run [--live]                  gift loop + chat log; practice mode unless --live. F12 = stop
  python bongo.py setup --bubble                calibrate where chat bubbles sit (speaker detection)
  python bongo.py chat [show|export] [--date D] [--speaker S] [--search W]
                                              chat log from data/bongo.db; export -> exports/*.md
  python bongo.py menu                         numbered console menu
  (no arguments = control panel window; this is what double-clicking the .exe opens)
  (test-ocr / run / chat / gui come in later steps)
"""
import argparse
import sys
import time

import capture
import config

LOG_DIR = config.BASE_DIR / "logs"


def cmd_capture_test(args, cfg):
    import cv2

    cap = capture.Capturer()
    try:
        for i, m in enumerate(cap.monitors()[1:], start=1):
            print(f"monitor {i}: {m['width']}x{m['height']} at ({m['left']}, {m['top']})")
        index = args.monitor or cfg["monitor"]
        t0 = time.perf_counter()
        frame = cap.grab(index)
        ms = (time.perf_counter() - t0) * 1000
    finally:
        cap.close()
    LOG_DIR.mkdir(exist_ok=True)
    out = LOG_DIR / "capture_test.png"
    cv2.imwrite(str(out), frame)
    print(f"captured monitor {index}: {frame.shape[1]}x{frame.shape[0]} in {ms:.1f} ms -> {out}")


def _imread(path):
    import cv2
    import numpy as np

    img = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)  # unicode-safe
    if img is None:
        raise SystemExit(f"이미지를 열 수 없습니다: {path}")
    return img


def _pick_monitor(cap, default):
    mons = cap.monitors()[1:]
    for i, m in enumerate(mons, start=1):
        mark = " (현재 설정)" if i == default else ""
        print(f"  {i}: {m['width']}x{m['height']} at ({m['left']}, {m['top']}){mark}")
    answer = input(f"게임이 있는 모니터 번호 [{default}]: ").strip()
    return int(answer) if answer else default


def cmd_setup(args, cfg):
    import cv2

    import calib

    if args.bubble and not cfg["region"][2]:
        print("먼저 기본 보정(setup)을 해 주세요. 말풍선 보정은 그 다음입니다.")
        return 1
    if args.image:
        frame, monitor = _imread(args.image), args.monitor or cfg["monitor"]
    else:
        cap = capture.Capturer()
        try:
            monitor = cfg["monitor"] if args.bubble else (args.monitor or _pick_monitor(cap, cfg["monitor"]))
            print("말풍선이 떠 있는 상태로 두세요." if args.bubble else "선물 아이콘이 떠 있는 상태로 두세요.")
            for left in range(args.delay, 0, -1):
                print(f"  {left}초 후 캡처...")
                time.sleep(1)
            frame = cap.grab(monitor)
        finally:
            cap.close()
    LOG_DIR.mkdir(exist_ok=True)
    cv2.imwrite(str(LOG_DIR / "setup_frame.png"), frame)

    if args.bubble:
        while True:
            rects = calib.select_rects(frame, steps=calib.BUBBLE_STEPS, view_rect=cfg["region"])
            try:
                cfg["offsets"]["bubble"] = calib.compute_bubble_offset(frame, rects)
                break
            except calib.SetupError as e:
                print(f"오류: {e}: 다시 지정합니다.")
        config.save(cfg)
        print(f"말풍선 위치 저장: 이름표 기준 {cfg['offsets']['bubble']}")
        return 0

    while True:
        rects = calib.select_rects(frame)
        try:
            res = calib.compute(frame, rects)
            break
        except calib.SetupError as e:
            print(f"오류: {e}: 처음부터 다시 지정합니다.")

    print("새 설정으로 감지해 보는 중... (처음엔 OCR 모델 로딩으로 몇 초 걸립니다)")
    report = calib.verify(frame, res, threshold=cfg["match_threshold"],
                          max_dist=cfg["max_dist"], ambiguity_px=cfg["ambiguity_px"])
    cv2.imwrite(str(LOG_DIR / "setup_check.png"), report.image)
    print(f"  이름표 {report.tags}개: {', '.join(report.names) or '-'}")
    print(f"  선물 아이콘 {report.icons}개 중 주인 판별 {report.owned}개")
    print(f"  오프셋 왼쪽 {res.offsets['left']} / 오른쪽 {res.offsets['right']} / 이름표 높이 {res.tag['height']}px")
    print(f"  확인 이미지: {LOG_DIR / 'setup_check.png'}")
    calib.show(report.image)
    if input("이 설정을 저장할까요? [Y/n]: ").strip().lower() in ("", "y", "yes", "ㅛ"):
        calib.apply(cfg, res, monitor, config.BASE_DIR / "templates")
        config.save(cfg)
        print(f"저장했습니다: {config.CONFIG_PATH}")
    else:
        print("저장하지 않았습니다.")


def cmd_selftest(args, cfg):
    """Render Korean names and a fake scene, run OCR + detection on them."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    import detect
    import ocr

    font_path = r"C:\Windows\Fonts\malgun.ttf"
    font = ImageFont.truetype(font_path, 20)
    ok = True
    t0 = time.perf_counter()
    ocr.ensure_ready()
    print(f"OCR 모델 로딩: {(time.perf_counter() - t0) * 1000:.0f} ms ({ocr.MODEL_DIR})")
    for name in ["리네", "철수", "민지", "야옹 야옹"]:
        img = Image.new("RGB", (40 + 22 * len(name), 40), "white")
        ImageDraw.Draw(img).text((20, 6), name, fill="black", font=font)
        t0 = time.perf_counter()
        got = " ".join(l.text for l in ocr.read_lines(np.array(img)[:, :, ::-1].copy()))
        good = ocr.normalize(got) == ocr.normalize(name)
        ok &= good
        print(f"  OCR {'OK ' if good else 'FAIL'} {name!r} -> {got!r} ({(time.perf_counter() - t0) * 1000:.0f} ms)")
    canvas = np.full((200, 400, 3), (200, 120, 40), np.uint8)
    icon = np.full((40, 40, 3), (40, 170, 240), np.uint8)
    icon[17:23, :] = (40, 40, 220)
    canvas[50:90, 60:100] = canvas[50:90, 300:340] = icon
    hits = detect.find_templates(canvas, [icon], 0.85)
    good = len(hits) == 2
    ok &= good
    print(f"  아이콘 감지 {'OK ' if good else 'FAIL'}: {len(hits)}/2")
    print("셀프 테스트 통과" if ok else "셀프 테스트 실패: 위 FAIL 항목을 알려 주세요")
    return 0 if ok else 1


def _zone_grabber(cfg):
    cap = capture.Capturer()
    region = cfg["region"]
    return cap, (lambda: cap.grab(cfg["monitor"], region))


def cmd_test_ocr(args, cfg):
    import cv2

    import debug

    if not cfg["region"][2] or not cfg["tag"]["height"]:
        print("보정(setup)이 아직 저장되지 않았습니다. 먼저 보정을 해 주세요.")
        return 1
    try:
        templates = debug.load_templates(cfg, config.BASE_DIR)
    except (FileNotFoundError, ValueError) as e:
        print(e)
        return 1
    if args.image:
        x, y, w, h = cfg["region"]
        zone = _imread(args.image)[y:y + h, x:x + w]
    else:
        cap, grab = _zone_grabber(cfg)
        zone = grab()
    print("감지 중... (처음엔 OCR 모델 로딩으로 몇 초 걸립니다)")
    a = debug.analyze(zone, cfg["tag"]["height"], templates, cfg["offsets"], cfg["match_threshold"],
                      cfg["max_dist"], cfg["ambiguity_px"], cfg["targets"])
    targets = {debug.ocr.normalize(t) for t in cfg["targets"]}
    print(f"고양이(이름표) {len(a.cats)}마리:")
    for c in a.cats:
        mark = "대상" if c.name in targets else "대상 아님"
        print(f"  {c.name}  신뢰도 {c.score:.2f}  위치 {c.box.c}  [{mark}]")
    if a.ignored:
        print(f"이름이 아닌 박스 {len(a.ignored)}개 (숫자칸 등) 무시")
    if a.pending:
        print(f"확실히 못 읽은 이름표 {len(a.pending)}개 (애니메이션이 겹쳤을 수 있음, 실행 중엔 다음 프레임에서 다시 읽음)")
    print(f"선물 아이콘 {len(a.hits)}개:")
    for h in a.hits:
        side = {"left": "왼쪽", "right": "오른쪽"}.get(h.side, "?")
        who = f"{h.name} {side} (거리 {h.dist:.0f}px)" if h.name else "주인 불명 -> 보내지 않음"
        print(f"  점수 {h.hit.score:.2f}  위치 {h.hit.c}  -> {who}")
    t = a.timings
    if a.bubbles:
        print(f"말풍선 {len(a.bubbles)}개:")
        for b, speaker, text in a.bubbles:
            print(f"  {speaker}: {text or '(못 읽음)'}")
    if not cfg["offsets"]["bubble"]:
        print("  (말풍선 위치 미보정: 화자를 알려면 말풍선이 떠 있을 때 메뉴의 '말풍선 보정')")
    print(f"시간: 이름표 {t['tags_ms']:.1f}ms · 이름 읽기 {t['ocr_ms']:.0f}ms · 아이콘 {t['icons_ms']:.1f}ms"
          f" · 말풍선 {t['chat_ms']:.0f}ms")
    LOG_DIR.mkdir(exist_ok=True)
    out = LOG_DIR / "debug.png"
    cv2.imwrite(str(out), a.image)
    print(f"그림 저장: {out}")

    if args.watch and not args.image:
        print(f"{args.watch}초 동안 실제 루프로 측정합니다...")
        stats = debug.watch(grab, cfg, templates, args.watch)
        print(f"  {stats['ticks']}회 · 화면 변화 {stats['dirty_ticks']}회 · OCR {stats['ocr_calls']}회")
        print(f"  1회 평균 {stats['avg_ms']:.1f}ms / 최대 {stats['max_ms']:.1f}ms · CPU {stats['cpu_pct']:.1f}%")
        print(f"  인식된 고양이: {', '.join(stats['cats']) or '-'}")
    return 0


def _fmt_left(sec):
    return "준비됨" if sec <= 0 else f"{sec // 60:02d}:{sec % 60:02d} 남음"


def cmd_targets(args, cfg):
    targets = list(cfg["targets"])
    interactive = not (args.add or args.remove)
    if interactive:
        print("현재 선물 대상:", ", ".join(targets) or "(없음)")
        add = input("추가할 이름 (쉼표로 구분, 없으면 Enter): ")
        remove = input("뺄 이름 (쉼표로 구분, 없으면 Enter): ")
        args.add = [n.strip() for n in add.split(",") if n.strip()]
        args.remove = [n.strip() for n in remove.split(",") if n.strip()]
    for n in args.add or []:
        if n not in targets:
            targets.append(n)
    targets = [t for t in targets if t not in set(args.remove or [])]
    cfg["targets"] = targets
    config.save(cfg)
    print("저장했습니다. 선물 대상:", ", ".join(targets) or "(없음)")
    print("이름은 게임 이름표와 글자 하나까지 똑같아야 합니다 (띄어쓰기는 무시).")
    return 0


def cmd_run(args, cfg):
    import datetime

    import clicker
    import debug
    import engine
    import store as store_mod

    if not cfg["region"][2] or not cfg["tag"]["height"]:
        print("보정(setup)이 아직 저장되지 않았습니다. 먼저 보정을 해 주세요.")
        return 1
    if not cfg["targets"]:
        print("선물 대상이 없습니다. 먼저 선물 대상을 추가해 주세요 (targets).")
        return 1
    try:
        templates = debug.load_templates(cfg, config.BASE_DIR)
    except (FileNotFoundError, ValueError) as e:
        print(e)
        return 1
    cfg["dry_run"] = not args.live
    if args.live:
        print("실제로 마우스를 클릭해서 선물을 보냅니다. 대상:", ", ".join(cfg["targets"]))
        if input("계속하려면 yes 를 입력하세요: ").strip().lower() != "yes":
            print("취소했습니다.")
            return 1

    cap = capture.Capturer()
    mon = cap.monitor(cfg["monitor"])
    db = store_mod.Store(config.BASE_DIR / "data" / "bongo.db")
    eng = engine.Engine(cfg, lambda: cap.grab(cfg["monitor"], cfg["region"]), clicker.Clicker(), db,
                        templates, monitor=mon, should_stop=clicker.stop_pressed)
    eng.restore_timers()
    print("OCR 모델 로딩 중...")
    debug.ocr.ensure_ready()
    LOG_DIR.mkdir(exist_ok=True)
    mode = "연습 모드(클릭 안 함)" if cfg["dry_run"] else "실제 클릭"
    print(f"시작: {mode} · 대상 {', '.join(cfg['targets'])} · 멈추려면 F12 (또는 Ctrl+C)")
    last_status = 0.0
    try:
        while not clicker.stop_pressed():  # checked every cycle, even when a tick ran long
            t0 = time.time()
            for e in eng.tick():
                line = engine.format_event(e)
                print(line)
                day = datetime.date.today().isoformat()
                with open(LOG_DIR / f"actions_{day}.txt", "a", encoding="utf-8") as f:
                    print(line, file=f)
            if t0 - last_status >= 30:
                last_status = t0
                rows = [r for r in eng.timers.upcoming(t0) if r[0] in eng.targets]
                if rows:
                    print("  다음 선물: " + " · ".join(
                        f"{n} {engine.SIDE_LABEL[s]} {_fmt_left(r)}" for n, s, r in rows))
            while time.time() - t0 < cfg["interval_sec"] and not clicker.stop_pressed():
                time.sleep(0.05)
        print("멈췄습니다 (F12).")
    except KeyboardInterrupt:
        print("멈췄습니다.")
    finally:
        db.close()
        cap.close()
    return 0


def cmd_chat(args, cfg):
    import chatlog
    import store as store_mod

    db = store_mod.Store(config.BASE_DIR / "data" / "bongo.db")
    try:
        if args.action is None:  # interactive (menu)
            dates = db.chat_dates()
            if not dates:
                print("저장된 채팅이 없습니다.")
                return 0
            print("채팅이 있는 날짜:", ", ".join(dates))
            args.date = input(f"날짜 [{dates[-1]}] (전체 = all): ").strip() or dates[-1]
            if args.date == "all":
                args.date = None
            speakers = db.chat_speakers(args.date)
            print("말한 사람:", ", ".join(speakers))
            args.speaker = input("말한 사람 (전체 = Enter): ").strip() or None
            args.search = input("검색어 (없으면 Enter): ").strip() or None
        rows = db.query_chat(args.date, args.speaker, args.search)
        for ts, speaker, text in rows:
            print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))}  {speaker}: {text}")
        print(f"{len(rows)}건")
        export = args.action == "export" or (
            args.action is None and rows and input("MD 파일로 내보낼까요? [y/N]: ").strip().lower() in ("y", "yes", "ㅛ"))
        if export and rows:
            hint = " ".join(x for x in (args.speaker, args.search) if x)
            path = chatlog.export_md(rows, config.BASE_DIR / "exports", hint)
            print(f"내보냈습니다: {path}")
    finally:
        db.close()
    return 0


MENU = [
    ("setup", "보정 (게임 화면에서 고양이 1마리 드래그로 지정)"),
    ("capture-test", "화면 캡처 테스트"),
    ("test-ocr", "디버그 (저장된 보정으로 한 번 감지 + 30초 성능 측정)"),
    ("selftest", "셀프 테스트 (OCR/감지가 이 PC에서 동작하는지)"),
    ("targets", "선물 대상 편집"),
    ("run", "실행: 연습 모드 (클릭 안 하고 기록만)"),
    ("run --live", "실행: 실제 클릭 (선물 보냄)"),
    ("chat", "채팅 기록 보기 / MD로 내보내기"),
    ("setup --bubble", "말풍선 보정 (말풍선이 떠 있을 때: 화자 판별용)"),
]


def menu():
    print("Bongo Cat 헬퍼")
    for i, (_, label) in enumerate(MENU, start=1):
        print(f"  {i}. {label}")
    answer = input("번호를 입력하세요 (Enter = 종료): ").strip()
    if not answer.isdigit() or not 1 <= int(answer) <= len(MENU):
        return None
    cmd = MENU[int(answer) - 1][0]
    return [cmd, "--watch", "30"] if cmd == "test-ocr" else cmd.split()


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):  # cp949 consoles/pipes must never crash on a character
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    argv = sys.argv[1:] if argv is None else argv
    if not argv:  # double-click: control panel; the console stays hidden behind it
        import ctypes

        import gui

        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
        gui.main()
        return 0
    double_clicked = argv == ["menu"]
    if double_clicked:
        argv = menu()
        if argv is None:
            return 0
    try:
        return _run(argv)
    finally:
        if double_clicked:
            print()
            input("끝났습니다. Enter를 누르면 창이 닫힙니다.")


def _run(argv):
    capture.set_dpi_aware()
    parser = argparse.ArgumentParser(prog="bongo")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("capture-test", help="save a screenshot to logs/capture_test.png")
    p.add_argument("--monitor", type=int)
    p = sub.add_parser("setup", help="calibrate on one cat and save config")
    p.add_argument("--monitor", type=int)
    p.add_argument("--delay", type=int, default=3, help="seconds before capture")
    p.add_argument("--image", help="use a saved screenshot instead of capturing")
    p.add_argument("--bubble", action="store_true", help="only calibrate the chat bubble position")
    sub.add_parser("selftest", help="check OCR model and detection on this PC")
    p = sub.add_parser("test-ocr", help="detect once with saved settings, save logs/debug.png")
    p.add_argument("--image", help="full-monitor screenshot to use instead of capturing")
    p.add_argument("--watch", type=int, default=0, help="also run the loop for N seconds and measure")
    p = sub.add_parser("targets", help="edit gift targets")
    p.add_argument("--add", nargs="*")
    p.add_argument("--remove", nargs="*")
    p = sub.add_parser("chat", help="show chat log; export to Markdown")
    p.add_argument("action", nargs="?", choices=["show", "export"])
    p.add_argument("--date")
    p.add_argument("--speaker")
    p.add_argument("--search")
    p = sub.add_parser("run", help="gift loop (practice mode unless --live), F12 stops")
    p.add_argument("--live", action="store_true", help="really click")
    args = parser.parse_args(argv)
    cfg = config.load()
    cmds = {"capture-test": cmd_capture_test, "setup": cmd_setup, "selftest": cmd_selftest,
            "test-ocr": cmd_test_ocr, "targets": cmd_targets, "run": cmd_run, "chat": cmd_chat}
    return cmds[args.cmd](args, cfg)


if __name__ == "__main__":
    sys.exit(main())
