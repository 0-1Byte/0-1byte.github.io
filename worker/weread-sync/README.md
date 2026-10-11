# Private WeRead Sync Console

The complete WeRead dataset is stored only in private Cloudflare D1. The
repository and GitHub Pages contain no WeRead dataset. The homepage requests one
random, allowlisted quote from the Worker; the public endpoint is read-only and
rate limited. Individual quotes returned to visitors are public, so rate
limiting reduces bulk scraping but cannot make returned quote text confidential.

## Local Hugo preview

For a local-only preview, run the standard-library development service in one
terminal:

```powershell
py -3.12 .\tools\dev_weread_quote_server.py
```

In another terminal, start Hugo bound to loopback:

```powershell
.\hugo.exe server --bind 127.0.0.1 --port 1313
```

Open `http://localhost:1313/?wereadDev=1` (or
`http://127.0.0.1:1313/?wereadDev=1`). The browser uses the local server only
when both the hostname is loopback and the explicit `wereadDev=1` query
parameter is present. The Python service binds only to `127.0.0.1:8765`,
validates the local dataset, and returns one random quote with the same public
field allowlist as the Worker. It does not copy the dataset into Hugo output or
the static directory. If it is stopped or rejects the data, the homepage
falls back to a manual quote. This is a development convenience, not a
production interface or privacy boundary; production continues to use the
Worker and private D1.

## Data flow

1. The authenticated console dispatches the fixed `sync-weread.yml` workflow.
2. GitHub Actions synchronizes into `$RUNNER_TEMP`, validates the full dataset,
   runs offline checks, and builds/verifies a manual-only homepage.
3. `publish_weread_quotes.py` uploads validated chunks to the Worker over HTTPS.
   Each chunk is size-limited and idempotent. The Worker validates the whole
   staged dataset, writes a new D1 version, verifies its count, and switches the
   active-version pointer only after all rows are stored.
4. The Worker exposes only `text`, `source_type`, `source`, `author`, and
   `chapter` from one random active record. Internal IDs and other attributions
   remain in private D1 and are never returned to the browser.

An incomplete, empty, malformed, duplicate, or oversized upload does not
replace the current active dataset. Failed staging uploads are marked stale
after 90 minutes and cleaned up on the next upload start. Cleanup of inactive
D1 versions is attempted after activation; if cleanup fails, the newly
activated dataset remains valid and the orphaned version may need later
maintenance.

## GitHub configuration

Create a GitHub OAuth App:

- Homepage URL: `https://0-1byte.github.io/admin/weread-sync/`
- Authorization callback URL: `<WORKER_ORIGIN>/auth/callback`, for example
  `https://weread-sync-console.<account-subdomain>.workers.dev/auth/callback`

Configure this repository variable:

- `WEREAD_SYNC_API_BASE`: the Worker HTTPS origin, with no path or trailing
  slash. It must exactly match `WORKER_ORIGIN` in `wrangler.toml` and use the
  `https://weread-sync-console.<account-subdomain>.workers.dev` host.
- `WEREAD_SYNC_REPORT_URL`: `<WORKER_ORIGIN>/internal/report`.

Configure these repository Actions secrets:

- `WEREAD_API_KEY`: WeRead Skills API key used only by the workflow.
- `WEREAD_UPLOAD_SECRET`: a dedicated random secret matching the Worker
  `UPLOAD_SECRET`; do not reuse the report or session secret.
- `WEREAD_SYNC_REPORT_SECRET`: a separate random secret matching the Worker
  `REPORT_SECRET`.

`WEREAD_PUBLISH_TOKEN` is no longer required: the workflow does not commit or
push the dataset. Remove that old secret after confirming no other workflow
uses it. The workflow's `GITHUB_TOKEN` permission is `contents: read`; it does
not receive write permissions.

## Cloudflare configuration

1. Create a D1 database named `weread-private-quotes`. Set its generated ID in
   `worker/weread-sync/wrangler.toml` at `database_id`.
2. Apply `migrations/0001_private_quotes.sql` to that database before deploying.
3. Set `PUBLIC_QUOTE_LIMITER` to a unique positive integer namespace ID for
   this Cloudflare account (the sample `1001` must be checked/replaced if used
   elsewhere). The configured limit is 30 requests per 60 seconds per
   Cloudflare location and client key.
4. Keep the fixed `SITE_ORIGIN`, repository, workflow, and branch values.
   Configure `ADMIN_GITHUB_LOGIN` for the sole allowed GitHub account.
5. Create Worker secrets:

   - `GITHUB_TOKEN`: narrowly scoped token for reading Actions status and
     dispatching the fixed workflow; grant only this repository `Actions: read`
     and `Actions: write` plus required read-only repository metadata access.
   - `GITHUB_OAUTH_CLIENT_ID`
   - `GITHUB_OAUTH_CLIENT_SECRET`
   - `SESSION_SECRET`: independent random session-signing secret.
   - `REPORT_SECRET`: independent random callback secret for task summaries.
   - `UPLOAD_SECRET`: independent random upload bearer secret; never reuse
     `REPORT_SECRET`.

Enable `workers.dev` for the Cloudflare account, then set the same canonical
origin in `wrangler.toml` (`WORKER_ORIGIN`), the GitHub repository variable
(`WEREAD_SYNC_API_BASE`), and `static/admin/weread-sync/config.js`. The Worker
rejects OAuth requests sent to an origin other than the pinned one, and the
uploader refuses any target that differs from the pin or is not the expected
Worker name under `workers.dev`. The OAuth callback URL is exactly
`<WORKER_ORIGIN>/auth/callback`. No secret belongs in the public config file.

## Safe rollout order

1. Merge only the reviewed code files; do not publish `data/weread_quotes.json`
   or unrelated worktree files.
2. Create the D1 database, apply the migration, reserve a rate-limit namespace,
   configure the Worker secrets/vars, and deploy the Worker.
3. Create the OAuth App and set its callback to the deployed Worker host.
4. Configure the GitHub variable and Actions secrets above. Do not add a
   publish token.
5. Set the public Worker origin in the static config and publish the site.
6. Run workflow `mode=check`. It must not call WeRead, upload data, or write to
   the repository.
7. Test wrong-account OAuth rejection, session/CSRF, status polling, an
   unauthorized upload rejection, public response field allowlisting, and
   rate limiting.
8. Only after those checks, run one real sync. GitHub-hosted access to the
   official WeRead gateway remains an external prerequisite and is checked
   before downloading the full dataset.

Local offline tests use synthetic quotes only. OAuth, Cloudflare D1, the
Worker deployment, GitHub dispatch, and GitHub-hosted WeRead network access
remain unverified until configured and tested on those services.
