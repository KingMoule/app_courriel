"""Un passage complet (ARCHITECTURE.md, « Un passage ») : lire, bloquer, classer, déplacer, alerter."""

import os
import re
import sys
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr
from pathlib import Path
from zoneinfo import ZoneInfo

from app_courriel import classify, db, notify

TZ = ZoneInfo("America/Toronto")
MAX_CALLS = 50  # appels à Claude par passage ; le surplus attend le passage suivant
LOOKBACK = timedelta(days=30)
ALERT_WINDOW = timedelta(hours=1)
REMINDER_MAX_LINES = 10  # par section ; on montre les plus vieux
FOLLOW_UP_AFTER = timedelta(days=3)
REMINDER_EXPIRES = timedelta(days=14)
CONTACT_WINDOW = timedelta(days=365)
OVERLAP = timedelta(minutes=10)  # un courriel livré en retard n'est pas raté ; les doublons sont ignorés


def utc_iso(value):
    """ISO 8601 avec fuseau -> ISO UTC, pour trier et comparer en texte dans SQLite."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.astimezone(timezone.utc).isoformat()


def block(conn, sender, now):
    with conn:
        conn.execute("INSERT OR IGNORE INTO blocked_senders VALUES (?, ?)", (classify.address(sender), utc_iso(now)))


def read_account(conn, name, client, now):
    """Étape 2 : nouveaux courriels de la boîte de réception, puis état de `Pourriels-Claude`."""
    last = db.get_state(conn, f"last_pass:{name}")
    since = max(datetime.fromisoformat(last) - OVERLAP, now - LOOKBACK) if last else now - LOOKBACK
    with conn:
        for m in client.list_inbox(since):
            conn.execute(
                "INSERT OR IGNORE INTO messages (account, id, thread_id, sender, subject, snippet, received_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (name, m["id"], m["thread_id"], m["sender"], m["subject"],
                 m["snippet"][: classify.SNIPPET_CHARS], utc_iso(m["received_at"])),
            )

    junk = set(client.list_junk())
    moved = {r[0]: r[1] for r in conn.execute(
        "SELECT id, sender FROM messages WHERE account = ? AND moved_by_script = 1", (name,))}
    for message_id in junk - moved.keys():  # c'est moi qui l'y ai mis
        sender = client.get_sender(message_id)
        if sender:
            block(conn, sender, now)
    for message_id, sender in moved.items():
        if message_id in junk:
            continue
        with conn:  # ressorti du dossier : on cesse de le surveiller
            conn.execute("UPDATE messages SET moved_by_script = 0 WHERE account = ? AND id = ?", (name, message_id))
            if client.in_inbox(message_id):  # remis dans la boîte de réception : débloquer
                conn.execute("DELETE FROM blocked_senders WHERE address = ?", (classify.address(sender),))


def alert_text(account, sender, subject, summary):
    """(titre, message). Rien de confidentiel du compte `travail` ne passe par ntfy.sh."""
    if account == "travail":
        return "Courriel important (travail)", "Courriel important (travail)"
    return f"{account} : {sender}", f"{subject}\n{summary}".strip()


def report_error(conn, name, error, now, send):
    """Une alerte par jour au plus pour un compte en panne ; jamais la nuit."""
    print(f"Compte {name} : {type(error).__name__}", file=sys.stderr)
    key, today = f"error_alert:{name}", now.date().isoformat()
    if notify.is_quiet(now) or db.get_state(conn, key) == today:
        return
    try:
        send(f"Compte {name} inaccessible", f"Le compte {name} n'a pas pu être lu ({type(error).__name__}).")
    except Exception as e:
        print(f"ntfy : {type(e).__name__}", file=sys.stderr)
        return
    db.set_state(conn, key, today)


def classify_pending(conn, clients, first_run, now, ask, send):
    """Étapes 3 et 4 : les plus récents d'abord, au plus MAX_CALLS appels à Claude."""
    blocked = {r[0] for r in conn.execute("SELECT address FROM blocked_senders")}
    known = {r[0] for r in conn.execute("SELECT address FROM known_contacts")}
    rows = conn.execute(
        "SELECT account, id, sender, subject, snippet, received_at FROM messages"
        " WHERE class IS NULL ORDER BY received_at DESC"
    ).fetchall()
    calls, failed = 0, set()
    for account, message_id, sender, subject, snippet, received_at in rows:
        if account not in clients or account in failed:
            continue
        addr = classify.address(sender)
        if addr not in blocked:
            if calls >= MAX_CALLS:
                continue  # les bloqués restent classables sans appel
            calls += 1

        try:
            result = classify.classify(sender, subject, snippet, blocked, known, ask=ask)
        except Exception as e:  # API en panne : reste non classé, repris au prochain passage
            print(f"Claude : {type(e).__name__}", file=sys.stderr)
            continue

        moved = result["classe"] == "pourriel"
        if moved:
            try:
                clients[account].move_to_junk(message_id)
            except Exception as e:
                failed.add(account)
                report_error(conn, account, e, now, send)
                continue
            block(conn, sender, now)
            blocked.add(addr)

        with conn:
            conn.execute(
                "UPDATE messages SET class = ?, summary = ?, snippet = '', moved_by_script = ?"
                " WHERE account = ? AND id = ?",
                (result["classe"], result["resume"], int(moved), account, message_id),
            )

        recent = datetime.fromisoformat(received_at) > now - ALERT_WINDOW
        if result["classe"] == "important" and recent and not first_run[account] and not notify.is_quiet(now):
            try:
                send(*alert_text(account, sender, subject, result["resume"]))
            except Exception as e:
                print(f"ntfy : {type(e).__name__}", file=sys.stderr)
                continue
            with conn:
                conn.execute("UPDATE messages SET alerted_at = ? WHERE account = ? AND id = ?",
                             (utc_iso(now), account, message_id))
    return failed


