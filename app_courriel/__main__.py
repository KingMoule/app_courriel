import sys

from app_courriel import db

COMMANDS = ("desabonner", "menage", "connecter")


def main(argv):
    command = argv[0] if argv else "passage"
    if command == "passage":
        db.open_db().close()  # le passage complet arrive avec run.py
        return 0
    if command in COMMANDS:
        print(f"Commande « {command} » pas encore implémentée.", file=sys.stderr)
        return 1
    print(f"Commande inconnue : {command}. Choix : passage, {', '.join(COMMANDS)}.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
