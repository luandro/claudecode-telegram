# PRD - Docker Compose + HTTPS + Telegram Allowlist

This PRD outlines the tasks to deploy the Telegram bridge behind a reverse proxy with HTTPS on `coder.luandro.com`, and restrict bot control to a DM allowlist.

## Project Setup

- [x] Create `docker-compose.yml` with `bridge` and `caddy` services
- [x] Add `Caddyfile` for `coder.luandro.com` with reverse proxy to bridge
- [x] Add `.env` template or document required env vars
- [x] Confirm Docker network isolates `bridge` from public access

## Core Features

- [x] Configure `bridge` service to listen only on internal network
- [x] Expose ports 80/443 only on `caddy`
- [x] Ensure HTTP redirects to HTTPS
- [x] Verify reverse proxy forwards to bridge

## Telegram Webhook Security

- [x] Generate a long random `WEBHOOK_PATH`
- [x] Set `TELEGRAM_WEBHOOK_SECRET` and validate `X-Telegram-Bot-Api-Secret-Token`
- [x] Configure `setWebhook` for `https://coder.luandro.com/<WEBHOOK_PATH>`
- [x] Verify `getWebhookInfo` reports OK

## Telegram DM Allowlist

- [x] Add `ALLOWED_TELEGRAM_USER_IDS` to configuration
- [x] Parse allowlist into integers on startup
- [x] Allow only DM updates from user `244055394`
- [x] Ignore unauthorized users safely (200 OK, no action)

## Documentation

- [ ] Document env vars: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `WEBHOOK_PATH`, `DOMAIN`, `ALLOWED_TELEGRAM_USER_IDS`
- [ ] Add Docker Compose startup steps to `README.md`
- [ ] Note that tokens must not be committed

## Testing & QA

- [ ] Compose up: `docker compose up -d` completes without errors
- [ ] HTTP redirect: `curl -I http://coder.luandro.com` redirects to HTTPS
- [ ] HTTPS: `curl -I https://coder.luandro.com` returns a valid response
- [ ] Secret token: wrong/missing secret is ignored; correct secret is accepted
- [ ] Allowlist: user `244055394` works; another user is ignored
- [ ] Telegram end-to-end: webhook set, DM reaches tmux, response sent back

## Deployment

- [ ] DNS: `coder.luandro.com` points to server IPv4
- [ ] Start stack on Ubuntu server
- [ ] Run QA checklist before normal use
- [ ] Verify webhook status after deployment
