import base64
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app_courriel import gmail

MS = "1793750400000"  # 2026-11-04 00:00 UTC


def b64(text):
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


class Response:
    def __init__(self, status_code, body):
        self.status_code, self.body = status_code, body

    def json(self):
        return self.body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise ConnectionError(self.status_code)


class FakeGmailHTTP:
    """Répond aux URL de l'API Gmail avec des données synthétiques ; garde les appels."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def request(self, method, url, timeout, headers=None, params=None, json=None, data=None):
        self.calls.append((method, url, params, json, data))
        if url == "https://oauth2.googleapis.com/token":
            return Response(200, {"access_token": "jeton-test"})
        assert headers == {"Authorization": "Bearer jeton-test"}
        path = url.removeprefix(gmail.API)
        paged = (path, (params or {}).get("pageToken"))
        key = paged if paged in self.routes else path
        if key not in self.routes:
            return Response(404, {})
        route = self.routes[key]
        return Response(200, route(params, json) if callable(route) else route)


def client(tmp_path, routes):
    token = tmp_path / "perso_recent.json"
    token.write_text(json.dumps({"token_uri": "https://oauth2.googleapis.com/token", "client_id": "id-test",
                                 "client_secret": "secret-test", "refresh_token": "rafraichir-test"}))
    http = FakeGmailHTTP(routes)
    return gmail.Gmail(token, http=http), http


def message(id, thread, labels=("INBOX",), headers=(), payload=None):
    payload = payload or {"mimeType": "text/plain", "body": {}}
    payload["headers"] = [{"name": n, "value": v} for n, v in headers]
    return {"id": id, "threadId": thread, "labelIds": list(labels), "internalDate": MS,
            "snippet": "Extrait Gmail", "payload": payload}


def test_list_inbox_pages_headers_and_body(tmp_path):
    body = {"mimeType": "multipart/alternative", "parts": [
        {"mimeType": "text/html", "body": {"data": b64("<p>html</p>")}},
        {"mimeType": "text/plain", "body": {"data": b64("Bonjour  Guillaume,\n\nété ?")}}]}
    gm, http = client(tmp_path, {
        ("/messages", None): {"messages": [{"id": "m1"}], "nextPageToken": "p2"},
        ("/messages", "p2"): {"messages": [{"id": "m2"}, {"id": "efface"}]},
        "/messages/m1": message("m1", "t1", headers=[("From", "Luc <luc@exemple.test>"), ("Subject", "Allô")],
                                payload=body),
        "/messages/m2": message("m2", "t2", headers=[("From", "pub@pub.test")]),
    })
    since = datetime(2026, 11, 3, tzinfo=timezone.utc)
    got = gm.list_inbox(since)
    assert got == [
        {"id": "m1", "thread_id": "t1", "sender": "Luc <luc@exemple.test>", "subject": "Allô",
         "snippet": "Bonjour Guillaume, été ?", "received_at": "2026-11-04T00:00:00+00:00"},
        {"id": "m2", "thread_id": "t2", "sender": "pub@pub.test", "subject": "",
         "snippet": "Extrait Gmail", "received_at": "2026-11-04T00:00:00+00:00"},  # HTML seulement : extrait Gmail
    ]
    assert http.calls[1][2]["labelIds"] == "INBOX" and http.calls[1][2]["q"] == f"after:{int(since.timestamp())}"
    assert sum(c[1].endswith("/token") for c in http.calls) == 1  # un seul rafraîchissement par passage


def test_list_sent_and_thread(tmp_path):
    gm, _ = client(tmp_path, {
        "/messages": {"messages": [{"id": "s1"}]},
        "/messages/s1": message("s1", "t1", labels=["SENT"],
                                headers=[("To", "Luc <Luc@Exemple.test>, ana@exemple.test"), ("Subject", "Suivi")]),
        "/threads/t1": {"messages": [message("s1", "t1", labels=["SENT"]), message("r1", "t1")]},
    })
    sent = gm.list_sent(datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert sent == [{"id": "s1", "thread_id": "t1", "subject": "Suivi", "sent_at": "2026-11-04T00:00:00+00:00",
                     "to": ["luc@exemple.test", "ana@exemple.test"]}]
    assert gm.get_thread("t1") == [{"from_me": True, "date": "2026-11-04T00:00:00+00:00"},
                                   {"from_me": False, "date": "2026-11-04T00:00:00+00:00"}]
    assert gm.get_thread("disparu") == []


def test_junk_label_read_only_until_a_move(tmp_path):
    labels = {"labels": [{"id": "INBOX", "name": "INBOX"}]}

    def create(params, body):
        labels["labels"].append({"id": "Label_9", "name": body["name"]})
        return {"id": "Label_9"}

    gm, http = client(tmp_path, {"/labels": lambda p, j: labels if j is None else create(p, j),
                                 "/messages/m1/modify": {}})
    assert gm.list_junk() == []  # libellé absent : rien n'est créé en lecture
    assert not any(c[0] == "POST" and c[1].endswith("/labels") for c in http.calls)

    gm.move_to_junk("m1")
    assert http.calls[-1][3] == {"addLabelIds": ["Label_9"], "removeLabelIds": ["INBOX"]}
    assert labels["labels"][-1]["name"] == "Pourriels-Claude"


def test_junk_ids_sender_and_in_inbox(tmp_path):
    gm, http = client(tmp_path, {
        "/labels": {"labels": [{"id": "Label_9", "name": "Pourriels-Claude"}]},
        "/messages": {"messages": [{"id": "j1"}]},
        "/messages/j1": message("j1", "t1", labels=["Label_9"], headers=[("From", "arnaque@pub.test")]),
        "/messages/m1": message("m1", "t2"),
    })
    assert gm.list_junk() == ["j1"]
    assert http.calls[-1][2]["labelIds"] == "Label_9"
    assert gm.get_sender("j1") == "arnaque@pub.test"
    assert gm.in_inbox("m1") and not gm.in_inbox("j1") and not gm.in_inbox("efface")


@pytest.mark.live
def test_live_read_only():
    """Lecture seule sur le vrai compte `perso_recent` : n'affiche que des nombres, jamais de contenu."""
    token = Path("secrets/perso_recent.json")
    if not token.exists():
        pytest.skip("Lancer d'abord : python -m app_courriel connecter perso_recent")
    gm = gmail.Gmail(token)
    now = datetime.now(timezone.utc)
    inbox = gm.list_inbox(now - timedelta(days=1))
    sent = gm.list_sent(now - timedelta(days=7))
    junk = gm.list_junk()
    thread = gm.get_thread(sent[0]["thread_id"]) if sent else []
    print(f"\nBoîte de réception (24 h) : {len(inbox)} ; envoyés (7 j) : {len(sent)} ; "
          f"Pourriels-Claude : {len(junk)} ; messages dans une conversation : {len(thread)}")
    assert all(m["received_at"] and m["thread_id"] for m in inbox)
    assert all(isinstance(m["to"], list) for m in sent)
    assert not sent or any(m["from_me"] for m in thread)
