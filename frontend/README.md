# RoadLens Frontend

React dashboard shell for RoadLens operations.

## Run

```bash
bun install
bun run dev
```

The dev server uses `http://localhost:5173` and proxies `/api` to
`http://localhost:8000` by default.

On a new database, the first visit displays secure owner/workspace setup.
Afterward, users sign in to manage workspaces, team roles, cameras, zones,
rules, pipeline settings, and evidence. No default account or password is
stored in the repository.

Override the API proxy target when needed:

```bash
VITE_API_PROXY_TARGET=http://localhost:8000 bun run dev
```
