"""The main loop step: find gift icons, decide, click (or pretend), verify, count down.

One `tick()` = one screenshot of the detection zone. Everything is injected (grab, clicker,
clock, OCR reader) so the whole decision flow is tested on synthetic screens.
"""
import time
from dataclasses import dataclass

import capture
import cats as cats_mod
import chatlog
import clicker as clicker_mod
import detect
import gift_timer
import ocr

SIDE_LABEL = {"left": "L1000", "right": "R1000", None: "?1000"}


@dataclass
class Event:
    ts: float
    result: str          # dry_run | clicked_ok | clicked_no_change | skipped | unmatched | cooldown | late
    name: str | None = None
    side: str | None = None
    score: float = 0.0
    pos: tuple | None = None
    text: str = ""


def owner_may_be_cut_off(point, offsets, tag, max_dist, W, H):
    """A neighbor whose tag sticks out of the zone is invisible to ownership and could not
    compete for this icon. True when the icon's possible owner tag (icon - side offset,
    +- max_dist, plus a long name's tag size) does not fit inside the zone."""
    th, aspect = tag["height"], tag["aspect"] or 4
    half_w, half_h = th * aspect * 1.5 / 2 + max_dist, th / 2 + max_dist
    for off in offsets.values():
        cx, cy = point[0] - off[0], point[1] - off[1]
        if cx - half_w < 0 or cy - half_h < 0 or cx + half_w > W or cy + half_h > H:
            return True
    return False


def format_event(e):
    t = time.strftime("%H:%M:%S", time.localtime(e.ts))
    if e.result == "chat":
        return f"{t} | 채팅 | {e.name}: {e.text}"
    return f"{t} | {SIDE_LABEL.get(e.side, '?1000')} | {e.score:.2f} | {e.name or '-'} | {e.result}"