def is_no_reply(address):
    local = re.sub(r"[-_.]", "", address.split("@")[0])
    return local.startswith(("noreply", "donotreply"))


def age_text(delta):
    return f"{delta.days} j" if delta.days >= 1 else f"{delta.seconds // 3600} h"


def build_reminder(items, now):
    """Fonction pure (SPEC.md, fonction 3). `items` : {kind: "reply" | "follow_up", account, who, subject, date}.
    Rend le texte du rappel, ou None s'il n'y a rien à rappeler."""
    sections = []
    for kind, title in (("reply", "À répondre"), ("follow_up", "À relancer")):
        mine = sorted((i for i in items if i["kind"] == kind), key=lambda i: i["date"])
        if not mine:
            continue
        head = f"{title} ({len(mine)})" if len(mine) <= REMINDER_MAX_LINES else \
            f"{title} ({len(mine)}, les {REMINDER_MAX_LINES} plus vieux)"
        lines = []
        for i in mine[:REMINDER_MAX_LINES]:
            age = age_text(now - i["date"])
            if i["account"] == "travail":  # rien de confidentiel sur ntfy.sh
                lines.append(f"• travail ({age})")
            else:
                lines.append(f"• {'→ ' if kind == 'follow_up' else ''}{i['who']} — {i['subject']} ({age})")
        sections.append("\n".join([head] + lines))
    return "\n\n".join(sections) or None


