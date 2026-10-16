# Zulip PaperBot
Zulip paper bot that saves papers (currently arxiv & openreview) and their info in a Notion database when their link is posted in Zulip.

![Zulip](readme_images/zulip_stream.png)

↓  

![Notion](readme_images/notion_database.png)

# Setup steps
## 1. Download Repo:
  Download the code of this repository to the machine you want to run the bot from
## 2. Add a new bot on Zulip:
  On Zulip go to the upper right corner to `Settings/Personal settings/Bots` and add a new bot. Choose bot type `Generic`. Add the `BOT EMAIL` as `ZULIP_EMAIL` in the `config.py`, and the `API KEY` under `ZULIP_API_KEY`. You can configure the name and avatar of the bot as you prefer. Then go to the Bot and `Edit bot`, then `Streams`. Now subscribe the bot to all the streams you want it to listen to.
## 3. Add the Zulip site
  Save the URL of the Zulip site you want to use the bot on under `ZULIP_SITE` in the `config.py`
## 4. Add connection to Notion
  Notion and Zotero are both optional: if any of a database's credentials in `config.py` are empty (or missing), that database is disabled. Zotero needs `ZOTERO_API_KEY` and `ZOTERO_GROUP_ID`.
  Go [here](https://www.notion.so/my-integrations) and add a `new integration`. Add the `Internal Integration Secret` as `NOTION_TOKEN` to the `config.py`.
  Select the workspace of the database you want to link to as the `Associated workspace`.
## 5. Create a database on Notion
  Create a database on Notion which must have the following columns:
  - `Name` having the Type `Title`
  - `URL` having the Type `URL`
  - `Code` having the Type `URL`
  - `Authors` having the Type `Multi-select`
  - `Shared by` having the Type `Multi-select`
  - `Published` having the Type `Date`
  - `Shared` having the Type `Date`
  - `Stream` having the Type `Multi-select`
  - `BibTeX` having the Type `Text`
    
  These can be in random order and additional columns can be added.
  The database id can be found in the url on Notion when being on the database page.
  The url is formatted in the following way `https://www.notion.so/{chars}/{database_id}?v={chars}`. Add the `database id` to the `config.py` as `NOTION_DATABASE_ID`.
## 6. Add the connection to the database
  Click the three dots in the upper right on your database and then under `Add connections` add your new connection.
## 7. (Optional) Run the Zotero translation server
  To support papers from other sites (ACL Anthology, NeurIPS/PMLR proceedings, ACM, IEEE, Springer, Nature, bioRxiv, PubMed, DOI links, ...), run [Zotero's translation server](https://github.com/zotero/translation-server) on the same machine as the bot. It needs Node.js 22 or later.

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
  The list of supported domains is `zoteroTranslationHandler.DEFAULT_DOMAINS` in `paper_handlers.py`. If the server isn't running, the bot replies that it is unreachable for those links and keeps handling arXiv and OpenReview links as usual.
## 8. Run the bot
  Install the dependencies with `pip install zulip notion-client pyzotero requests`, then run the bot using `python main.py` from the `src` folder.

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
  Create `/opt/paperbot/src/config.py` with your credentials (see the setup steps above), readable only by you:
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
