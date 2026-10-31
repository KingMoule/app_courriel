# Workflow Claude du projet

Principe directeur : **less is more**. On n'ajoute une pièce au workflow que lorsqu'un problème réel l'exige, jamais « au cas où ».

## 1. Ce que disent les sources

| Constat | Anthropic | Littérature récente |
|---|---|---|
| Le fichier de contexte doit être court | CLAUDE.md < 200 lignes ; n'y mettre que ce que Claude ne peut pas deviner du code ([best practices](https://code.claude.com/docs/en/best-practices)) | Les fichiers générés par LLM n'améliorent pas le succès et coûtent ~20 % de tokens en plus ; les fichiers écrits à la main aident un peu s'ils se limitent aux conventions non évidentes ([Gloaguen et al., ICLR 2026](https://arxiv.org/abs/2602.11988)) |
| Plus de contexte n'est pas mieux | `/clear` entre tâches sans lien ; chaque requête relit toute la conversation ([coûts](https://code.claude.com/docs/en/costs)) | « Context rot » : la performance baisse quand l'entrée s'allonge, même sous la limite ([Chroma](https://research.trychroma.com/context-rot)) |
| Une règle sans exception = un hook, pas une phrase | Un CLAUDE.md est une demande ; un hook ou une règle `deny` est une garantie | Les vétérans Reddit convergent : hooks pour formater et vérifier, pas pour les préférences ([synthèse communautaire](https://llm-tool-research-docs.pages.dev/reddit-llm-community-research/)) |
| Donner une vérification | Tests, typecheck, hook `Stop` ; exiger la preuve (commande + sortie) | « Sans boucle de vérification » est l'anti-patron le plus cité |
| Spec avant code | Écrire `SPEC.md`, puis repartir d'un contexte neuf pour construire | Mode plan et documents de passation qui survivent aux sessions |
| Projets (beta) | Chaque fil est une session Claude Code complète : plus de fils = plus de quota ([annonce](https://claude.com/resources/articles/projects-redesigned)) | Découper en objectifs qui ne touchent pas les mêmes fichiers ; un modèle moins cher pour les fils simples |

**Arrimage.** Les deux sources disent la même chose sous deux angles : Anthropic explique *comment* garder le contexte petit, la recherche montre *pourquoi* (coût mesuré, gain faible ou nul du contexte superflu). La seule divergence : la communauté ajoute souvent beaucoup de hooks et de skills, alors qu'Anthropic recommande de les ajouter au fil des déclencheurs réels. On suit Anthropic.

## 2. Le workflow

1. **Un fil = un objectif.** Le coordinateur crée un fil par fonctionnalité indépendante. Pas deux fils sur les mêmes fichiers en même temps.
2. **Spec d'abord.** Toute fonctionnalité passe par `SPEC.md` (quoi, critère de fin, cas limites). Court.
3. **Construire, vérifier, prouver.** Le fil code, lance la vérification, et montre la sortie dans la PR.
4. **Une PR par objectif.** Tu relis et fusionnes ; rien ne va sur `main` sans toi.
5. **Apprendre une fois.** Une erreur répétée deux fois devient une ligne de CLAUDE.md (ou un hook si elle ne tolère aucune exception).

La mémoire du projet est désactivée : **le dépôt est la mémoire.** Les décisions durables vont dans `CLAUDE.md` ou `SPEC.md`, pas dans le fil.

## 3. Harness, hooks, skills : ce qu'il faut, et quand

Le **harness** est Claude Code lui-même : il charge `CLAUDE.md` à chaque session, applique `.claude/settings.json`, exécute les hooks et propose les skills. Il est déterministe ; le modèle ne l'est pas.

| Pièce | Maintenant | Déclencheur pour en ajouter |
|---|---|---|
| `CLAUDE.md` | ~20 lignes : commandes, règles, pièges | Claude se trompe deux fois sur la même chose |
| Règles `deny` (`.claude/settings.json`) | Bloquer la lecture de `.env` et `secrets/` : des jetons de 3 boîtes courriel ne doivent jamais entrer dans le contexte (le `deny` couvre l'outil Read, pas un `cat` en shell : le sandbox ou un hook le fermera si besoin) | Un nouveau fichier sensible apparaît |
| Hook `Stop` | Aucun (pas encore de tests) | Dès qu'une commande de test existe : bloquer la fin du tour tant qu'elle échoue |
| Hook `PostToolUse` (formatage) | Aucun | Dès qu'un formateur est choisi |
| Skills | Aucun | On colle la même procédure pour la 3ᵉ fois |
| Sous-agents | Aucun | Une tâche produit beaucoup de sortie qu'on ne relira pas |
| MCP | Aucun | Besoin d'un service que le CLI ne couvre pas |

## 4. Économie de tokens, en pratique

- Prompts précis : fichier, comportement attendu, vérification.
- `/clear` (ou un nouveau fil) entre sujets sans lien ; après deux corrections ratées, repartir avec un meilleur prompt.
- Modèle et effort adaptés : un fil simple n'a pas besoin du modèle le plus coûteux.
- Préférer un CLI (`gh`) à un serveur MCP quand les deux existent.

## 5. Instructions de projet suggérées (Projets beta)

À coller dans les réglages du projet :

> Réponds en français. Un fil par objectif, une PR par fil. Suis CLAUDE.md et SPEC.md du dépôt. Préfère la solution la plus simple ; n'ajoute ni hook, ni skill, ni dépendance sans déclencheur réel.

## 6. Garde-fou contre la complexité

Chaque PR finit par une ligne **« Complexité ajoutée : »** qui nomme ce qui a été ajouté au workflow ou au code, et le problème réel qui le justifie. Si on ne peut pas nommer le problème, on retire l'ajout.
