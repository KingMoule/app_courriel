"""Client Microsoft Graph (comptes `perso_ancien` et `travail`) : mêmes fonctions que `gmail.py`, sans SDK Microsoft.

Identifiants immuables (`Prefer: IdType="ImmutableId"`) : un courriel garde son identifiant quand on le déplace.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

API = "https://graph.microsoft.com/v1.0/me"
SCOPES = ["Mail.ReadWrite"]  # lire, et déplacer ; jamais supprimer. MSAL ajoute offline_access.
AUTHORITY = {"perso_ancien": "https://login.microsoftonline.com/consumers",
             "travail": "https://login.microsoftonline.com/organizations"}
JUNK = "Pourriels-Claude"
JUNK_WINDOW = timedelta(days=30)  # on surveille les pourriels du dernier mois, pas tout l'historique du dossier


def connect(name, client_id):
    """Connexion OAuth initiale : ouvre le navigateur, range le jeton dans secrets/<name>.json."""
    import msal

    cache = msal.SerializableTokenCache()
    app = msal.PublicClientApplication(client_id, authority=AUTHORITY[name], token_cache=cache)
    result = app.acquire_token_interactive(SCOPES)
    if "access_token" not in result:
        raise RuntimeError(f"{result.get('error')} : {result.get('error_description')}")
    path = Path("secrets") / f"{name}.json"
    path.write_text(json.dumps({"client_id": client_id, "authority": AUTHORITY[name], "cache": cache.serialize()}),
                    encoding="utf-8")
    return path


def gmt(value):
    """`2026-11-04T00:00:00Z` -> ISO avec fuseau, comme gmail.py."""
    return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()


def odata_time(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sender_text(message):
    a = (message.get("from") or {}).get("emailAddress", {})
    name, address = a.get("name", ""), a.get("address", "")
    return f"{name} <{address}>" if name and name != address else address


class Graph:
    def __init__(self, token_file, http=None, access_token=None):
        if http is None:
            import requests

            http = requests.Session()
        self.token_file, self.http, self.access_token = Path(token_file), http, access_token
        self.folders = {}

    def token(self):
        """Un jeton d'accès neuf par passage ; le cache MSAL est réécrit, car le jeton de rafraîchissement change."""
        if self.access_token is None:
            import msal

            t = json.loads(self.token_file.read_text(encoding="utf-8"))
            cache = msal.SerializableTokenCache()
            cache.deserialize(t["cache"])
            app = msal.PublicClientApplication(t["client_id"], authority=t["authority"], token_cache=cache)
            accounts = app.get_accounts()
            result = app.acquire_token_silent(SCOPES, account=accounts[0]) if accounts else None
            if not result or "access_token" not in result:
                raise PermissionError("Jeton Microsoft expiré : relancer « connecter ».")
            if cache.has_state_changed:
                t["cache"] = cache.serialize()
                self.token_file.write_text(json.dumps(t), encoding="utf-8")
            self.access_token = result["access_token"]
        return self.access_token

    def call(self, method, url, **kwargs):
        """Un appel à l'API ; None si l'objet n'existe plus (404)."""
        url = url if url.startswith("https://") else API + url
        r = self.http.request(method, url, timeout=30, headers={
            "Authorization": f"Bearer {self.token()}",
            "Prefer": 'IdType="ImmutableId", outlook.body-content-type="text"'}, **kwargs)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def items(self, path, params):
        """Tous les éléments d'une liste, en suivant `@odata.nextLink`."""
        page = self.call("GET", path, params={"$top": 100, **params})
        while page:
            yield from page.get("value", [])
            link = page.get("@odata.nextLink")
            page = self.call("GET", link) if link else None

    def folder_id(self, name, create=False):
        """Identifiant d'un dossier connu (`inbox`, `sentitems`) ou de `Pourriels-Claude` ; None s'il n'existe pas."""
        if name not in self.folders:
            if name != JUNK:
                self.folders[name] = self.call("GET", f"/mailFolders/{name}", params={"$select": "id"})["id"]
            else:
                found = list(self.items("/mailFolders", {"$filter": f"displayName eq '{JUNK}'", "$select": "id"}))
                if found:
                    self.folders[name] = found[0]["id"]
                elif create:
                    self.folders[name] = self.call("POST", "/mailFolders", json={"displayName": JUNK})["id"]
        return self.folders.get(name)

    def get(self, message_id, fields):
        return self.call("GET", f"/messages/{message_id}", params={"$select": fields})

    def list_inbox(self, since):
        return [{"id": m["id"], "thread_id": m["conversationId"], "sender": sender_text(m),
                 "subject": m.get("subject") or "",
                 "snippet": " ".join((m.get("body") or {}).get("content", "").split()) or m.get("bodyPreview", ""),
                 "received_at": gmt(m["receivedDateTime"])}
                for m in self.items("/mailFolders/inbox/messages", {
                    "$filter": f"receivedDateTime ge {odata_time(since)}",
                    "$select": "id,conversationId,from,subject,body,bodyPreview,receivedDateTime"})]

    def list_sent(self, since):
        return [{"id": m["id"], "thread_id": m["conversationId"], "subject": m.get("subject") or "",
                 "to": [r["emailAddress"]["address"].lower() for r in m.get("toRecipients", [])
                        if r.get("emailAddress", {}).get("address")],
                 "sent_at": gmt(m["sentDateTime"])}
                for m in self.items("/mailFolders/sentitems/messages", {
                    "$filter": f"sentDateTime ge {odata_time(since)}",
                    "$select": "id,conversationId,subject,toRecipients,sentDateTime"})]

    def get_thread(self, thread_id):
        """Les messages de la conversation, tous dossiers confondus ; « de moi » = rangé dans les éléments envoyés."""
        sent = self.folder_id("sentitems")
        messages = self.items("/messages", {"$filter": f"conversationId eq '{thread_id}'",
                                            "$select": "parentFolderId,receivedDateTime,isDraft"})
        return sorted(({"from_me": m["parentFolderId"] == sent, "date": gmt(m["receivedDateTime"])}
                       for m in messages if not m.get("isDraft")), key=lambda m: m["date"])

    def list_junk(self):
        """Identifiants des courriels de `Pourriels-Claude` ; rien si le dossier n'existe pas encore."""
        folder = self.folder_id(JUNK)
        if not folder:
            return []
        since = odata_time(datetime.now(timezone.utc) - JUNK_WINDOW)
        return [m["id"] for m in self.items(f"/mailFolders/{folder}/messages",
                                            {"$filter": f"receivedDateTime ge {since}", "$select": "id"})]

    def get_sender(self, message_id):
        m = self.get(message_id, "from")
        return sender_text(m) if m else ""

    def in_inbox(self, message_id):
        m = self.get(message_id, "parentFolderId")
        return bool(m) and m["parentFolderId"] == self.folder_id("inbox")

    def move_to_junk(self, message_id):
        """Déplacer dans `Pourriels-Claude` ; l'identifiant immuable ne change pas. Rien n'est supprimé."""
        self.call("POST", f"/messages/{message_id}/move", json={"destinationId": self.folder_id(JUNK, create=True)})
