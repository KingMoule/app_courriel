"""Faux services en mémoire : aucun réseau, aucune vraie donnée."""

from datetime import datetime


class FakeMail:
    """Même interface que gmail.py / graph.py (duck typing). `received_at` : ISO 8601 avec fuseau."""

    def __init__(self, inbox=None, junk=None, fail=False, sent=None, threads=None):
        # sent : [{"id", "thread_id", "to": [adresses], "subject", "sent_at"}]
        # threads : {thread_id: [{"from_me": bool, "date": ISO 8601}]}
        self.sent = list(sent or [])
        self.threads = dict(threads or {})
        self.inbox = list(inbox or [])
        self.junk = list(junk or [])
        self.fail = fail
        self.moved = []

    def list_inbox(self, since):
        if self.fail:
            raise ConnectionError("compte inaccessible")
        return [m for m in self.inbox if datetime.fromisoformat(m["received_at"]) >= since]

    def list_sent(self, since):
        return [m for m in self.sent if datetime.fromisoformat(m["sent_at"]) >= since]

    def get_thread(self, thread_id):
        return list(self.threads.get(thread_id, []))

    def list_junk(self):
        return [m["id"] for m in self.junk]

    def get_sender(self, message_id):
        return next(m["sender"] for m in self.junk if m["id"] == message_id)

    def in_inbox(self, message_id):
        return any(m["id"] == message_id for m in self.inbox)

    def move_to_junk(self, message_id):
        m = next(m for m in self.inbox if m["id"] == message_id)
        self.inbox.remove(m)
        self.junk.append(m)
        self.moved.append(message_id)


class FakeClaude:
    """Renvoie des classes préparées, par expéditeur ; `normal` par défaut."""

    def __init__(self, classes=None):
        self.classes = classes or {}
        self.calls = 0

    def classify(self, sender, subject, snippet):
        self.calls += 1
        return {"classe": self.classes.get(sender, "normal"), "resume": subject}


class FakeNtfy:
    """Se passe à `notify.send(post=...)`."""

    def __init__(self):
        self.sent = []

    def __call__(self, url, data, headers, timeout):
        self.sent.append((url, data.decode("utf-8"), headers))
