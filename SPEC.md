# SPEC — app_courriel v1

## But
Un script local qui surveille les 3 comptes et :
1. déplace les pourriels que les filtres ont ratés ;
2. envoie une alerte sur le cellulaire quand un courriel important arrive ;
3. envoie chaque matin la liste des courriels importants encore sans réponse.

## Comptes
| Nom | Fournisseur | Accès |
|---|---|---|
| `travail` | Microsoft 365 (compte d'organisation) | Microsoft Graph |
| `perso_recent` | Gmail | Gmail API |
| `perso_ancien` | Hotmail (compte Microsoft personnel, le plus de pourriels) | Microsoft Graph |

Connexion OAuth une fois par compte ; les jetons vivent dans `secrets/` (jamais dans le dépôt). Aucune adresse réelle dans le code : on désigne les comptes par leur nom ci-dessus.

## Forme
Script Python en ligne de commande, `python -m app_courriel`, lancé **toutes les 10 minutes** par le planificateur de tâches de l'ordinateur, qui reste allumé (écran en veille : OK ; mise en veille de l'ordinateur : non, sinon le planificateur s'arrête). Pas d'interface.

Alertes et rappels passent par [ntfy](https://ntfy.sh) : une app gratuite sur le cellulaire, sans compte, qui reçoit un message par simple requête HTTP sur un sujet secret (gardé dans `.env`).

## Classement (une passe par nouveau courriel)
- Lit les courriels de la boîte de réception reçus depuis le dernier passage.
- Expéditeur dans les contacts ou à qui on a déjà écrit : jamais `pourriel`.
- Claude classe chaque courriel : `pourriel`, `important` ou `normal`, avec une raison d'une ligne. Seuls l'expéditeur, l'objet et les 500 premiers caractères sont envoyés.
- `important` = une personne (pas une infolettre ni un `no-reply`) m'écrit directement et attend une réponse ou une action de ma part.

## Fonction 1 — Tri des pourriels
Un `pourriel` est **déplacé** dans un dossier `Pourriels-Claude`, jamais supprimé.

**Fini quand** : sur 20 courriels synthétiques (10 pourriels, 10 légitimes), au moins 18 sont bien classés et aucun courriel d'un contact n'est déplacé.

## Fonction 2 — Alerte sur le cellulaire
Un courriel `important` déclenche une alerte ntfy : compte, expéditeur, objet. Une seule alerte par courriel. Pas d'alerte entre 22 h et 7 h (elles attendent le matin).

**Fini quand** : un courriel synthétique `important` produit exactement une alerte, un `normal` aucune.

## Fonction 3 — Rappel du matin
À 7 h, une alerte ntfy liste les courriels `important` sans réponse : aucun message de moi n'a suivi dans la même conversation. Un courriel sort de la liste quand j'y réponds, ou après 14 jours.

**Fini quand** : sur des conversations synthétiques, le rappel liste exactement les `important` sans réponse et ignore ceux où j'ai répondu.

## Cas limites
- Un compte inaccessible (jeton expiré, accès refusé) : une alerte le signale une fois par jour ; les autres comptes continuent.
- Le compte `travail` peut exiger l'approbation de l'administrateur pour Graph : si c'est refusé, la v1 se limite aux deux comptes personnels.
- Ordinateur éteint : rien ne tourne ; au redémarrage, le script traite ce qui est arrivé entre-temps, sans alerte pour ce qui a déjà été lu.

## Hors de la v1
Interface web ou de bureau, réponses rédigées par Claude, suppression automatique.

## Ordre de construction
Les deux comptes personnels d'abord. Le compte `travail` en dernier, après avoir vérifié auprès de l'employeur que l'accès par une app tierce et l'envoi d'extraits de courriels à Claude sont permis.