def account_items(conn, name, client, sent, now):
    """Les courriels d'un compte à rappeler, après relecture des conversations par l'API."""
    threads = {}

    def later(thread_id):
        if thread_id not in threads:
            threads[thread_id] = [(m["from_me"], datetime.fromisoformat(m["date"])) for m in client.get_thread(thread_id)]
        return threads[thread_id]

    items = []
    rows = conn.execute(
        "SELECT sender, subject, received_at, thread_id FROM messages"
        " WHERE account = ? AND class = 'important' AND received_at > ?",
        (name, utc_iso(now - REMINDER_EXPIRES)))
    for sender, subject, received_at, thread_id in rows.fetchall():
        received = datetime.fromisoformat(received_at)
        if not any(mine and date > received for mine, date in later(thread_id)):  # je n'ai pas répondu
            items.append({"kind": "reply", "account": name, "date": received, "subject": subject,
                          "who": parseaddr(sender)[0] or classify.address(sender)})
    for m in sent:
        when, to = datetime.fromisoformat(m["sent_at"]), m["to"]
        if not (now - REMINDER_EXPIRES < when <= now - FOLLOW_UP_AFTER) or len(to) != 1 or is_no_reply(to[0]):
            continue
        if not any(date > when for _, date in later(m["thread_id"])):  # personne n'a écrit depuis
            items.append({"kind": "follow_up", "account": name, "date": when, "subject": m["subject"], "who": to[0]})
    return items


def remind(conn, now, clients, send):
    """Étape 5 : le premier passage après 7 h, une fois par jour. Un compte en panne n'empêche pas les autres."""
    today = now.date().isoformat()
    if now.hour < notify.QUIET_END or db.get_state(conn, "last_reminder") == today:
        return
    items, contacts, all_ok = [], set(), True
    for name, client in clients.items():
        try:
            sent = client.list_sent(now - CONTACT_WINDOW)
            items += account_items(conn, name, client, sent, now)
        except Exception as e:
            all_ok = False
            report_error(conn, name, e, now, send)
            continue
        contacts |= {classify.address(a) for m in sent for a in m["to"]}
    with conn:  # known_contacts se reconstruit ; on ne retire rien si un compte n'a pas répondu
        if all_ok:
            conn.execute("DELETE FROM known_contacts")
        conn.executemany("INSERT OR IGNORE INTO known_contacts VALUES (?)", [(a,) for a in contacts])
    text = build_reminder(items, now)
    if text:
        try:
            send("Rappel du matin", text)
        except Exception as e:
            print(f"ntfy : {type(e).__name__}", file=sys.stderr)
            return  # repris au prochain passage
    db.set_state(conn, "last_reminder", today)


def run_pass(conn, now, clients, ask, send):
    """Un passage. `clients` : {nom du compte: client}, `send(titre, message)` pousse sur ntfy."""
    first_run = {name: db.get_state(conn, f"last_pass:{name}") is None for name in clients}
    ok = {}
    for name, client in clients.items():
        try:
            read_account(conn, name, client, now)
            ok[name] = client
        except Exception as e:
            report_error(conn, name, e, now, send)

    failed = classify_pending(conn, ok, first_run, now, ask, send)
    remind(conn, now, ok, send)

    for name in ok:
        if name not in failed:
            db.set_state(conn, f"last_pass:{name}", now.isoformat())


def load_env(path=".env"):
    """Lit KEY=valeur ligne par ligne ; ne remplace pas une variable déjà définie."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def make_clients(secrets="secrets"):
    """Les comptes connectés (jeton présent dans secrets/). Graph arrive à l'étape 6."""
    from app_courriel import gmail

    token = Path(secrets) / "perso_recent.json"
    return {"perso_recent": gmail.Gmail(token)} if token.exists() else {}


def main():
    load_env()
    clients = make_clients()
    topic = os.environ.get("NTFY_TOPIC")
    if clients and not (os.environ.get("ANTHROPIC_API_KEY") and topic):
        print("ANTHROPIC_API_KEY et NTFY_TOPIC doivent être définis dans .env.", file=sys.stderr)
        return 1

    def send(title, message):
        notify.send(topic, message, title=title)

    anthropic_client = None

    def ask(sender, subject, snippet):
        nonlocal anthropic_client
        if anthropic_client is None:
            import anthropic

            anthropic_client = anthropic.Anthropic()
        return classify.ask_haiku(sender, subject, snippet, client=anthropic_client)

    conn = db.open_db()
    try:
        run_pass(conn, datetime.now(TZ), clients, ask, send)
    finally:
        conn.close()
    return 0
