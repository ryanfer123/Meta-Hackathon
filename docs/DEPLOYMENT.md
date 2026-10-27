# Public replay deployment

The public source is published. GitHub Pages built the app successfully but could not create the Pages site: `Resource not accessible by integration`. No live URL is claimed yet.

A Render static deployment is prepared with:
- Repository: https://github.com/ryanfer123/Meta-Hackathon
- Branch: main
- Build: `cd frontend && npm ci && npm run build`
- Publish path: `frontend/dist`
- Node: 22
- Public synthetic replay only; no model key, inference server or GPU.

The connected Render workspace selection is awaiting confirmation. The connector requires a confirmed workspace ID before creating the site.

An alternate Pages workflow is included. After Pages has been enabled for GitHub Actions in repository settings, set repository variable `DEPLOY_GITHUB_PAGES=true`; the next push or a manual dispatch deploys it. It stays skipped until configured, so it does not repeatedly fail on an unavailable permission.

The Dockerfile can serve the full UI and FastAPI together on port 8000 for a private live instance. No backend cloud service or GPU was started during the key-free build.
