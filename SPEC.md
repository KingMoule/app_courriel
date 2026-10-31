# SPEC — app_courriel v1

## But
Un script local qui, chaque matin, (1) déplace les pourriels que les filtres ont ratés et (2) rappelle les courriels qui attendent une réponse, sur les 3 comptes.

## Comptes
| Nom | Fournisseur | Accès |
|---|---|---|
| `travail` | Microsoft 365 (compte d'organisation) | Microsoft Graph |
| `perso_recent` | Gmail | Gmail API |
| `perso_ancien` | Hotmail (compte Microsoft personnel) | Microsoft Graph |

Connexion OAuth une fois par compte ; les jetons vivent dans `secrets/` (jamais dans le dépôt). Aucune adresse réelle dans le code : on désigne les comptes par leur nom ci-dessus.

## Forme
Script Python en ligne de commande, `python -m app_courriel`, lancé à la main ou par le planificateur de tâches. Pas d'interface. La sortie est un résumé texte (console + un courriel de résumé envoyé à soi-même sur `perso_recent`).

## Fonction 1 — Tri des pourriels
- Lit les courriels de la boîte de réception reçus depuis le dernier passage.
- Claude classe chacun : `pourriel` ou `ok`, avec une raison d'une ligne. Seuls l'expéditeur, l'objet et les 500 premiers caractères sont envoyés.
- Un `pourriel` est **déplacé** dans un dossier `Pourriels-Claude`, jamais supprimé.
- Expéditeur dans les contacts ou à qui on a déjà écrit : toujours `ok`, sans appel à Claude.

**Fini quand** : sur un jeu de 20 courriels synthétiques (10 pourriels, 10 légitimes), le tri en classe au moins 18 correctement et aucun courriel d'un contact n'est déplacé.

## Fonction 2 — Rappels de réponse
- Un courriel « attend une réponse » s'il est dans la boîte de réception, vient d'une personne (pas d'une infolettre ni d'un `no-reply`), m'est adressé en `À`, et qu'aucun message de moi n'a suivi dans la même conversation.
- Après **3 jours** ouvrables sans réponse, il apparaît dans le résumé du matin : compte, expéditeur, objet, âge.
- Pas de relance au-delà de 14 jours : il sort de la liste.

**Fini quand** : sur des conversations synthétiques, le script liste exactement celles sans réponse depuis 3 jours et ignore celles où j'ai répondu.

## Cas limites
- Un compte inaccessible (jeton expiré, accès bloqué) : le résumé le signale et les autres comptes sont traités quand même.
- Le compte `travail` peut exiger l'approbation de l'administrateur pour Graph : si c'est refusé, la v1 se limite aux deux comptes personnels.

## Hors de la v1
Interface web ou de bureau, réponses rédigées par Claude, suppression automatique, notifications sur téléphone.

## Questions ouvertes
- Une interface plutôt qu'un script ?
- 3 jours ouvrables comme délai de rappel ?
- Le compte de travail autorise-t-il les apps tierces ?
