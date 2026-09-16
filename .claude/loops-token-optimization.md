# Boucles Claude Code & optimisation des tokens

Référence opérationnelle. Deux mécanismes distincts portent le nom de « boucle ».
Le premier est la source de 90 % de la facture, le second est l'outil que la
plupart des gens croient être le sujet.

---

## 1. La boucle interne (agentic loop) — la vraie facture

L'API est **sans état**. À chaque tour d'assistant, l'intégralité du contexte
(system prompt + définitions d'outils + toute la conversation + tous les
résultats d'outils) est renvoyée en entrée.

```
coût_entrée ≈ nb_de_tours × taille_moyenne_du_contexte × prix_input
```

Conséquence contre-intuitive : **le nombre d'allers-retours coûte plus cher que
la longueur des réponses.** 40 appels d'outils séquentiels sur un contexte de
60 k tokens = ~2,4 M tokens d'entrée. Les mêmes 40 appels groupés en 8 tours
parallèles = ~0,5 M.

### Leviers, par ordre d'impact

| Levier | Gain typique | Comment |
|---|---|---|
| Paralléliser les appels d'outils | 3-5× sur les tâches d'exploration | Un seul message contenant N appels indépendants, pas N messages |
| Ne jamais charger un fichier entier | 5-20× sur la lecture | `grep -n`, `sed -n '120,180p'`, `head`, jamais `cat` sur un gros fichier |
| Déléguer l'exploration à un sous-agent | énorme sur les tâches « cherche où est X » | Le sous-agent brûle son propre contexte, seule la conclusion revient |
| Garder le préfixe stable (cache) | 10× sur l'entrée | voir §2 |
| Externaliser l'état dans un fichier | évite la recompaction | Un fichier d'état de 2 ko relu à chaque tick > 80 k de transcript |

---

## 2. Le cache de prompt — le multiplicateur

Le cache est un **match de préfixe**. Ordre de rendu : `tools` → `system` →
`messages`. Un seul octet qui change quelque part invalide tout ce qui suit.

Tarifs relatifs au prix d'entrée de base :

| Opération | Multiplicateur |
|---|---|
| Lecture en cache | **0,1×** |
| Écriture en cache, TTL 5 min | 1,25× |
| Écriture en cache, TTL 1 h | 2× |

Rentabilité : TTL 5 min → rentable dès 2 requêtes. TTL 1 h → il en faut 3.
Une lecture rafraîchit le minuteur gratuitement.

**Ce qui casse le cache silencieusement** (et double la facture sans prévenir) :

- modifier `CLAUDE.md` ou le system prompt en cours de session ;
- changer l'ensemble des outils disponibles en cours de route ;
- un timestamp / UUID / `datetime.now()` dans le préfixe ;
- un `json.dumps()` non trié ;
- changer de modèle ou de niveau d'`effort` (les caches sont scopés par modèle).

Corollaire pratique : **les règles stables vont dans `CLAUDE.md`, écrit une fois
avant de démarrer**, pas répétées dans chaque prompt et surtout pas éditées en
plein milieu d'une session longue.

---

## 3. La boucle externe : `/loop`

Deux modes, mécaniques différentes.

### Mode intervalle fixe — `/loop 30m <prompt ou /commande>`

- S'appuie sur un job cron **en mémoire de session**. Rien n'est écrit sur
  disque : le job meurt avec la session.
- Ne se déclenche que quand le REPL est **inactif**, jamais au milieu d'un tour.
- Jitter automatique : jusqu'à 10 % de la période de retard (max 15 min).
- **Auto-expiration à 7 jours** : dernier tir, puis suppression.
- Éviter les minutes `:00` et `:30` — tout le monde y atterrit.

### Mode dynamique — `/loop <prompt>` sans intervalle

Le modèle se cadence lui-même via un appel de planification à chaque itération :

- `delaySeconds` est **borné à [60, 3600]**.
- `noop: true` quand rien n'a changé → les ticks silencieux consécutifs sont
  repliés dans l'affichage et comptés comme une série. `noop: false` quand
  quelque chose a bougé (fichier édité, message posté, état avancé).
- `stop: true` termine la boucle immédiatement.
- Le TTL de cache d'une heure couvre **toute** la plage autorisée : n'importe
  quel délai dans [60, 3600] se réveille avec le contexte encore en cache. Il
  n'y a donc aucune « falaise de cache » à contourner, et **planifier des
  réveils juste pour garder le cache chaud est du pur gaspillage.**

### Choix du délai

| Situation | Délai |
|---|---|
| Polling d'un état externe non notifiable (CI, déploiement, file distante) | La durée réelle du truc surveillé. Un run CI de 8 min = **un** check à 480 s, pas huit à 60 s |
| Heartbeat de secours (un Monitor ou une notification de tâche est le vrai signal) | 1200 s et plus |
| Tick inactif sans signal précis | 1200–1800 s |

---

## 4. Hiérarchie des primitives d'attente (du moins cher au plus cher)

C'est ici que se joue le plus gros gain. **Ne jamais poller ce que le harness
notifie déjà.**

1. **`Bash` en arrière-plan avec une condition de sortie** — coût token ≈ 0
   pendant l'attente, une seule notification à la sortie.
   ```bash
   until grep -q "Ready in" dev.log; do sleep 0.5; done
   ```
2. **`Monitor`** — un événement par ligne stdout filtrée. Expire par défaut à
   5 min, 30 min au maximum, à réarmer. Le filtre doit couvrir **aussi les
   échecs** : un monitor qui ne grep que le marqueur de succès reste muet
   pendant un crashloop, et le silence ressemble exactement à « ça tourne
   encore ».
3. **Abonnement aux événements PR** — piloté par événement, gratuit à l'arrêt.
4. **Boucle dynamique / réveil planifié** — un rejeu complet du contexte par
   tick. À réserver à ce qui n'est pas notifiable.
5. **Cron à intervalle fixe** — même coût, mais cadence aveugle.
6. **Jamais** : `sleep` au premier plan puis re-check (bloqué de toute façon),
   ni polling serré à 60 s.

---

## 5. Sous-agents : l'isolation de contexte

Un sous-agent a son propre contexte. Il lit 30 fichiers, brûle 200 k tokens
chez lui, et ne renvoie que sa conclusion dans le contexte principal.

À utiliser quand : la réponse demande de balayer beaucoup de fichiers et qu'on
ne veut que la conclusion. À ne pas utiliser quand on sait déjà quel fichier et
quel symbole regarder — l'ouvrir directement coûte moins.

Règle : une recherche déléguée n'est **pas** refaite en parallèle par soi-même.

---

## 6. Anti-patterns coûteux

| Anti-pattern | Coût | Correctif |
|---|---|---|
| `/loop 1m` sur une tâche qui bouge toutes les heures | 60× le contexte par heure | Intervalle = cadence réelle du changement |
| Boucle qui poll une tâche de fond déjà suivie | rejeu complet pour rien | Heartbeat long (1200 s+) en secours uniquement |
| `cat` d'un gros fichier « pour voir » | 10–50 k tokens | `grep -n` puis `sed -n` sur la plage |
| Appels d'outils séquentiels indépendants | N rejeux de contexte | Un message, N appels |
| Éditer `CLAUDE.md` en cours de session longue | cache invalidé, ×10 sur l'entrée | Le figer avant de démarrer |
| Session unique qui traîne sur 3 sujets | contexte gonflé + compaction | Une session par sujet |
| Laisser une boucle tourner après la fin du travail | facture silencieuse | `stop: true`, ou supprimer le job cron |

---

## 7. Comment rédiger un prompt de boucle

Un bon prompt de boucle contient quatre choses :

1. **La condition d'arrêt, explicite et vérifiable.** « Arrête quand
   `pytest -q` sort 0 » — pas « arrête quand c'est bon ».
2. **La commande de vérification à lancer à chaque tick**, pour que l'état soit
   re-dérivé d'une commande courte plutôt que du transcript.
3. **Le fichier d'état** à lire et écrire (`.claude/state/<tâche>.md`), pour
   survivre à une compaction.
4. **Ce qui compte comme `noop`.** Sinon chaque tick produit du bruit.

Squelette :

```
/loop Vérifie `make test`. Si rouge : diagnostique, corrige, relance.
Écris l'état dans .claude/state/tests.md (dernier commit testé, échecs restants).
Tick sans changement de l'état → noop.
Arrête dès que `make test` passe, ou après 3 échecs sur la même cause.
```

---

## 8. Ordre d'attaque pour réduire la facture

1. Supprimer les boucles inutiles (ce qui est notifié ne se poll pas).
2. Grouper les appels d'outils.
3. Ne lire que des plages de fichiers.
4. Stabiliser le préfixe pour que le cache tienne.
5. Isoler l'exploration dans des sous-agents.
6. Externaliser l'état sur disque.
7. Seulement ensuite : baisser l'`effort` ou changer de modèle — c'est le seul
   levier qui échange de la qualité contre du coût, tous les précédents sont
   gratuits.

---

## 9. Découper les sessions

Une session n'est pas le projet. Le projet vit sur le disque — code, `CLAUDE.md`,
docs, fichiers d'état. La session n'est que la fenêtre de conversation. Changer
de session ne fait perdre que le transcript, jamais le projet.

D'où la seule question qui compte : **le savoir est-il dans les fichiers ou
seulement dans la conversation ?** Dans les fichiers, couper est gratuit. Dans
la conversation, couper fait mal — et la réponse n'est pas de rallonger la
session, c'est d'écrire en continu.

### La règle

**Une frontière de session = une frontière de module.** Une session est
livrable quand on peut écrire :

1. ce qu'elle produit, en cinq lignes ;
2. la **commande** qui prouve que c'est fini.

Sans ces deux éléments, ce n'est pas une session, c'est encore un projet.

Corollaire utile : un projet qui résiste au découpage en sessions est presque
toujours un projet dont le code n'est pas découpé non plus. Le découpage de
session est un révélateur d'architecture.

### Le contrat d'abord

Dans un projet à plusieurs entrées (plusieurs sources, plusieurs connecteurs,
plusieurs formats), la première session fige le **schéma de données normalisé**,
et celle-là ne se découpe pas. Tant qu'il n'est pas figé, aucune autre session
n'est indépendante : chacune doit deviner ce que les autres produisent.

Une fois le contrat figé, les modules se traitent en sessions séparées, chacune
lisant le schéma et n'écrivant que son module, avec des fixtures en entrée. Une
session n'a jamais besoin de savoir comment une autre a été écrite.

### La reprise

Chaque session se termine en touchant deux fichiers :

- `.claude/state/<module>.md` — où ça en est, ce qui reste, les pièges
  rencontrés ;
- `ROADMAP.md` — statut des lots.

La session suivante démarre sur « lis `.claude/state/` et `ROADMAP.md`, on
attaque <module> ». Environ 2 ko de reprise au lieu de traîner un transcript
entier, sans perte, parce que ce qui comptait a été écrit au fil de l'eau.

### Quand ne pas couper

Jamais au milieu d'un diagnostic en cours : le raisonnement qui a de la valeur
n'est pas encore écrit. Terminer, écrire l'état, puis couper.
