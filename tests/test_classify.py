import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from app_courriel import classify as c
from app_courriel.run import load_env
from tests.fakes import FakeClaude

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "classification.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "text",
    [
        "pas du json",
        "",
        None,
        "[1, 2]",
        '{"classe": "urgent", "resume": "x"}',
        '{"classe": "important"}',
        '{"classe": "important", "resume": 3}',
    ],
)
def test_invalid_reply_is_normal(text):
    assert c.parse_reply(text) == {"classe": "normal", "resume": ""}


def test_valid_reply():
    assert c.parse_reply('{"classe": "pourriel", "resume": " Arnaque. "}') == {"classe": "pourriel", "resume": "Arnaque."}


def test_address_is_normalized():
    assert c.address("Marie <Marie.Tremblay@Exemple.TEST>") == "marie.tremblay@exemple.test"


def test_blocked_sender_skips_claude():
    fake = FakeClaude()
    result = c.classify("Promo <a@pub.test>", "Soldes", "...", blocked={"a@pub.test"}, known=set(), ask=fake.classify)
    assert result["classe"] == "pourriel"
    assert fake.calls == 0


def test_blocked_wins_over_known_contact():
    result = c.classify("a@x.test", "s", "", blocked={"a@x.test"}, known={"a@x.test"}, ask=FakeClaude().classify)
    assert result["classe"] == "pourriel"


def test_known_contact_never_spam():
    fake = FakeClaude({"Luc <luc@x.test>": "pourriel"})
    result = c.classify("Luc <luc@x.test>", "Offre", "", blocked=set(), known={"luc@x.test"}, ask=fake.classify)
    assert result["classe"] == "normal"


def test_known_contact_can_be_important():
    fake = FakeClaude({"luc@x.test": "important"})
    assert c.classify("luc@x.test", "s", "", set(), {"luc@x.test"}, ask=fake.classify)["classe"] == "important"


class FakeClient:
    def __init__(self, content):
        self.content = content
        self.kwargs = None
        self.messages = self

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(content=self.content)


def test_ask_haiku_sends_500_chars_and_parses():
    client = FakeClient([SimpleNamespace(type="text", text='{"classe": "important", "resume": "Question."}')])
    result = c.ask_haiku("a@x.test", "Objet", "é" * 800, client=client)
    assert result == {"classe": "important", "resume": "Question."}
    assert client.kwargs["model"] == "claude-haiku-5-5"
    sent = json.loads(client.kwargs["messages"][0]["content"])
    assert sent == {"expediteur": "a@x.test", "objet": "Objet", "extrait": "é" * 500}


def test_ask_haiku_without_text_is_normal():
    client = FakeClient([])  # p. ex. un refus
    assert c.ask_haiku("a@x.test", "s", "", client=client)["classe"] == "normal"


def test_fixture_has_10_spam_10_legit():
    expected = [e["expected"] for e in FIXTURE["emails"]]
    assert expected.count("pourriel") == 10 and expected.count("legitime") == 10


@pytest.mark.live
def test_function1_real_api():
    """Fonction 1 : au moins 18/20 bien classés, aucun contact connu déplacé."""
    load_env()  # la clé vit dans .env
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY absent")
    known = set(FIXTURE["known_contacts"])
    wrong, moved_contacts = [], []
    for e in FIXTURE["emails"]:
        result = c.classify(e["sender"], e["subject"], e["snippet"], blocked=set(), known=known)
        is_spam = result["classe"] == "pourriel"
        if is_spam != (e["expected"] == "pourriel"):
            wrong.append((e["subject"], result))
        if is_spam and c.address(e["sender"]) in known:
            moved_contacts.append(e["subject"])
    print(f"\n{20 - len(wrong)}/20 bien classés", *wrong, sep="\n")
    assert len(wrong) <= 2, wrong
    assert moved_contacts == []
