from datetime import datetime

QUIET_START, QUIET_END = 22, 7  # plage silencieuse : 22 h – 7 h


def is_quiet(now: datetime) -> bool:
    return now.hour >= QUIET_START or now.hour < QUIET_END


def send(topic, message, title=None, post=None):
    """POST un message sur ntfy. `post` est injectable pour les tests."""
    if post is None:
        import requests

        post = requests.post
    headers = {"Title": title.encode("utf-8")} if title else {}
    post(f"https://ntfy.sh/{topic}", data=message.encode("utf-8"), headers=headers, timeout=10)