class Engine:
    VERIFY_DELAY = 1.5      # seconds after a click before checking the icon is gone
    LOG_REPEAT = 60         # same non-click decision is reported at most once a minute
    FULL_SCAN = 5           # whole-zone icon search at least this often (static icons)

    def __init__(self, cfg, grab, clicker, store, templates, read=cats_mod.read_tag,
                 clock=time.time, monitor=None, should_stop=lambda: False):
        self.cfg, self.grab, self.clicker, self.store = cfg, grab, clicker, store
        self.templates, self.clock, self.should_stop = templates, clock, should_stop
        self.monitor = monitor or {"left": 0, "top": 0}
        self.offsets = {"left": cfg["offsets"]["left"], "right": cfg["offsets"]["right"]}
        self.registry = cats_mod.CatRegistry(read, ttl=cfg["cat_ttl_sec"])
        self.change = detect.ChangeDetector()
        self.timers = gift_timer.GiftTimers(cfg["gift_cooldown_sec"])
        self.bubbles = chatlog.BubbleReader()
        self.dedup = chatlog.ChatDedup(cfg["chat_gap_sec"])
        self._verify = []          # [(key, hit, due, cat_id, tag_center)]
        self._recent_clicks = []   # [((x, y), t)]
        self._reported = {}        # (result, key) -> t
        self._last_full = -1e9
        self._named_count = 0
        self._last_icon = {}       # key -> t an icon for it was last seen
        self._late_reported = set()

    @property
    def targets(self):
        """Read live from cfg: the GUI edits the target list while the engine runs."""
        return {ocr.normalize(t) for t in self.cfg["targets"]}

    # ------------------------------------------------------------------ helpers
    def restore_timers(self):
        now = self.clock()
        results = ("clicked_ok", "dry_run") if self.cfg["dry_run"] else ("clicked_ok",)
        self.timers.restore(self.store.recent_gifts(since=now - self.timers.cooldown), now, results)

    def _report(self, events, result, key, hit, now, force=False):
        k = (result, key if key else (hit.c if hit else None))
        if not force and now - self._reported.get(k, -1e9) < self.LOG_REPEAT:
            return
        self._reported[k] = now
        name, side = key if key else (None, None)
        events.append(Event(now, result, name, side, hit.score if hit else 0.0, hit.c if hit else None))

    def _start_timer(self, key, now):
        self.timers.start(*key, now)
        self._late_reported.discard(key)

    def _click_cooling(self, pos, now):
        r, cd = 12, self.cfg["click_cooldown_sec"]
        self._recent_clicks = [(p, t) for p, t in self._recent_clicks if now - t < cd]
        return any(abs(p[0] - pos[0]) <= r and abs(p[1] - pos[1]) <= r for p, _ in self._recent_clicks)

    def _need_icon_search(self, now):
        """Skip template matching while every visible target is counting down."""
        if self.registry.pending():
            return True                          # might be a target we cannot name yet
        wake, targets = self.cfg["wake_before_sec"], self.targets
        for cat in self.registry.cats():
            if cat.name in targets:
                for side in ("left", "right"):
                    if self.timers.remaining(cat.name, side, now) <= wake:
                        return True
        return bool(self._verify)

    def _icon_still_there(self, zone, hit):
        x, y, w, h = detect.pad_rect((hit.x, hit.y, hit.w, hit.h), 8, (zone.shape[1], zone.shape[0]))
        found = detect.find_templates(zone[y:y + h, x:x + w], self.templates, self.cfg["match_threshold"])
        return bool(found)

    def _click(self, events, owner, key, hit, zone, now):
        """Decide on a fresh capture and click there. True if a click was sent."""
        fresh = self.grab()  # this tick's frame may be stale after OCR work
        if fresh.shape != zone.shape:
            return False
        x, y, w, h = detect.pad_rect((hit.x, hit.y, hit.w, hit.h), 8, (fresh.shape[1], fresh.shape[0]))
        found = detect.find_templates(fresh[y:y + h, x:x + w], self.templates, self.cfg["match_threshold"],
                                      offset=(x, y))
        if not found:
            return False
        target = min(found, key=lambda f: abs(f.c[0] - hit.c[0]) + abs(f.c[1] - hit.c[1]))
        # identity on the same frame that is clicked, target list read live, stop checked last
        if not self.registry.reverify(owner.cat, fresh, now) or owner.cat.name not in self.targets \
                or self.should_stop():
            return False
        sx, sy = capture.to_screen(self.monitor, target.c[0], target.c[1], self.cfg["region"])
        try:
            self.clicker.click(sx, sy, abort=self.should_stop)
        except clicker_mod.ClickAborted:
            self._report(events, "click_aborted", key, target, now, force=True)
            return False
        self._recent_clicks.append((target.c, now))
        self._verify.append((key, target, now + self.VERIFY_DELAY, owner.cat.id, owner.cat.box.c))
        self._last_full = -1e9  # other icons were left for the next tick: search them then
        return True

    # ------------------------------------------------------------------ one step
    def tick(self):
        now = self.clock()
        events = []
        zone = self.grab()
        H, W = zone.shape[:2]
        rects = self.change.feed(zone)

        tag_h = self.cfg["tag"]["height"]
        if rects:
            area = detect.pad_rect(detect.merge_rects(rects), 48, (W, H))
            x, y, w, h = area
            sub = zone[y:y + h, x:x + w]
            self.registry.update(detect.find_tag_boxes(sub, tag_h, offset=(x, y)), zone, now, scanned=[area])
            bubbles = detect.find_bubble_boxes(sub, tag_h, exclude=self.registry.boxes(), offset=(x, y))
            scanned = [area]
        else:
            area, bubbles, scanned = None, [], []
            self.registry.update([], zone, now, scanned=[])
        for speaker, text in self.bubbles.update(bubbles, zone, now, self.registry,
                                                 self.cfg["offsets"]["bubble"], self.cfg["max_dist"], scanned):
            if self.dedup.observe(speaker, text, now):
                self.store.add_chat(now, speaker, text)
                events.append(Event(now, "chat", speaker, text=text))

        # clicks waiting for confirmation
        still = []
        for key, hit, due, cat_id, tag_c in self._verify:
            if now < due:
                still.append((key, hit, due, cat_id, tag_c))
                continue
            cat = self.registry.get(cat_id)
            in_place = cat is not None and cat.is_named and cat.name == key[0] \
                and abs(cat.box.c[0] - tag_c[0]) <= 8 and abs(cat.box.c[1] - tag_c[1]) <= 8
            if not in_place or not self.registry.reverify(cat, zone, now):
                result = "clicked_unverified"   # cat moved/left/hidden/replaced: no timer
            elif self._icon_still_there(zone, hit):
                result = "clicked_no_change"
            else:
                result = "clicked_ok"
                self._start_timer(key, now)
            self.store.add_gift(now, key[0], key[1], result)
            self._report(events, result, key, hit, now, force=True)
        self._verify = still

        named = len(self.registry.cats())
        full = named > self._named_count or now - self._last_full >= self.FULL_SCAN
        self._named_count = named
        if not self._need_icon_search(now) or (area is None and not full):
            self._check_late(events, now)
            return events
        if full:
            area, self._last_full = (0, 0, W, H), now
        x, y, w, h = area
        hits = detect.find_templates(zone[y:y + h, x:x + w], self.templates,
                                     self.cfg["match_threshold"], offset=(x, y))

        targets = self.targets
        for hit in hits:
            owner = self.registry.owner_of(hit.c, self.offsets, self.cfg["max_dist"], self.cfg["ambiguity_px"])
            if owner is None:
                self._report(events, "unmatched", None, hit, now)
                continue
            if not owner.cat.is_named:
                continue  # name still being read; decided on a later tick
            key = (owner.cat.name, owner.side)
            self._last_icon[key] = now
            if owner.cat.name not in targets:
                self._report(events, "skipped", key, hit, now)
            elif self.timers.cooling(*key, now):
                self._report(events, "cooldown", key, hit, now)
            elif any(k == key for k, *_ in self._verify) or self._click_cooling(hit.c, now):
                continue
            elif owner_may_be_cut_off(hit.c, self.offsets, self.cfg["tag"], self.cfg["max_dist"], W, H):
                self._report(events, "edge_unsafe", key, hit, now)  # widen the detection zone
            elif self.cfg["dry_run"]:
                if not self.registry.reverify(owner.cat, zone, now):
                    continue  # not a confident read of the same name right now (or someone else)
                self._start_timer(key, now)
                self.store.add_gift(now, key[0], key[1], "dry_run")
                self._report(events, "dry_run", key, hit, now, force=True)
            elif self.should_stop():
                break
            elif self._click(events, owner, key, hit, zone, now):
                break  # one click per tick: a click may change the screen (popup, cat moves)
        self._check_late(events, now)
        return events

    def _check_late(self, events, now):
        grace = self.cfg["late_grace_sec"]
        for name, side, remaining in self.timers.upcoming(now):
            key = (name, side)
            ready = self.timers.ready_at(name, side)
            if remaining or key in self._late_reported or now < ready + grace:
                continue
            if self._last_icon.get(key, -1e9) < ready and any(c.name == name for c in self.registry.cats()):
                self._late_reported.add(key)
                self._report(events, "late", key, None, now, force=True)
