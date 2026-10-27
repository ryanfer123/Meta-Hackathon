# Public web deployment

Live replay: https://apprentice-meta.onrender.com

Render reports deployment `dep-dbgcuji9lscs739n0s80` live for source commit `4a0d842515f1fc1edd93df7b5c7d036749672cde`. The public site serves six synthetic examples. No model key, inference server or GPU is present in this deployment. Supabase separately provides authenticated persistence and private recording storage.

Configuration:
- Service: `apprentice-meta` (`srv-dbgcuj29lscs739n0qrg`)
- Repository: https://github.com/ryanfer123/Meta-Hackathon
- Branch: main, automatic deployment enabled
- Build: `cd frontend && npm ci && npm run build`
- Publish path: `frontend/dist`
- Node: 22
- Workspace: ryan's workspace

GitHub Pages built the app but could not create the Pages site: `Resource not accessible by integration`. Render is the active hosting provider. The alternate Pages workflow stays skipped until repository variable `DEPLOY_GITHUB_PAGES=true` is set after Pages has been enabled for GitHub Actions.

The Dockerfile can serve the full UI and FastAPI together on port 8000 for a private live instance. No backend cloud service or GPU was started during the key-free build. Real model inference and video validation remain pending owner-provided configuration and recordings.

## Homepage and cloud workspace revision

Render build variables include `VITE_STATIC_REPLAY=true`, `VITE_SUPABASE_URL` and the project publishable key. These are public client configuration; service role/model keys are absent. Values were merged into the existing service environment. Database project `ntuuztideqsdvuiiohlh` is active in ap-south-1 with three applied migrations. Auth Site URL and redirect allowlist use the production Render origin. See [Supabase setup](../supabase/README.md).

The homepage is `/`, the guest workstation is `/#/workspace`, and Learn/Audit/library are workspace views. Static samples continue to work without sign-in. Uploaded files remain private and staged until a separately configured inference service processes them.
