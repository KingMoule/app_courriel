# SPEC — app_courriel v1

## But
Un script local qui surveille les 3 comptes et :
1. déplace les pourriels que les filtres ont ratés ;
2. envoie une alerte sur le iPhone, avec un résumé d'une ligne, quand un courriel important arrive ;
3. envoie chaque matin la liste des courriels qui attendent une réponse, de moi ou des autres.

Plus deux commandes à lancer une fois : désabonnement en masse et grand ménage.

## Pourquoi bâtir plutôt qu'utiliser une app
Aucune app étudiée ne réunit tri par IA, alertes jugées par l'IA, rappel du matin et relances pour moins de 5 $ par mois ([comparaison](https://claude.ai/artifact/PJ5AsvwXDF1P7jU1BzK29Z)). Spark gratuit ne trie pas par IA et n'a pas de rappel du matin ; SaneBox coûte 319 $ US par an pour 3 comptes.

## Comptes
| Nom | Fournisseur | Accès |
|---|---|---|
| `travail` | Microsoft 365 (compte d'organisation) | Microsoft Graph |
| `perso_recent` | Gmail | Gmail API |
| `perso_ancien` | Hotmail (compte Microsoft personnel, le plus de pourriels) | Microsoft Graph |

Connexion OAuth une fois par compte ; les jetons vivent dans `secrets/` (jamais dans le dépôt). Aucune adresse réelle dans le code : on désigne les comptes par leur nom ci-dessus.

## Forme
Script Python en ligne de commande, `python -m app_courriel`, lancé **toutes les 10 minutes** par le planificateur de tâches de l'ordinateur, qui reste allumé (écran en veille : OK ; mise en veille de l'ordinateur : non, sinon le planificateur s'arrête). Pas d'interface.

Alertes et rappels passent par [ntfy](https://ntfy.sh) : une app gratuite sur iPhone, sans compte, qui reçoit un message par simple requête HTTP sur un sujet secret (gardé dans `.env`). Les notifications de l'app de courriel sur le cellulaire sont coupées : seules les alertes ntfy sonnent.

**Budget : moins de 5 $ par mois.** Volume : plus de 100 courriels par jour. On utilise le plus petit modèle Claude, et les règles passent avant l'IA (voir Classement).

## Classement (une passe par nouveau courriel)
- Lit les courriels de la boîte de réception reçus depuis le dernier passage.
- Règles d'abord, sans appel à Claude :
  - expéditeur bloqué (déjà déplacé dans `Pourriels-Claude`, par moi ou par le script) : `pourriel` directement ;
  - expéditeur dans les contacts ou à qui j'ai déjà écrit : jamais `pourriel`.
- Claude classe chaque courriel restant : `pourriel`, `important` ou `normal`, avec un résumé d'une ligne. Seuls l'expéditeur, l'objet et les 500 premiers caractères sont envoyés.
- `important` = une personne (pas une infolettre ni un `no-reply`) m'écrit directement et attend une réponse ou une action de ma part.

## Fonction 1 — Tri des pourriels
Un `pourriel` est **déplacé** dans un dossier `Pourriels-Claude`, jamais supprimé, et son expéditeur est bloqué pour les prochains passages. Les pourriels visés : la pub non désirée comme les arnaques.

**Fini quand** : sur 20 courriels synthétiques (10 pourriels, 10 légitimes), au moins 18 sont bien classés et aucun courriel d'un contact n'est déplacé.

## Fonction 2 — Alerte sur le cellulaire
Un courriel `important` déclenche une alerte ntfy : compte, expéditeur, objet, résumé d'une ligne. Une seule alerte par courriel. Pas d'alerte entre 22 h et 7 h (elles attendent le matin).

**Fini quand** : un courriel synthétique `important` produit exactement une alerte avec son résumé, un `normal` aucune.

## Fonction 3 — Rappel du matin
À 7 h, une notification ntfy liste :
- **À répondre** : les courriels `important` reçus auxquels je n'ai pas répondu (aucun message de moi n'a suivi dans la conversation), **qu'ils soient lus ou non** ;
- **À relancer** : mes courriels envoyés à une personne, sans réponse depuis 3 jours.

Chaque ligne : expéditeur ou destinataire, objet, âge. Si la liste dépasse 10 lignes, on montre les 10 plus vieilles et le total. Un courriel sort de la liste quand la conversation reçoit une réponse, ou après 14 jours.

**Fini quand** : sur des conversations synthétiques, le rappel liste exactement les `important` sans réponse et les envois sans réponse depuis 3 jours, et ignore ceux qui ont reçu une réponse.

## Commandes ponctuelles
- `python -m app_courriel desabonner` : liste les expéditeurs d'infolettres des 90 derniers jours (en-tête `List-Unsubscribe`), je coche, le script se désabonne et bloque l'expéditeur.
- `python -m app_courriel menage` : liste les expéditeurs qui occupent le plus de place dans Hotmail ; je choisis, le script déplace leurs courriels dans un dossier `Menage` (jamais supprimés).

**Fini quand** : sur des données synthétiques, chaque commande ne touche que les expéditeurs cochés.

## Cas limites
- Un compte inaccessible (jeton expiré, accès refusé) : une alerte le signale une fois par jour ; les autres comptes continuent.
- Le compte `travail` peut exiger l'approbation de l'administrateur pour Graph : si c'est refusé, la v1 se limite aux deux comptes personnels.
- Ordinateur éteint : rien ne tourne ; au redémarrage, le script traite ce qui est arrivé entre-temps, sans alerte pour ce qui a déjà été lu.
- Un courriel légitime déplacé par erreur : le remettre dans la boîte de réception débloque son expéditeur.

## Hors de la v1
Interface web ou de bureau, réponses rédigées par Claude, suppression automatique, courriels transformés en tâches.

## Hypothèse
L'employeur permet l'accès au compte `travail` par une app tierce et l'envoi d'extraits de courriels à Claude. À confirmer avant de brancher ce compte.
