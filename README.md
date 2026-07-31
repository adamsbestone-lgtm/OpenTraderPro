# OpenTrader Pro

Plateforme de trading professionnelle open source orientée **Order Flow /
DOM**, conforme au cahier des charges : Python 3.13, PySide6, architecture
GUI → Widgets → EventBus → 7 Engines (Market, Order, Position, Risk, Bot,
Plugin, Broker).

## Installation

```bash
python3.13 -m venv venv
source venv/bin/activate        # Windows : venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Générer un .exe Windows

Voir la section dédiée plus bas ("Générer un .exe Windows").

## Architecture

```
GUI (MainWindow, DockManager, Theme)
 │
 ▼
Widgets (DOM, TimeSales, Orders, Positions, Account, Alerts, News,
          EventLog, AddonManager, HFT)
 │
 ▼
EventBus (Core/EventBus.py)
 │
 ├── MarketEngine    (Engines/MarketEngine.py)
 ├── OrderEngine     (Engines/OrderEngine.py)
 ├── PositionEngine  (Engines/PositionEngine.py)
 ├── RiskEngine      (Engines/RiskEngine.py)
 ├── BotEngine       (Engines/BotEngine.py)
 ├── PluginEngine    (Engines/PluginEngine.py)
 └── BrokerEngine    (Brokers/BrokerEngine.py)
```

## Fenêtres disponibles au lancement

DOM, Time & Sales, Orders (Actifs/Exécutés/Historique), Positions,
Account, Alerts, News, Event Log, **Add-ons** (gestionnaire de plugins
à chaud), **HFT** (tableau de bord haute fréquence).

### Fenêtre Add-ons

Liste tous les plugins découverts dans `Plugins/<Nom>/` (via `plugin.json`
+ `plugin.py`), avec case à cocher pour charger/décharger à chaud sans
redémarrer l'application. Les plugins `Replay` et `Order Flow Suite`
fournis ajoutent chacun leur propre dock au chargement.

### Fenêtre Order Flow (plugin `Order Flow Suite`)

Portage Python complet de notre add-on Bookmap "ES Order Flow (custom)"
(écrit initialement en Java pour l'API Simplified de Bookmap). La logique
de détection (`Plugins/OrderFlowSuite/{model,state,detectors}.py`) est un
portage fidèle, sans dépendance à Bookmap ni à Qt — seule la couche
d'intégration (`plugin.py`, `widget.py`) est spécifique à OpenTrader Pro.

11 concepts détectés en direct sur le flux de marché (simulé ou réel) :
1. **Imbalance empilée** — ratio diagonal ask(P)/bid(P+1) sur plusieurs niveaux
2. **Absorption/iceberg** — avec classification bloc vs fragmentée
3. **Sweep** — rafale multi-niveaux
4. **Cascade de stops** — rafale de petits prints indépendants
5. **Out-of-spread** — exécutions au-delà du bid/ask affiché
6. **Zone défendue** — niveau qui se recharge après attaques répétées
7. **Inside print** — déséquilibre acheteur/vendeur exécuté au meilleur bid/ask
8. **Reliquat post-sweep** — corrélation sweep + nouveau niveau passif (inférence, pas certitude)
9. **Sweep + Défense** — reversal-context ou continuation
10. **Confirmation croisée** — entre deux symboles corrélés (ex. ES/MES), via un registre partagé
11. **Score de confluence** — accord entre plusieurs types de signaux distincts

La fenêtre a 3 onglets : **Signaux** (flux en direct), **Réglages** (tous
les seuils ajustables à chaud, sans recompiler), **Exécution** (boutons
Buy/Sell manuels, quantité, et bascule "trading automatique" — protégée
par une boîte de dialogue de confirmation avant activation, comme dans
la version Bookmap d'origine).

**Adaptations par rapport à la version Bookmap**, documentées en tête de
`plugin.py` : le DOM d'OpenTrader Pro livre des snapshots complets (pas
des deltas par niveau comme Bookmap), donc un diff est calculé à chaque
cycle ; le reliquat post-sweep (`OrderReuseDetector`) est nourri par une
approximation (apparition d'un niveau significatif) faute de vrai MBO
dans le flux simulé — déjà présenté comme une inférence et non une
certitude, fidèlement à l'avertissement du README Java original.

### Fenêtre HFT

Tableau de bord de supervision haute fréquence :
- débit du flux marché (ticks/s, mises à jour de profondeur/s)
- débit d'ordres envoyés/s avec alerte visuelle si le seuil indicatif est dépassé
- latence moyenne ordre → accusé de réception broker
- spread et déséquilibre du carnet (bid/ask imbalance)
- bouton **Mode HFT** (surveillance renforcée)
- lanceur rapide des bots marqués `"hft": true` dans leur `bot.json`
  (un exemple `MarketMakerHFT` est fourni : cote en continu, annule/replace
  à chaque tick de profondeur — usage pédagogique uniquement)

## Ce qui est déjà implémenté

| Domaine | État |
|---|---|
| EventBus, Database SQLite (WAL), Settings, chiffrement des identifiants (Fernet) | ✅ |
| MarketEngine (flux simulé + recorder vers SQLite) | ✅ |
| OrderEngine (Market/Limit/Stop/StopLimit/MIT/Bracket ; OCO/TrailingStop : structure prête) | ✅ |
| PositionEngine (P&L, Reverse/Close/Flatten/Scale In/Scale Out) | ✅ |
| RiskEngine (perte max jour/compte, taille max, nb max ordres, verrouillage, **Kill Switch**) | ✅ |
| BotEngine + API `Strategy` (on_start/on_tick/on_depth/on_bar/on_order/on_position/on_timer/on_stop) | ✅ + `Scalper` et `MarketMakerHFT` fournis |
| PluginEngine + API `PluginBase` | ✅ + plugins `Replay` et `Order Flow Suite` fournis |
| BrokerEngine multi-broker + `BaseBroker` (interface commune) | ✅ |
| SimBroker (fonctionnel) | ✅ |
| Tradovate/Rithmic/CQG/InteractiveBrokers/Binance/Bybit/Bitget/Kraken/Coinbase | 🔲 squelettes `StubBroker` prêts (voir `Brokers/FuturesBrokers.py`, `Brokers/CryptoBrokers.py`) — nécessitent vos identifiants + SDK officiels |
| ReplayEngine (relecture x1/x2/x4/x10/x100, pause, avance/retour) | ✅ |
| Recorder (ticks + profondeur → SQLite) | ✅ (branché automatiquement dans MarketEngine) |
| Docking, multi-écran, sauvegarde/restauration/import/export de layouts | ✅ |
| Thème dark_blue | ✅ (architecture multi-thème prête, `GUI/Theme.py`) |
| Kill Switch | ✅ (bouton Account + toolbar) |
| ZeroMQ | 🔲 prévu pour un déploiement distribué (GUI/moteur séparés en process) — l'EventBus actuel est in-process |
| NumPy/Numba | 🔲 non utilisés pour l'instant — à intégrer sur vos calculs intensifs (indicateurs, agrégations) |
| Tests unitaires/intégration/performance | 🔲 non fournis dans ce socle — voir "Prochaines étapes" |

## Écrire un bot

`Bots/MonBot/bot.json` + `Bots/MonBot/strategy.py` :

```python
from Bots.Strategy import BaseStrategy
from Engines.OrderEngine import Order, OrderType, OrderSide

