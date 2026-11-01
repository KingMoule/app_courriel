from datetime import datetime, timedelta

from app_courriel import db, run
from tests.fakes import FakeClaude, FakeMail

NOW = datetime(2026, 11, 2, 10, 0, tzinfo=run.TZ)


def mail(id, sender="Marie <marie@exemple.test>", subject="Question", minutes_ago=5):
    received = (NOW - timedelta(minutes=minutes_ago)).isoformat()
    return {"id": id, "thread_id": f"t-{id}", "sender": sender, "subject": subject,
            "snippet": "Bonjour " * 100, "received_at": received}


class Sent(list):
    def __call__(self, title, message):
        self.append((title, message))


def setup(clients, first_run=False):
    conn = db.open_db(":memory:")
    if not first_run:
        for name in clients:
            db.set_state(conn, f"last_pass:{name}", (NOW - timedelta(minutes=10)).isoformat())
    return conn


def row(conn, id):
    return conn.execute("SELECT class, summary, snippet, alerted_at, moved_by_script FROM messages WHERE id = ?",
                        (id,)).fetchone()


def test_important_alerts_once_normal_never():
    """Fonction 2 : un `important` produit exactement une alerte avec son résumé, un `normal` aucune."""
    clients = {"perso_recent": FakeMail([mail("a", "Marie <marie@exemple.test>", "Souper samedi ?"),
                                         mail("b", "Infolettre <news@exemple.test>", "Nouveautés")])}
    claude, sent = FakeClaude({"Marie <marie@exemple.test>": "important"}), Sent()
    conn = setup(clients)
    run.run_pass(conn, NOW, clients, claude.classify, sent)
    run.run_pass(conn, NOW + timedelta(minutes=10), clients, claude.classify, sent)
    assert sent == [("perso_recent : Marie <marie@exemple.test>", "Souper samedi ?\nSouper samedi ?")]
    assert row(conn, "a")[0] == "important" and row(conn, "a")[3]
    assert row(conn, "b")[:4] == ("normal", "Nouveautés", "", None)
    assert claude.calls == 2  # le second passage ne reclasse rien


def test_work_alert_says_nothing_confidential():
    clients = {"travail": FakeMail([mail("a", "Patron <patron@employeur.test>", "Contrat secret")])}
    sent = Sent()
    run.run_pass(setup(clients), NOW, clients, FakeClaude({"Patron <patron@employeur.test>": "important"}).classify, sent)
    assert sent == [("Courriel important (travail)", "Courriel important (travail)")]


def test_no_alert_at_night_first_run_or_old_mail():
    important = FakeClaude({"Marie <marie@exemple.test>": "important"}).classify
    night = NOW.replace(hour=23)
    cases = [
        ({"perso_recent": FakeMail([mail("a", minutes_ago=-13 * 60 + 5)])}, night, False),  # reçu à 22 h 55
        ({"perso_recent": FakeMail([mail("a")])}, NOW, True),  # premier lancement
        ({"perso_recent": FakeMail([mail("a", minutes_ago=90)])}, NOW, False),  # rattrapage
    ]
    for clients, now, first_run in cases:
        conn, sent = setup(clients, first_run), Sent()
        if not first_run:
            db.set_state(conn, "last_pass:perso_recent", (now - timedelta(hours=3)).isoformat())
        run.run_pass(conn, now, clients, important, sent)
        assert row(conn, "a")[0] == "important"
        assert sent == []


def test_spam_moved_and_sender_blocked_on_all_accounts():
    spam = "Promo <promo@pub.test>"
    a, b = FakeMail([mail("a", spam, "Soldes")]), FakeMail()
    clients = {"perso_recent": a, "perso_ancien": b}
    claude = FakeClaude({spam: "pourriel"})
    conn = setup(clients)
    run.run_pass(conn, NOW, clients, claude.classify, Sent())
    assert a.moved == ["a"] and row(conn, "a")[4] == 1
    assert conn.execute("SELECT address FROM blocked_senders").fetchall() == [("promo@pub.test",)]

    b.inbox.append(mail("b", spam, "Encore des soldes", minutes_ago=1))
    run.run_pass(conn, NOW + timedelta(minutes=10), clients, claude.classify, Sent())
    assert b.moved == ["b"] and claude.calls == 1  # bloqué : pas d'appel à Claude


