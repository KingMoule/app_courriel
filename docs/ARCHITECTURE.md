# Architecture v1

Issue d'un débat entre deux propositions indépendantes (2026-10-31). Elle sert `SPEC.md` ; en cas d'écart, `SPEC.md` gagne.

## Fichiers
| Fichier | Rôle |
|---|---|
| `app_courriel/__main__.py` | Aiguillage : passage (par défaut), `desabonner`, `menage`, `connecter <compte>` |
| `app_courriel/db.py` | Ouvre `data/etat.db`, crée le schéma, petites requêtes |
| `app_courriel/gmail.py` | Client Gmail REST : lire, déplacer (libellé + retrait d'`INBOX`), lire une conversation |
| `app_courriel/graph.py` | Client Graph (`travail`, `perso_ancien`), en-tête `Prefer: IdType="ImmutableId"`, mêmes fonctions que `gmail.py` |
| `app_courriel/classify.py` | Règles, puis appel à Haiku, JSON strict, repli sur `normal` |
| `app_courriel/notify.py` | POST ntfy et plage silencieuse 22 h – 7 h |
| `app_courriel/run.py` | Le passage complet, et `build_reminder(items, now)`, fonction pure du rappel |
| `app_courriel/commands.py` | `desabonner` (POST RFC 8058 compris) et `menage` |
| `tests/fakes.py` | Faux client de courriel en mémoire, faux Claude, faux ntfy |
| `tests/fixtures/classification.json` | Les 20 courriels synthétiques |

Les deux clients exposent les mêmes fonctions (duck typing) : pas de classe de base, pas de SDK Google ou Microsoft. Ils rendent les en-têtes ; le regroupement (infolettres, gros expéditeurs) se fait une seule fois dans `commands.py`.

## Un passage (toutes les 10 min)
1. Fixer `now` (America/Toronto), ouvrir la base.
2. Pour chaque compte, dans un `try` : lire la boîte de réception depuis le dernier passage (30 jours au plus), insérer les nouveaux courriels non classés avec leur extrait de 500 caractères. Vérifier `Pourriels-Claude` : bloquer ce que j'y ai mis, débloquer ce qui en est ressorti. En cas d'erreur : une alerte par jour au plus, puis compte suivant.
3. Classer au plus 50 courriels, **les plus récents d'abord** : bloqué → `pourriel` sans appel ; sinon Haiku ; un contact connu n'est jamais `pourriel`. Vider l'extrait une fois classé. Une erreur d'API laisse le courriel non classé pour le passage suivant.
4. `pourriel` → déplacer, bloquer, `moved_by_script`. `important` → alerte seulement si reçu il y a moins d'1 h, hors 22 h – 7 h, pas déjà alerté et pas au premier lancement (couvre aussi le rattrapage).
5. Premier passage après 7 h : reconstruire `known_contacts` (envoyés des 12 derniers mois, en une transaction), relire par l'API les conversations en attente (« À répondre », « À relancer »), envoyer le rappel. Un compte en panne n'empêche pas le rappel des autres.
6. Écrire le dernier passage de chaque compte dont la lecture a réussi.

## Base SQLite (`data/etat.db`)
- `state(key PK, value)` : dernier passage par compte, date du dernier rappel, erreurs déjà signalées.
- `messages(account, id, thread_id, sender, subject, snippet, received_at, class, summary, alerted_at, moved_by_script, PK(account, id))`.
- `blocked_senders(address PK, blocked_at)` : commun aux 3 comptes.
- `known_contacts(address PK)` : reconstruite chaque jour.

## Dépendances
`anthropic`, `msal`, `google-auth-oauthlib`, `requests`, `tzdata` (fuseaux sous Windows) ; `pytest` en développement. `.env` est lu en quelques lignes, sans `python-dotenv`.

## Tests
`run.py` reçoit `now`, les clients, le classeur et l'envoyeur en paramètres ; les tests passent les faux de `tests/fakes.py`. Le test de la fonction 1 sur la vraie API est marqué `live` et se lance à la main. La fonction 3 se teste sur `build_reminder`.

## Ordre des PR
1. Squelette : `__main__`, `db`, `notify`, `fakes`, pytest, hook `Stop`.
2. `classify.py` + 20 courriels synthétiques + test réel (fonction 1).
3. `run.py` : tri, blocage, alertes, plafond, comptes en erreur (fonction 2).
4. Rappel du matin (fonction 3).
5. `gmail.py` + `connecter perso_recent`, essai réel en lecture seule.
6. `graph.py` + `perso_ancien`, puis `travail` si l'employeur le permet.
7. `commands.py` : `desabonner`, `menage`.
8. README : réglages du Planificateur de tâches Windows.

## Choix assumés
- Les réponses sont détectées en relisant les conversations par l'API une fois par jour : fidèle à « aucun message de moi n'a suivi dans la conversation », quelques dizaines d'appels par jour.
- Un extrait de courriel reste dans `data/etat.db` (ignoré par git) jusqu'à son classement, puis il est vidé.