class Strategy(BaseStrategy):
    def on_tick(self, tick):
        ...
```

Ajoutez `"hft": true` dans `params` de `bot.json` pour qu'il apparaisse
aussi dans la fenêtre **HFT**.

## Écrire un plugin (add-on)

`Plugins/MonPlugin/plugin.json` + `Plugins/MonPlugin/plugin.py` :

```python
from Plugins.PluginBase import PluginBase

class Plugin(PluginBase):
    def on_load(self):
        # ajoutez un dock, un menu, un raccourci via self.main_window
        ...
```

Il apparaît automatiquement dans la fenêtre **Add-ons** au lancement suivant.

## Implémenter un broker réel

Héritez `Brokers/BaseBroker.py` (voir `Brokers/SimBroker.py` comme modèle
complet, ou `Brokers/StubBroker.py` comme squelette). Enregistrez la
classe dans `AVAILABLE_BROKERS` (`Brokers/BrokerEngine.py`). Recommandé :
`ccxt` pour les brokers crypto (Binance/Bybit/Bitget/Kraken/Coinbase),
SDK officiel pour Tradovate/Rithmic/CQG/IB.

## Générer un .exe Windows sans machine Windows (recommandé)

Le dépôt contient déjà `.github/workflows/build-windows.yml`, un workflow
GitHub Actions qui compile `OpenTraderPro.exe` automatiquement **dans le
cloud**, sur un runner Windows gratuit fourni par GitHub. Vous n'avez
besoin d'aucune installation locale, juste d'un compte GitHub.

1. Créez un dépôt GitHub (public ou privé) et poussez-y ce projet :
   ```bash
   cd OpenTraderPro
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/<votre-compte>/<votre-repo>.git
   git push -u origin main
   ```
2. Sur GitHub, ouvrez l'onglet **Actions** du dépôt : le workflow
   "Build Windows executable" se déclenche automatiquement au push
   (ou lancez-le manuellement via **Run workflow**).
3. Une fois le job terminé (quelques minutes), ouvrez le run puis la
   section **Artifacts** en bas de page : téléchargez `OpenTraderPro-windows.zip`.
   Il contient `OpenTraderPro.exe` prêt à l'emploi (dossier complet,
   à décompresser et lancer — aucun Python requis sur la machine cible).

## Générer un .exe Windows localement (alternative)

**Sur une machine Windows** (le build ne se cross-compile pas depuis
Linux/macOS) :

1. Double-cliquez `build_exe.bat` → crée le venv, installe les
   dépendances + PyInstaller, compile via `packaging\OpenTraderPro.spec`.
   Résultat : `dist\OpenTraderPro\OpenTraderPro.exe` (autonome, pas besoin
   de Python installé côté utilisateur final).
2. *(Optionnel)* Installez [Inno Setup](https://jrsoftware.org/isinfo.php),
   ouvrez `packaging\installer.iss`, cliquez **Compile** → génère
   `packaging\Output\OpenTraderProSetup.exe`, l'installeur final.

Placez une icône `opentraderpro.ico` dans `packaging\` avant le build
pour personnaliser l'icône de l'exe.

## Prochaines étapes suggérées

1. Implémenter un premier broker réel (SimBroker → Tradovate en priorité, API bien documentée).
2. Finaliser OCO/TrailingStop (annulation croisée automatique côté OrderEngine).
3. Ajouter un agrégateur de bougies (`on_bar`) alimenté par MarketEngine, avec Polars pour les calculs de profil de volume.
4. Utiliser Numba pour accélérer les calculs intensifs (indicateurs, P&L sur gros volumes).
5. Si scaling multi-process : remplacer les signaux Qt internes de l'EventBus par des sockets ZeroMQ (PUB/SUB), l'API `publish/subscribe` reste identique côté widgets.
6. Écrire les tests unitaires/intégration (pytest + qtbot pour la partie GUI) et un test de performance du DOM à 120 FPS avec un flux simulé haute fréquence.