def test_known_contact_never_moved():
    conn_clients = {"perso_recent": FakeMail([mail("a", "Luc <luc@exemple.test>")])}
    conn = setup(conn_clients)
    conn.execute("INSERT INTO known_contacts VALUES ('luc@exemple.test')")
    run.run_pass(conn, NOW, conn_clients, FakeClaude({"Luc <luc@exemple.test>": "pourriel"}).classify, Sent())
    assert conn_clients["perso_recent"].moved == [] and row(conn, "a")[0] == "normal"


def test_call_cap_newest_first():
    inbox = [mail(f"m{i:02}", f"p{i}@exemple.test", minutes_ago=i) for i in range(60)]
    clients = {"perso_recent": FakeMail(inbox)}
    claude, conn = FakeClaude(), setup(clients, first_run=True)
    run.run_pass(conn, NOW, clients, claude.classify, Sent())
    assert claude.calls == 50
    pending = [r[0] for r in conn.execute("SELECT id FROM messages WHERE class IS NULL ORDER BY id")]
    assert pending == [f"m{i}" for i in range(50, 60)]  # les 10 plus vieux attendent
    run.run_pass(conn, NOW + timedelta(minutes=10), clients, claude.classify, Sent())
    assert claude.calls == 60


def test_blocked_senders_do_not_use_the_cap():
    inbox = [mail(f"s{i:02}", "spam@pub.test") for i in range(55)] + [mail("ok", "ami@exemple.test")]
    clients = {"perso_recent": FakeMail(inbox)}
    claude, conn = FakeClaude(), setup(clients)
    conn.execute("INSERT INTO blocked_senders VALUES ('spam@pub.test', 'x')")
    run.run_pass(conn, NOW, clients, claude.classify, Sent())
    assert claude.calls == 1 and len(clients["perso_recent"].moved) == 55


def test_api_error_leaves_mail_unclassified():
    def down(*args):
        raise TimeoutError

    clients = {"perso_recent": FakeMail([mail("a")])}
    conn = setup(clients)
    run.run_pass(conn, NOW, clients, down, Sent())
    assert row(conn, "a")[0] is None and row(conn, "a")[2]  # extrait gardé pour le prochain passage
    run.run_pass(conn, NOW + timedelta(minutes=10), clients, FakeClaude().classify, Sent())
    assert row(conn, "a")[:3] == ("normal", "Question", "")


def test_broken_account_alerts_once_a_day_others_continue():
    clients = {"travail": FakeMail(fail=True), "perso_recent": FakeMail([mail("a")])}
    conn, sent = setup(clients), Sent()
    for minutes in (0, 10, 20):
        run.run_pass(conn, NOW + timedelta(minutes=minutes), clients, FakeClaude().classify, sent)
    assert sent == [("Compte travail inaccessible", "Le compte travail n'a pas pu être lu (ConnectionError).")]
    assert row(conn, "a")[0] == "normal"
    assert db.get_state(conn, "last_pass:travail") == (NOW - timedelta(minutes=10)).isoformat()
    assert db.get_state(conn, "last_pass:perso_recent") == (NOW + timedelta(minutes=20)).isoformat()
    run.run_pass(conn, NOW + timedelta(days=1), clients, FakeClaude().classify, sent)
    assert len(sent) == 2


def test_junk_folder_blocks_and_unblocks():
    spam = "Promo <promo@pub.test>"
    box = FakeMail([mail("a", spam)], junk=[mail("u", "Arnaque <arnaque@pub.test>")])
    clients = {"perso_ancien": box}
    conn = setup(clients)
    run.run_pass(conn, NOW, clients, FakeClaude({spam: "pourriel"}).classify, Sent())
    blocked = {r[0] for r in conn.execute("SELECT address FROM blocked_senders")}
    assert blocked == {"promo@pub.test", "arnaque@pub.test"}  # « u » : déplacé par moi

    m = next(m for m in box.junk if m["id"] == "a")  # je le remets dans la boîte de réception
    box.junk.remove(m)
    box.inbox.append(m)
    run.run_pass(conn, NOW + timedelta(minutes=10), clients, FakeClaude().classify, Sent())
    assert {r[0] for r in conn.execute("SELECT address FROM blocked_senders")} == {"arnaque@pub.test"}
    assert row(conn, "a")[4] == 0


def test_load_env(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("# commentaire\nAPP_TEST_A=un\nAPP_TEST_B = \"deux\"\n", encoding="utf-8")
    monkeypatch.delenv("APP_TEST_A", raising=False)
    monkeypatch.setenv("APP_TEST_B", "déjà là")
    run.load_env(env)
    assert run.os.environ["APP_TEST_A"] == "un" and run.os.environ["APP_TEST_B"] == "déjà là"
    monkeypatch.delenv("APP_TEST_A")
