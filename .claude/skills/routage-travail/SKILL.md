---
name: routage-travail
description: >
  Décide AUTOMATIQUEMENT — sans qu'on le demande — comment router une demande de
  travail : traitement direct, sous-agent, ou session séparée. Appliquer ce skill
  dès que l'utilisateur ouvre un chantier plutôt qu'une question : « on attaque
  X », « il faut ajouter Y », « je veux un outil qui… », une nouvelle
  fonctionnalité, un lot de roadmap, une demande qui touche plusieurs modules,
  une exploration large du code, ou toute demande dont la réalisation dépasse
  quelques fichiers. Ce skill existe parce que le comportement par défaut est de
  tout traiter dans le fil en cours, ce qui gonfle le contexte et fait repayer ce
  gonflement à chaque tour. Ne PAS attendre que l'utilisateur demande un
  découpage, un sous-agent ou une nouvelle session : c'est ce skill qui le
  propose. Ne pas déclencher sur une question, une correction ponctuelle, ou la
  poursuite d'un diagnostic déjà entamé.
---

# Routage du travail

Avant de commencer à travailler, classer la demande. Le routage se fait en une
ligne visible par l'utilisateur, pas en silence.

## Les trois routes

| Route | Quand | Coût |
|---|---|---|
| **Ici, directement** | correction locale, question, suite d'un diagnostic en cours, tâche de quelques fichiers | nul |
| **Sous-agent** | exploration large (« où est X », « quels fichiers touchent Y »), sous-tâche lourde en lecture dont **seule la conclusion** doit revenir dans ce fil | le sous-agent brûle son propre contexte, la conclusion seule revient |
| **Session séparée** | lot indépendant, livrable et revu à part, travail parallèle sur un autre module, chantier qui va durer plusieurs heures | un conteneur de plus, une branche de plus à suivre |

**La confusion à éviter** : la plupart des sous-tâches lourdes appellent un
sous-agent, pas une session. Une session séparée ne se justifie que si le
travail a sa **propre vie** — sa branche, sa revue, son rythme. Ouvrir une
session pour ce qu'un sous-agent fait très bien ajoute de la charge de suivi
sans rien économiser.

## Procédure

1. **Classer** la demande selon le tableau. En cas d'hésitation entre sous-agent
   et session : sous-agent.
2. **Vérifier que c'est découpable.** Une unité séparable se décrit en cinq
   lignes et se vérifie par **une commande**. Si la vérification ne s'écrit pas,
   l'unité n'est pas prête : le dire, et traiter d'abord ce qui manque
   (typiquement un schéma de données ou un contrat d'interface non figé — voir
   `.claude/loops-token-optimization.md` §9).
3. **Annoncer le routage en une ligne**, avec le découpage concret proposé.
   Ne pas demander « veux-tu que je découpe ? » : proposer le découpage fait.
4. **Sous-agent** : lancer directement, pas de confirmation à demander.
5. **Session séparée** : écrire d'abord le relais (ci-dessous), puis proposer le
   lancement. Attendre un accord avant de créer la session — ouvrir un
   conteneur et une branche engage l'utilisateur au-delà du fil en cours.

## Relais avant de créer une session

Une session lancée sans relais démarre aveugle et refait le travail de
compréhension. Avant tout lancement :

- écrire ou mettre à jour `.claude/state/<module>.md` : l'état, ce qui reste,
  les pièges déjà rencontrés ;
- vérifier que `ROADMAP.md` (s'il existe) situe le lot ;
- rédiger le prompt de la nouvelle session comme une instruction **autonome** :
  elle ne voit rien de la conversation en cours. Elle doit pointer vers
  `.claude/state/` et `ROADMAP.md`, nommer le module, et donner la commande de
  vérification qui prouve que le lot est fini.

Créer la session avec `create_session` (serveur MCP Claude Code Remote) en
héritant de l'environnement courant, avec un `title` qui nomme le lot et un
`tags` commun au chantier pour les retrouver ensemble.

## Ne pas router

- au milieu d'un diagnostic en cours : le raisonnement utile n'est pas encore
  écrit — terminer, écrire l'état, router ensuite ;
- sur une demande dont la réponse tient dans le fil.
