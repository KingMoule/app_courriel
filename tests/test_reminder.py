from datetime import datetime, timedelta

from app_courriel import db, run
from tests.fakes import FakeMail

NOW = datetime(2026, 11, 3, 8, 0, tzinfo=run.TZ)


def ago(**delta):
    return (NOW - timedelta(**delta)).isoformat()


def item(kind, who="Marie", subject="Question", days=2, account="perso_recent"):
    return {"kind": kind, "account": account, "who": who, "subject": subject, "date": NOW - timedelta(days=days)}


def test_build_reminder_lines_and_work_account():
    text = run.build_reminder([item("reply", "Marie", "Souper", 2), item("follow_up", "luc@exemple.test", "Devis", 5),
                               item("reply", account="travail", subject="Secret", days=1)], NOW)
    assert text == ("À répondre (2)\n• Marie — Souper (2 j)\n• travail (1 j)\n\n"
                    "À relancer (1)\n• → luc@exemple.test — Devis (5 j)")
    assert "Secret" not in text


def test_build_reminder_caps_at_ten_oldest_and_empty_is_none():
    items = [item("reply", subject=f"s{i}", days=i + 1) for i in range(12)]
    lines = run.build_reminder(items, NOW).splitlines()
    assert lines[0] == "À répondre (12, les 10 plus vieux)" and len(lines) == 11
    assert lines[1].endswith("(12 j)") and lines[-1].endswith("(3 j)")  # s11 ... s2
    assert run.build_reminder([], NOW) is None


def test_reminder_lists_unanswered_and_ignores_answered():
    """Fonction 3 : exactement les `important` sans réponse et les envois sans réponse depuis 3 jours."""
    def sent(id, to, days, subject="Envoi"):
        return {"id": id, "thread_id": f"s-{id}", "to": to, "subject": subject, "sent_at": ago(days=days)}

    box = FakeMail(
        sent=[sent("a", ["luc@exemple.test"], 4, "Devis"),            # relancer
              sent("b", ["ami@exemple.test"], 4),                      # a reçu une réponse
              sent("c", ["noreply@exemple.test"], 4),                  # no-reply
              sent("d", ["x@exemple.test", "y@exemple.test"], 4),      # deux destinataires
              sent("e", ["neuf@exemple.test"], 1),                     # trop récent
              sent("f", ["vieux@exemple.test"], 15)],                  # expiré
        threads={"s-b": [{"from_me": True, "date": ago(days=4)}, {"from_me": False, "date": ago(days=1)}],
                 "t-ok": [{"from_me": False, "date": ago(days=2)}, {"from_me": True, "date": ago(days=1)}]})
    conn = db.open_db(":memory:")
    rows = [("w", "t-w", "Marie <marie@exemple.test>", "Souper ?", 2, "important"),      # à répondre
            ("ok", "t-ok", "Paul <paul@exemple.test>", "Déjà répondu", 2, "important"),  # j'ai répondu
            ("n", "t-n", "Infolettre <news@exemple.test>", "Promo", 2, "normal"),
            ("old", "t-old", "Vieux <vieux@exemple.test>", "Trop vieux", 15, "important")]
    for id, tid, sender, subject, days, cls in rows:
        conn.execute("INSERT INTO messages (account, id, thread_id, sender, subject, received_at, class)"
                     " VALUES ('perso_recent', ?, ?, ?, ?, ?, ?)",
                     (id, tid, sender, subject, run.utc_iso(NOW - timedelta(days=days)), cls))
    messages = []
    run.remind(conn, NOW, {"perso_recent": box}, lambda title, text: messages.append((title, text)))
    assert messages == [("Rappel du matin",
                         "À répondre (1)\n• Marie — Souper ? (2 j)\n\nÀ relancer (1)\n• → luc@exemple.test — Devis (4 j)")]
    contacts = {r[0] for r in conn.execute("SELECT address FROM known_contacts")}
    assert "luc@exemple.test" in contacts and "vieux@exemple.test" in contacts  # envoyés des 12 derniers mois


def test_reminder_once_a_day_after_7h_only():
    conn, messages = db.open_db(":memory:"), []
    box = FakeMail(sent=[{"id": "a", "thread_id": "s-a", "to": ["luc@exemple.test"], "subject": "Devis",
                          "sent_at": ago(days=4)}])
    send = lambda title, text: messages.append(text)
    run.remind(conn, NOW.replace(hour=6), {"x": box}, send)
    assert messages == []  # trop tôt
    run.remind(conn, NOW, {"x": box}, send)
    run.remind(conn, NOW + timedelta(minutes=10), {"x": box}, send)
    assert len(messages) == 1
    run.remind(conn, NOW + timedelta(days=1), {"x": box}, send)
    assert len(messages) == 2


def test_broken_account_does_not_block_others_nor_wipe_contacts():
    class Down(FakeMail):
        def list_sent(self, since):
            raise ConnectionError

    conn, messages = db.open_db(":memory:"), []
    conn.execute("INSERT INTO known_contacts VALUES ('garde@exemple.test')")
    ok = FakeMail(sent=[{"id": "a", "thread_id": "s-a", "to": ["luc@exemple.test"], "subject": "Devis",
                         "sent_at": ago(days=4)}])
    run.remind(conn, NOW, {"travail": Down(), "perso_recent": ok}, lambda t, m: messages.append((t, m)))
    assert [t for t, _ in messages] == ["Compte travail inaccessible", "Rappel du matin"]
    assert {r[0] for r in conn.execute("SELECT address FROM known_contacts")} == {"garde@exemple.test", "luc@exemple.test"}
