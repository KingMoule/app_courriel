import os
import sys
from pathlib import Path

from app_courriel import run

COMMANDS = ("desabonner", "menage", "connecter")
ACCOUNTS = ("perso_recent", "perso_ancien", "travail")


def connect(args):
    if len(args) != 1 or args[0] not in ACCOUNTS:
        print("Usage : python -m app_courriel connecter perso_recent|perso_ancien|travail", file=sys.stderr)
        return 2
    name = args[0]
    Path("secrets").mkdir(exist_ok=True)
    if name == "perso_recent":
        from app_courriel import gmail

        path = gmail.connect(name)
    else:
        from app_courriel import graph

        run.load_env()
        client_id = os.environ.get("MS_CLIENT_ID")
        if not client_id:
            print("MS_CLIENT_ID doit être défini dans .env (inscription de l'app dans Entra).", file=sys.stderr)
            return 1
        path = graph.connect(name, client_id)
    print(f"Jeton rangé dans {path}.")
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
