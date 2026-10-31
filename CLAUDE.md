# app_courriel

Application qui regroupe 3 comptes courriel (travail, personnel récent, personnel ancien) pour mieux trier les pourriels et rappeler les courriels qui attendent une réponse.

Langue : on échange en français ; le code et ses identifiants sont en anglais.

## Commandes
<!-- À remplir dès que la pile est choisie : installer, lancer, tester un seul fichier, lint. -->
- Installer : `pip install -r requirements-dev.txt`
- Tests : `python3 -m pytest -q` (aussi lancé par le hook `Stop`)
- Lancer un passage : `python3 -m app_courriel`

## Règles
- Avant de coder une fonctionnalité, s'appuyer sur `SPEC.md` ; si elle n'y est pas, la proposer d'abord.
- Une tâche est finie quand sa vérification passe ; montrer la commande lancée et sa sortie.
- Aucun vrai courriel, identifiant ou jeton dans le dépôt, les tests ou les logs : données de test synthétiques seulement.
- Préférer la solution la plus simple qui marche. Pas d'abstraction pour un seul usage.

## Pièges
- Les secrets (jetons, mots de passe) vivent dans `.env` : ignoré par git, lecture bloquée pour Claude.
