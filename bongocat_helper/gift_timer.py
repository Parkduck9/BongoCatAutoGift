"""Gift regeneration countdown: a gift icon comes back `cooldown_sec` after it was sent.
Keyed by (name, side) because each cat has a left and a right 1000 icon."""



class GiftTimers:
    def __init__(self, cooldown_sec=1800):
        self.cooldown = cooldown_sec
        self._ready_at = {}   # (name, side) -> time

    def start(self, name, side, now):
        self._ready_at[(name, side)] = now + self.cooldown

    def remaining(self, name, side, now):
        return max(0, round(self._ready_at.get((name, side), 0) - now))

    def cooling(self, name, side, now):
        return self.remaining(name, side, now) > 0

    def ready_at(self, name, side):
        return self._ready_at.get((name, side))

    def upcoming(self, now):
        """[(name, side, remaining_sec)] for every key ever started, soonest first.
        Called from the UI thread while the worker may add keys: iterate over a copy."""
        rows = [(n, s, max(0, round(t - now))) for (n, s), t in dict(self._ready_at).items()]
        return sorted(rows, key=lambda r: (r[2], r[0], r[1]))

    def restore(self, rows, now, results):
        """rows: [(ts, name, side, result)] from the store, oldest first. Only `results` start a
        timer: a live run must not be blocked by practice-mode (dry_run) records."""
        for ts, name, side, result in rows:
            if result in results and ts + self.cooldown > now:
                self._ready_at[(name, side)] = ts + self.cooldown
