"""Faux services en mémoire : aucun réseau, aucune vraie donnée."""


class FakeMail:
    """Même interface que gmail.py / graph.py (duck typing)."""

    def __init__(self, inbox=None):
        self.inbox = list(inbox or [])
        self.moved = []

    def list_inbox(self, since):
        return [m for m in self.inbox if m["received_at"] >= since]

    def move_to_junk(self, message_id):
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
