from datetime import datetime

import pytest

from app_courriel import db, notify
from app_courriel.__main__ import main
from tests.fakes import FakeNtfy


def test_schema_has_four_tables():
    conn = db.open_db(":memory:")
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert names == {"state", "messages", "blocked_senders", "known_contacts"}


def test_state_roundtrip():
    conn = db.open_db(":memory:")
    assert db.get_state(conn, "k", "x") == "x"
    db.set_state(conn, "k", "1")
    db.set_state(conn, "k", "2")
    assert db.get_state(conn, "k") == "2"


@pytest.mark.parametrize("hour,quiet", [(6, True), (7, False), (21, False), (22, True), (23, True), (0, True)])
def test_quiet_hours(hour, quiet):
    assert notify.is_quiet(datetime(2026, 11, 1, hour, 30)) is quiet


def test_send_posts_to_topic():
    fake = FakeNtfy()
    notify.send("sujet-test", "Bonjour é", title="Titre", post=fake)
    url, body, headers = fake.sent[0]
    assert url == "https://ntfy.sh/sujet-test"
    assert body == "Bonjour é"
    assert headers["Title"] == "Titre".encode()


def test_main_dispatch(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main([]) == 0
    assert (tmp_path / "data" / "etat.db").exists()
    assert main(["menage"]) == 1
    assert main(["bidon"]) == 2
