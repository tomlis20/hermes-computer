# After install

This plugin does **not** start a computer.

1. The supervisor + `docker.sock` is **root-equivalent**. Only continue if you trust this SHA.
2. `plugin-guard` may ask for confirmation (`caution`). That is expected (repo contains Docker runtime). `--force` skips the prompt, not the scan.
3. Put `COMPUTER_SUPERVISOR_TOKEN` in the supervisor compose `.env` and the **same** token plus `COMPUTER_SUPERVISOR_URL=http://hermes-computer-supervisor:9376` on **every** Hermes process (gateway and WebUI).
4. `docker compose -f deploy/docker-compose.yml up -d` from this plugin directory (or merge `deploy/compose.override.hermes-sidecar.yml`).
5. Run `hermes computer doctor` and **paste the FIX lines** it prints to merge `computer` into your existing `platform_toolsets`. Do not replace the list by hand.
6. `hermes plugins enable hermes-computer` if needed. Open a **new** chat.
7. Doctor must be green in the process you chat through.
