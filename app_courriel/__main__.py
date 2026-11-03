import sys
from pathlib import Path

from app_courriel import run

COMMANDS = ("desabonner", "menage", "connecter")


def connect(args):
    if args != ["perso_recent"]:
        print("Usage : python -m app_courriel connecter perso_recent (travail et perso_ancien : à venir).",
              file=sys.stderr)
        return 2
    from app_courriel import gmail

    Path("secrets").mkdir(exist_ok=True)
    print(f"Jeton rangé dans {gmail.connect('perso_recent')}.")
    return 0


def main(argv):
    command = argv[0] if argv else "passage"
    if command == "passage":
        return run.main()
    if command == "connecter":
        return connect(argv[1:])
    if command in COMMANDS:
        print(f"Commande « {command} » pas encore implémentée.", file=sys.stderr)
        return 1
    print(f"Commande inconnue : {command}. Choix : passage, {', '.join(COMMANDS)}.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
