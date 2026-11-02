# Hosted development preview

The root `Dockerfile` builds React and serves its compiled assets alongside the
Flask API through `backend/deploy_wsgi.py`. Both use the same HTTPS origin, so
browser API calls use `/api` without a separate Vite server or CORS proxy.
Production session cookies are secure. This deployment uses its own newly
provisioned PostgreSQL database; local and existing business databases are not
copied into the image or used by this configuration.

## Render deployment

`render.yaml` defines a web service named `buildconnect-preview` and a separate
database named `buildconnect-preview-db`. It targets branch
`codex/hosted-preview`, generates application signing secrets on Render, and
reads `DATABASE_URL` from that new database's internal connection string.

1. Ensure the latest reviewed code, including `Dockerfile`, `render.yaml`, and
   `backend/deploy_wsgi.py`, is pushed to `codex/hosted-preview` in
   `Saddalivishnu/Buildconnect`. A workspace-only change or downloaded archive is
   not yet a GitHub deployment source.
2. Sign in to Render and connect the GitHub repository. Create a **Blueprint**
   from that repository and select `codex/hosted-preview` as the Blueprint
   branch. Review the two resources and their current pricing before creating
   them. The file requests free plans; do not switch to paid plans automatically
   if a free plan is unavailable for the account.
3. Wait for the image build and service health check to pass. Open the service
   URL shown by Render. Its exact hostname is assigned by Render, not assumed
   by this repository.
4. Create your own contractor and supplier test accounts to explore the app.
   The initial database also contains labeled research/demo data. Do not load
   real business records into this disposable preview.

For agent-managed deployment, provide a Render API key securely as the
`RENDER_API_KEY` environment credential with access to `api.render.com`. Never
paste API keys into chat, commit them, or put their values in this file.
The GitHub connection must also authorize Render to read the selected repository.
Preparing these files does not create services or establish a public URL.

Free web services can sleep when idle and cold starts can take time. Free
PostgreSQL databases can expire and have retention limitations. Provider plans,
limits, and account eligibility can change; verify the current terms in the
Render resource review. A durable production deployment needs a separately
reviewed database plan, backups, and operational setup.

## Update and preview cycle

After each requested change, run the backend tests and frontend build, then push
the reviewed update to `codex/hosted-preview`. Render is configured to deploy
each new commit on that branch. Wait for the deployment health check, then
reload the same Render URL. Changes that remain only in the agent's workspace
will not appear online. Keep this preview branch separate from `main` until
the changes are approved for integration.

## Container validation

Build from the repository root with `docker build -t buildconnect-preview .`.
In the managed cloud environment, retain its configured proxy and supply the
session CA using ephemeral BuildKit mounts:

```sh
docker build \
  --secret id=proxy_ca,src="$CODEX_PROXY_CERT" \
  --secret id=ca_bundle,src=/etc/ssl/certs/ca-certificates.crt \
  -t buildconnect-preview .
```

The secrets are optional for ordinary builders with trusted Internet access.
TLS verification remains enabled, and the session CA is not saved into image
layers. Run the resulting container with a separate disposable PostgreSQL
`DATABASE_URL` and a fresh `BUILDCONNECT_SECRET_KEY` of at least 32 characters.
No secret values belong in Docker build arguments or source files.

Verify `/api/health`, `/api/materials`, `/`, a React client route such as
`/procurement`, and the JavaScript/CSS assets before calling the preview ready.
