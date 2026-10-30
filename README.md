# Zulip PaperBot
A Zulip bot that watches your channels for paper links, replies with a summary of each paper (title, authors, abstract, link and official GitHub repo), and saves it to a Notion database and/or a Zotero group library.

![Zulip](readme_images/zulip_stream.png)

↓  

![Notion](readme_images/notion_database.png)

# Features
- **Supported links**
  - **arXiv**: `arxiv.org/abs/...` links and bare IDs such as `2401.12345` or `arXiv:2401.12345`. The official GitHub repo is looked up on Hugging Face Papers.
  - **OpenReview**: `openreview.net/forum?id=...` and `openreview.net/pdf?id=...` links.
  - **Other sites** (optional, via the [Zotero translation server](#5-optional-run-the-zotero-translation-server)): ACL Anthology, NeurIPS/PMLR/JMLR/CVF/AAAI/IJCAI proceedings, ACM, IEEE, Springer, Nature, Science, Cell, ScienceDirect, JNeurosci, bioRxiv/medRxiv, PubMed, Semantic Scholar, `doi.org` links and more. The full list is `zoteroTranslationHandler.DEFAULT_DOMAINS` in `src/paper_handlers.py`.
- **Databases** (each optional, see [Configuration](#configuration))
  - **Notion**: adds a row per paper. If the paper is already there, it adds the new channel, sharer and comment to the existing row.
  - **Zotero**: adds the paper to a group library, in a collection named after the channel, tagged with the sharer's name, with the Zulip message attached as a note. Papers already in the library are updated the same way.
- **Robust lookups**: arXiv requests are retried when the API is rate limiting. If it still fails, the bot falls back to the Zotero translation server (when running). When a lookup finds nothing useful, the bot posts nothing and logs the reason instead. Lookup errors (e.g. "the arXiv API is rate limiting requests") are posted in Zulip.

# Setup steps
## 1. Download the repo
  Download the code of this repository to the machine you want to run the bot from, and install the dependencies:
  ```bash
  pip install zulip notion-client pyzotero requests
  ```
## 2. Add a new bot on Zulip
  On Zulip go to `Personal settings/Bots` and add a new bot of type `Generic`. You can configure the name and avatar of the bot as you prefer. Note the bot's email and API key for the [configuration](#configuration), along with the URL of your Zulip site.
  Then go to the bot, `Edit bot`, then `Channels`, and subscribe the bot to all the channels you want it to listen to.
## 3. (Optional) Set up Notion
  1. Go [here](https://www.notion.so/my-integrations) and add a `new integration`, selecting the workspace of your database as the `Associated workspace`. Its `Internal Integration Secret` is your `NOTION_TOKEN`.
  2. Create a database on Notion with the following columns (in any order; additional columns are fine):

     | Column | Type |
     |---|---|
     | `Name` | Title |
     | `Link` | URL |
     | `Code` | URL |
     | `Authors` | Text |
     | `Published` | Number (the year) |
     | `Shared on Zulip by` | Multi-select |
     | `Zulip stream(s) source` | Multi-select |
     | `Source` | Multi-select |
     | `BibTeX` | Text |
     | `Comments` | Text |

  3. The database id is in the database's URL, `https://www.notion.so/{chars}/{database_id}?v={chars}`. That's your `NOTION_DATABASE_ID`.
  4. Click the three dots in the upper right of the database and add your integration under `Connections`.
## 4. (Optional) Set up Zotero
  The bot saves papers to a Zotero **group** library.
  1. The group ID is the number in the group's URL, `https://www.zotero.org/groups/{group_id}/...`. That's your `ZOTERO_GROUP_ID`.
  2. Create an API key at [zotero.org/settings/keys](https://www.zotero.org/settings/keys) with read/write access to that group. That's your `ZOTERO_API_KEY`.
## 5. (Optional) Run the Zotero translation server
  To support papers from sites other than arXiv and OpenReview, run [Zotero's translation server](https://github.com/zotero/translation-server) on the same machine as the bot. It also serves as the fallback when the arXiv API is unavailable. It needs Node.js 22 or later.

  `apt install nodejs` installs an older version on Debian/Ubuntu (e.g. Node 18 on Debian 12), with which the server fails to start (`ERR_REQUIRE_ESM`). Install Node 22 from NodeSource instead, removing the distro packages first since they conflict:
  ```bash
  sudo apt remove -y nodejs npm
  curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
  sudo apt install -y nodejs   # includes npm
  node --version               # should print v22.x
  ```
  On macOS use `brew install node@22`; for other systems see [nodejs.org](https://nodejs.org/en/download).

  Then install and start the server:
  ```bash
  git clone --recurse-submodules https://github.com/zotero/translation-server
  cd translation-server
  npm install
  echo '{ "host": "127.0.0.1" }' > config/local.json   # listen on localhost only (the default is all interfaces)
  npm start
  ```
  The `--recurse-submodules` is needed, the site translators are a submodule. The bot expects the server at `http://localhost:1969`. To run it as a service that starts on boot, see [Hosting on a Google Cloud free-tier VM](#hosting-on-a-google-cloud-free-tier-vm) below.
  If the server isn't running, the bot replies that it is unreachable for those links and keeps handling arXiv and OpenReview links as usual.
## 6. Configure and run the bot
  Create `src/config.py` as described in [Configuration](#configuration), then run the bot from the `src` folder:
  ```bash
  python main.py
  ```

# Configuration
All settings go in `src/config.py`, which is gitignored since it holds your credentials:
```python
# Required
ZULIP_EMAIL = "paperbot-bot@yourorg.zulipchat.com"
ZULIP_API_KEY = "..."
ZULIP_SITE = "https://yourorg.zulipchat.com"

# Notion (optional): leave empty or remove to disable
NOTION_TOKEN = "..."
NOTION_DATABASE_ID = "..."

# Zotero (optional): leave empty or remove to disable
ZOTERO_API_KEY = "..."
ZOTERO_GROUP_ID = "..."
```
A database is disabled if any of its settings is empty or missing, and the bot says so in its log at startup.

# Hosting on a Google Cloud free-tier VM
The bot only makes outgoing connections, so a small always-on VM is enough. Google Cloud's [free tier](https://cloud.google.com/free/docs/free-cloud-features#compute) includes one `e2-micro` VM per month. These steps run both the bot and the (optional) Zotero translation server on it as systemd services.

## 1. Create the VM
  In the Google Cloud console go to `Compute Engine/VM instances` and create an instance with:
  - **Region**: one of the free-tier regions, `us-west1`, `us-central1` or `us-east1`.
  - **Machine type**: `e2-micro`.
  - **Boot disk**: Debian 12, **Standard persistent disk**, up to 30 GB. The default disk type (Balanced) is *not* covered by the free tier.
  - **Firewall**: leave HTTP/HTTPS traffic unticked. The bot needs no inbound ports apart from SSH.

  The free-tier terms change from time to time (e.g. charges for external IPv4 addresses), so check the current limits on the page linked above and set up a budget alert under `Billing/Budgets & alerts` to catch unexpected charges.

  Connect with the `SSH` button in the console, or `gcloud compute ssh <instance name>`.

## 2. Add swap
  An `e2-micro` has 1 GB of RAM, which can run out while installing packages. Add 1 GB of swap:
  ```bash
  sudo fallocate -l 1G /swapfile && sudo chmod 600 /swapfile
  sudo mkswap /swapfile && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
  ```

## 3. Install the bot
  ```bash
  sudo apt update && sudo apt install -y git python3-venv
  sudo git clone https://github.com/anandtrex/ZulipNotionPaperBot /opt/paperbot
  sudo chown -R $USER: /opt/paperbot
  python3 -m venv /opt/paperbot/venv
  /opt/paperbot/venv/bin/pip install zulip notion-client pyzotero requests
  ```
  Create `/opt/paperbot/src/config.py` with your credentials (see [Configuration](#configuration) above), readable only by you:
  ```bash
  nano /opt/paperbot/src/config.py
  chmod 600 /opt/paperbot/src/config.py
  ```
  ```python
  ZULIP_EMAIL = "..."
  ZULIP_API_KEY = "..."
  ZULIP_SITE = "https://yourorg.zulipchat.com"
  NOTION_TOKEN = "..."         # leave empty to disable Notion
  NOTION_DATABASE_ID = "..."
  ZOTERO_API_KEY = "..."       # leave empty to disable Zotero
  ZOTERO_GROUP_ID = "..."
  ```

## 4. (Optional) Install the Zotero translation server
  The translation server needs Node.js 22 or later; Debian's own `nodejs` package is too old. Install Node from NodeSource and the server from source (the `--recurse-submodules` is needed, the site translators are a submodule):
  ```bash
  curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
  sudo apt install -y nodejs
  sudo git clone --recurse-submodules https://github.com/zotero/translation-server /opt/translation-server
  sudo chown -R $USER: /opt/translation-server
  cd /opt/translation-server && npm install
  ```
  By default the server listens on all interfaces. Restrict it to localhost:
  ```bash
  echo '{ "host": "127.0.0.1" }' > /opt/translation-server/config/local.json
  ```

## 5. Run everything as systemd services
  So that both start on boot and restart if they crash:
  ```bash
  sudo tee /etc/systemd/system/zotero-translation-server.service > /dev/null <<EOF
  [Unit]
  Description=Zotero translation server
  After=network-online.target
  Wants=network-online.target

  [Service]
  User=$USER
  WorkingDirectory=/opt/translation-server
  ExecStart=/usr/bin/npm start
  Restart=on-failure

  [Install]
  WantedBy=multi-user.target
  EOF

  sudo tee /etc/systemd/system/paperbot.service > /dev/null <<EOF
  [Unit]
  Description=Zulip paper bot
  After=network-online.target zotero-translation-server.service
  Wants=network-online.target

  [Service]
  User=$USER
  WorkingDirectory=/opt/paperbot/src
  ExecStart=/opt/paperbot/venv/bin/python main.py
  Restart=on-failure
  RestartSec=10

  [Install]
  WantedBy=multi-user.target
  EOF

  sudo systemctl daemon-reload
  sudo systemctl enable --now zotero-translation-server paperbot
  ```
  Skip the first unit (and drop it from the `enable` line) if you're not using the translation server.

## 6. Check that it works
  ```bash
  systemctl status paperbot zotero-translation-server --no-pager
  sudo ss -ltnp | grep 1969      # should show 127.0.0.1:1969 only
  journalctl -u paperbot -f      # the bot's log
  ```
  Then post a paper link in a stream the bot is subscribed to. If a link gets no reply, the bot's log says why (e.g. `No info returned for ID ... Details: ...`).

## Updating
  ```bash
  cd /opt/paperbot && git pull && sudo systemctl restart paperbot
  cd /opt/translation-server && git pull --recurse-submodules && npm install && sudo systemctl restart zotero-translation-server
  ```
  Updating the translation server now and then keeps its site translators current.
