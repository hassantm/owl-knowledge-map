# OWL Knowledge Map — Anvil App

This worktree (`anvil-app` branch) holds the Anvil web application code.

## What belongs here

All Anvil UI code:
- `anvil.yaml` — app manifest (created/managed by Anvil IDE)
- `client_code/` — form Python files (one directory per form)
- `server_code/` — thin Anvil server module stubs

## What does NOT belong here

Backend code stays on `main`:
- `src/uplink.py` — all server-callable functions
- `src/graph_builder.py`, `src/batch_process.py`, etc.
- `db/` — SQLite database
- `docs/` — project documentation

## Setup sequence

1. Create a new Anvil app at anvil.works
2. Enable the **Users** service → add `role` column (Text) to the users table
3. Enable **Uplink** → copy the key → `export ANVIL_UPLINK_KEY='...'`
4. **Settings → Version History → Connect to GitHub** → select this repo, branch `anvil-app`
5. Anvil will push the initial app structure to this branch
6. After sync, copy form code from `../owl-knowledge-map/docs/anvil_forms/` into each form

## Reference documentation

- Form-by-form design: `../owl-knowledge-map/docs/20260226_anvil_app_build.md`
- Architecture overview: `../owl-knowledge-map/docs/20260226_anvil_architecture.md`
- Uplink functions: `../owl-knowledge-map/src/uplink.py`

## Starting the uplink

```bash
# From the main worktree
export ANVIL_UPLINK_KEY='your-key-here'
python src/uplink.py
```
