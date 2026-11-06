# Deployment

Target: one Debian-like machine, one process, SQLite on local disk.

## Native

```bash
sudo useradd --system --create-home --home-dir /opt/stipula stipula
sudo mkdir -p /opt/stipula
sudo rsync -a ./ /opt/stipula/
sudo chown -R stipula:stipula /opt/stipula
sudo -u stipula bash -lc 'cd /opt/stipula && scripts/install.sh'
sudoedit /opt/stipula/.env   # BOT_TOKEN, BOT_OWNER_ID, LOG_SALT
sudo cp deploy/stipula.service /etc/systemd/system/stipula.service
sudo systemctl daemon-reload
sudo systemctl enable --now stipula
sudo journalctl -u stipula -f
```

The unit runs `python -m telegram_innovation run` as `stipula`, with `NoNewPrivileges` and `PrivateTmp`. Logs also rotate in `LOG_PATH` if you set one.

Health from the host, without printing the token:

```bash
sudo -u stipula bash -lc 'cd /opt/stipula && set -a && . ./.env && set +a && .venv/bin/python -m telegram_innovation check --offline'
```

That checks the database and the pinned hash. It does not call Telegram. A bad token shows up when the service fails to poll; journald gets `bot_starting` and then an API error class, not the token.

## Docker

The image does not contain a token. Mount a data volume and pass the environment.

```bash
docker build -f deploy/Dockerfile -t stipula .
docker run --rm -d --name stipula \
  -e BOT_TOKEN -e BOT_OWNER_ID -e LOG_SALT \
  -v stipula-data:/data \
  stipula
```

## Not supported

- Two containers polling the same token.
- Webhooks. Polling needs no inbound port.
- A network database. If you outgrow one SQLite file, that is a later design, not a connection-string change.
