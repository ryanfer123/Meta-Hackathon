# Public replay deployment

Live replay: https://apprentice-meta.onrender.com

Render reports deployment `dep-dbgcuji9lscs739n0s80` live for source commit `4a0d842515f1fc1edd93df7b5c7d036749672cde`. The public site serves six synthetic examples. No model key, inference server or GPU is present in this deployment.

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
