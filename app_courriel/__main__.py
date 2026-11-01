import sys

from app_courriel import run

COMMANDS = ("desabonner", "menage", "connecter")


def main(argv):
    command = argv[0] if argv else "passage"
    if command == "passage":
        return run.main()
    if command in COMMANDS:
        print(f"Commande « {command} » pas encore implémentée.", file=sys.stderr)
        return 1
    print(f"Commande inconnue : {command}. Choix : passage, {', '.join(COMMANDS)}.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
