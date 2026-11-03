from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app_courriel import graph, run

WHEN = "2026-11-04T00:00:00Z"
ISO = "2026-11-04T00:00:00+00:00"


class Response:
    def __init__(self, status_code, body):
        self.status_code, self.body = status_code, body

    def json(self):
        return self.body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise ConnectionError(self.status_code)


class FakeGraphHTTP:
    """Répond aux URL de Graph avec des données synthétiques ; garde les appels."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def request(self, method, url, timeout, headers=None, params=None, json=None):
        self.calls.append((method, url, params, json))
        assert headers["Authorization"] == "Bearer jeton-test"
        assert 'IdType="ImmutableId"' in headers["Prefer"]
        key = url.removeprefix(graph.API)
        if key not in self.routes:
            return Response(404, {})
        route = self.routes[key]
        return Response(200, route(params, json) if callable(route) else route)


def client(routes):
    http = FakeGraphHTTP(routes)
    return graph.Graph("inutilise.json", http=http, access_token="jeton-test"), http


def sender(name, address):
    return {"emailAddress": {"name": name, "address": address}}


def test_list_inbox_pages_sender_and_body():
    gr, http = client({
        "/mailFolders/inbox/messages": {"value": [
            {"id": "m1", "conversationId": "c1", "from": sender("Luc", "luc@exemple.test"), "subject": "Allô",
             "body": {"content": "Bonjour  Guillaume,\r\n\r\nété ?"}, "receivedDateTime": WHEN}],
            "@odata.nextLink": graph.API + "/page2"},
        "/page2": {"value": [
            {"id": "m2", "conversationId": "c2", "from": sender("pub@pub.test", "pub@pub.test"), "subject": None,
             "body": {"content": ""}, "bodyPreview": "Aperçu", "receivedDateTime": WHEN}]},
    })
    got = gr.list_inbox(datetime(2026, 11, 3, 1, tzinfo=timezone(timedelta(hours=-5))))
    assert got == [
        {"id": "m1", "thread_id": "c1", "sender": "Luc <luc@exemple.test>", "subject": "Allô",
         "snippet": "Bonjour Guillaume, été ?", "received_at": ISO},
        {"id": "m2", "thread_id": "c2", "sender": "pub@pub.test", "subject": "", "snippet": "Aperçu",
         "received_at": ISO},
    ]
    assert http.calls[0][2]["$filter"] == "receivedDateTime ge 2026-11-03T06:00:00Z"
    assert http.calls[1][2] is None  # le lien suivant porte déjà ses paramètres


def test_list_sent_and_thread():
    gr, http = client({
        "/mailFolders/sentitems/messages": {"value": [
            {"id": "s1", "conversationId": "c1", "subject": "Suivi", "sentDateTime": WHEN,
             "toRecipients": [sender("Luc", "Luc@Exemple.test"), sender("", "ana@exemple.test")]}]},
        "/mailFolders/sentitems": {"id": "dossier-envoyes"},
        "/messages": {"value": [
            {"parentFolderId": "dossier-inbox", "receivedDateTime": "2026-11-05T00:00:00Z"},
            {"parentFolderId": "dossier-envoyes", "receivedDateTime": WHEN},
            {"parentFolderId": "dossier-brouillons", "receivedDateTime": WHEN, "isDraft": True}]},
    })
    assert gr.list_sent(datetime(2026, 1, 1, tzinfo=timezone.utc)) == [
        {"id": "s1", "thread_id": "c1", "subject": "Suivi", "sent_at": ISO,
         "to": ["luc@exemple.test", "ana@exemple.test"]}]
    assert gr.get_thread("c1") == [{"from_me": True, "date": ISO},
                                   {"from_me": False, "date": "2026-11-05T00:00:00+00:00"}]
    assert http.calls[-1][2]["$filter"] == "conversationId eq 'c1'"


def test_junk_folder_read_only_until_a_move():
    folders = []

    def mail_folders(params, body):
        if body is None:
            return {"value": folders}
        folders.append({"id": "dossier-pourriels"})
        return folders[-1]

    gr, http = client({"/mailFolders": mail_folders, "/messages/m1/move": {"id": "m1"}})
    assert gr.list_junk() == []  # dossier absent : rien n'est créé en lecture
    assert not any(c[0] == "POST" for c in http.calls)

    gr.move_to_junk("m1")
    assert http.calls[-2][3] == {"displayName": "Pourriels-Claude"}
    assert http.calls[-1][3] == {"destinationId": "dossier-pourriels"}


def test_junk_ids_sender_and_in_inbox():
    gr, http = client({
        "/mailFolders": {"value": [{"id": "dossier-pourriels"}]},
        "/mailFolders/dossier-pourriels/messages": {"value": [{"id": "j1"}]},
        "/mailFolders/inbox": {"id": "dossier-inbox"},
        "/messages/j1": {"from": sender("", "arnaque@pub.test"), "parentFolderId": "dossier-pourriels"},
        "/messages/m1": {"parentFolderId": "dossier-inbox"},
    })
    assert gr.list_junk() == ["j1"]
    assert http.calls[0][2]["$filter"] == "displayName eq 'Pourriels-Claude'"
    assert gr.get_sender("j1") == "arnaque@pub.test"
    assert gr.in_inbox("m1") and not gr.in_inbox("j1") and not gr.in_inbox("efface")
    assert gr.get_sender("efface") == ""


def test_make_clients_picks_connected_accounts(tmp_path):
    (tmp_path / "perso_ancien.json").write_text("{}")
    clients = run.make_clients(tmp_path)
    assert list(clients) == ["perso_ancien"] and isinstance(clients["perso_ancien"], graph.Graph)


@pytest.mark.live
@pytest.mark.parametrize("name", ["perso_ancien", "travail"])
def test_live_read_only(name):
    """Lecture seule sur un vrai compte Outlook : n'affiche que des nombres, jamais de contenu."""
    token = Path(f"secrets/{name}.json")
    if not token.exists():
        pytest.skip(f"Lancer d'abord : python -m app_courriel connecter {name}")
    gr = graph.Graph(token)
    now = datetime.now(timezone.utc)
    inbox = gr.list_inbox(now - timedelta(days=1))
    sent = gr.list_sent(now - timedelta(days=7))
    junk = gr.list_junk()
    thread = gr.get_thread(sent[0]["thread_id"]) if sent else []
    print(f"\n{name} : boîte de réception (24 h) : {len(inbox)} ; envoyés (7 j) : {len(sent)} ; "
          f"Pourriels-Claude : {len(junk)} ; messages dans une conversation : {len(thread)}")
    assert all(m["received_at"] and m["thread_id"] for m in inbox)
    assert all(isinstance(m["to"], list) for m in sent)
    assert not sent or any(m["from_me"] for m in thread)
