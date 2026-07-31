# Scalper (bot d'exemple)

Détecte une rafale de `aggressive_window` trades agressifs consécutifs du
même côté sur le Time & Sales, puis entre au marché avec un bracket
(stop + target exprimés en ticks).

## Paramètres (`bot.json`)

| Paramètre | Rôle |
|---|---|
| `symbol` | Symbole tradé |
| `quantity` | Taille de l'entrée |
| `aggressive_window` | Nombre de trades agressifs consécutifs déclenchant l'entrée |
| `target_ticks` / `stop_ticks` | Objectif / stop en ticks |
| `tick_size` | Valeur d'un tick pour ce symbole |
| `cooldown_ticks` | Nombre de trades à attendre avant une nouvelle entrée |

## Avertissement

Ceci est un exemple pédagogique pour illustrer l'API `Strategy`, pas une
stratégie de trading validée. Testez toujours en simulation avant tout
usage réel.
