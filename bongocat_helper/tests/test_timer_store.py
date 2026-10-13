import gift_timer
import store


def test_timer_counts_down_per_name_and_side():
    t = gift_timer.GiftTimers(cooldown_sec=1800)
    t.start("리네", "left", now=100)
    assert t.remaining("리네", "left", now=160) == 1740
    assert t.remaining("리네", "right", now=160) == 0
    assert t.cooling("리네", "left", now=160)
    assert not t.cooling("리네", "left", now=1900)


def test_upcoming_sorted_by_remaining_and_includes_ready():
    t = gift_timer.GiftTimers(1800)
    t.start("민지", "left", now=0)
    t.start("리네", "right", now=600)
    up = t.upcoming(now=1000)
    assert [(n, s) for n, s, _ in up] == [("민지", "left"), ("리네", "right")]
    assert [r for _, _, r in up] == [800, 1400]
    assert t.upcoming(now=5000)[0][2] == 0


def test_store_roundtrip_and_timer_restore(tmp_path):
    db = store.Store(tmp_path / "bongo.db")
    db.add_gift(ts=1000, name="리네", side="left", result="clicked_ok")
    db.add_gift(ts=1500, name="리네", side="right", result="clicked_no_change")
    db.add_gift(ts=100, name="민지", side="left", result="dry_run")
    db.close()
    db = store.Store(tmp_path / "bongo.db")
    t = gift_timer.GiftTimers(1800)
    t.restore(db.recent_gifts(since=2000 - 1800), now=2000, results=("clicked_ok", "dry_run"))
    assert t.remaining("리네", "left", now=2000) == 800
    assert t.remaining("리네", "right", now=2000) == 0      # no_change does not start a timer
    assert t.remaining("민지", "left", now=2000) == 0      # older than cooldown
