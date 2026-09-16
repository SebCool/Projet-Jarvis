# Instructions projet

Ce fichier est chargé automatiquement au démarrage de chaque session et se
trouve dans le préfixe mis en cache. **Ne pas le modifier en cours de session :
toute édition invalide le cache et multiplie le coût d'entrée des tours
suivants.** Le garder court fait partie de son objet.

## Discipline de contexte

Le contexte complet est renvoyé en entrée à chaque tour. Le coût suit
`nombre de tours × taille du contexte` : le nombre d'allers-retours pèse plus
que la longueur des réponses.

1. **Grouper.** Des appels d'outils indépendants partent dans un seul message,
   jamais en série.
2. **Lire des plages, pas des fichiers.** `grep -n` pour localiser, puis
   `sed -n 'debut,finp'` ou un Read avec `offset`/`limit`. Un hook
   (`.claude/hooks/guard-whole-file-reads.sh`) refuse les lectures entières
   au-delà de 800 lignes ; il ne bloque pas les pipes (`cat f | grep …`).
3. **Déléguer l'exploration.** « Où est implémenté X », « quels fichiers
   touchent Y » partent à un sous-agent : il brûle son propre contexte et ne
   remonte que sa conclusion. Inutile quand le fichier visé est déjà connu.
4. **Externaliser l'état.** Un travail qui s'étale sur plusieurs tours tient son
   état dans `.claude/state/<tâche>.md`, pas dans le fil de la conversation.
   L'état survit ainsi à une compaction.
5. **Ne pas sonder ce qui est déjà notifié.** Attendre une commande longue se
   fait avec un Bash en arrière-plan à condition de sortie
   (`until <condition>; do sleep 0.5; done`) ou un `Monitor` filtré — jamais une
   boucle qui rejoue le contexte. Voir `.claude/loops-token-optimization.md`.

## Boucles (`/loop`)

Une boucle n'est acceptée qu'avec les quatre éléments suivants, sinon demander
les manquants avant de la lancer :

- une **condition d'arrêt vérifiable** (une commande qui sort 0, pas « quand
  c'est bon ») ;
- la **commande de vérification** relancée à chaque tick ;
- le **fichier d'état** lu et écrit à chaque tick ;
- ce qui compte comme **`noop`** (tick sans changement).

Cadence : le délai correspond à la vitesse réelle de ce qui est surveillé. Un
job CI de 8 minutes se vérifie une fois à ~480 s, pas huit fois à 60 s. Une
boucle qui ne fait que doubler une notification existante se met à 1200 s ou
plus. Arrêter la boucle dès la condition atteinte.

## Livraison

- Signaler explicitement ce qui n'a pas été fait et pourquoi.
- Les tests qui échouent se rapportent avec leur sortie, jamais en les
  contournant.
- Pas de PR sans demande explicite.
