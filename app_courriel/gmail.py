"""Client Gmail REST (compte `perso_recent`) : mêmes fonctions que `tests/fakes.FakeMail`, sans SDK Google."""

import base64
import json
from datetime import datetime, timezone
from email.utils import getaddresses
from pathlib import Path

API = "https://gmail.googleapis.com/gmail/v1/users/me"
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]  # lire, et déplacer (libellés) ; jamais supprimer
JUNK = "Pourriels-Claude"
JUNK_WINDOW = "newer_than:30d"  # on surveille les pourriels du dernier mois, pas tout l'historique du libellé


def connect(name, client_file="secrets/google_client.json"):
    """Connexion OAuth initiale : ouvre le navigateur, range le jeton dans secrets/<name>.json."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = InstalledAppFlow.from_client_secrets_file(client_file, SCOPES).run_local_server(port=0)
    path = Path("secrets") / f"{name}.json"
    path.write_text(creds.to_json(), encoding="utf-8")
    return path


def iso(message):
    return datetime.fromtimestamp(int(message["internalDate"]) / 1000, timezone.utc).isoformat()


def headers(message):
    return {h["name"].lower(): h["value"] for h in message["payload"].get("headers", [])}


def body_text(part):
    """Le premier texte brut du courriel, espaces compactés ; vide si le courriel n'est qu'en HTML."""
    data = part.get("body", {}).get("data")
    if part.get("mimeType") == "text/plain" and data:
        return " ".join(base64.urlsafe_b64decode(data + "==").decode("utf-8", "replace").split())
    for p in part.get("parts", []):
        text = body_text(p)
        if text:
            return text
    return ""


class Gmail:
    def __init__(self, token_file, http=None):
        if http is None:
            import requests

            http = requests.Session()
        self.token_file, self.http = Path(token_file), http
        self.access_token = self.junk_id = None

    def call(self, method, path, **kwargs):
        """Un appel à l'API ; None si l'objet n'existe plus (404)."""
        if self.access_token is None:  # un jeton d'accès neuf par passage
            t = json.loads(self.token_file.read_text(encoding="utf-8"))
            r = self.http.request("POST", t["token_uri"], timeout=30, data={
                "client_id": t["client_id"], "client_secret": t["client_secret"],
                "refresh_token": t["refresh_token"], "grant_type": "refresh_token"})
            r.raise_for_status()
            self.access_token = r.json()["access_token"]
        r = self.http.request(method, API + path, timeout=30,
                              headers={"Authorization": f"Bearer {self.access_token}"}, **kwargs)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def ids(self, label, query):
        params = {"labelIds": label, "q": query, "maxResults": 500}
        while True:
            page = self.call("GET", "/messages", params=params)
            yield from (m["id"] for m in page.get("messages", []))
            if "nextPageToken" not in page:
                return
            params["pageToken"] = page["nextPageToken"]

    def get(self, message_id, fmt, *names):
        return self.call("GET", f"/messages/{message_id}", params={"format": fmt, "metadataHeaders": list(names)})

    def junk_label(self, create=False):
        if self.junk_id is None:
            labels = self.call("GET", "/labels")["labels"]
            self.junk_id = next((label["id"] for label in labels if label["name"] == JUNK), None)
            if self.junk_id is None and create:
                self.junk_id = self.call("POST", "/labels", json={"name": JUNK})["id"]
        return self.junk_id

    def list_inbox(self, since):
        out = []
        for message_id in self.ids("INBOX", f"after:{int(since.timestamp())}"):
            m = self.get(message_id, "full")
            if m:
                h = headers(m)
                out.append({"id": m["id"], "thread_id": m["threadId"], "sender": h.get("from", ""),
                            "subject": h.get("subject", ""), "snippet": body_text(m["payload"]) or m.get("snippet", ""),
                            "received_at": iso(m)})
        return out

    def list_sent(self, since):
        out = []
        for message_id in self.ids("SENT", f"after:{int(since.timestamp())}"):
            m = self.get(message_id, "metadata", "To", "Subject")
            if m:
                h = headers(m)
                out.append({"id": m["id"], "thread_id": m["threadId"], "subject": h.get("subject", ""),
                            "to": [a.lower() for _, a in getaddresses([h.get("to", "")]) if a], "sent_at": iso(m)})
        return out

    def get_thread(self, thread_id):
        t = self.call("GET", f"/threads/{thread_id}", params={"format": "minimal"})
        return [{"from_me": "SENT" in m.get("labelIds", []), "date": iso(m)} for m in (t or {}).get("messages", [])]

    def list_junk(self):
        """Identifiants des courriels du libellé `Pourriels-Claude` ; rien si le libellé n'existe pas encore."""
        label = self.junk_label()
        return list(self.ids(label, JUNK_WINDOW)) if label else []

    def get_sender(self, message_id):
        m = self.get(message_id, "metadata", "From")
        return headers(m).get("from", "") if m else ""

    def in_inbox(self, message_id):
        m = self.get(message_id, "minimal")
        return bool(m) and "INBOX" in m.get("labelIds", [])

    def move_to_junk(self, message_id):
        """Déplacer, sur Gmail : ajouter le libellé et retirer INBOX. Rien n'est supprimé."""
        self.call("POST", f"/messages/{message_id}/modify",
                  json={"addLabelIds": [self.junk_label(create=True)], "removeLabelIds": ["INBOX"]})
