# Deployment status

The hosted service is inactive. On 2026-10-10, the configured Cloudflare account had no `cstd-help` Pages project, no `cstd-help-api` Worker, and no matching review KV namespace or Worker route. The old deployment workflow was still running on pushes and failed because its KV binding no longer existed.

Pushes and pull requests now run tests, Python compilation, and static-site validation. Cloudflare deployment steps and both on-demand remote cache workflows require the repository variable `CLOUDFLARE_DEPLOY_ENABLED` to be exactly `true`. Leaving it unset or setting it to `false` keeps all of these cloud writes disabled.

The checked-in Wrangler configuration is retained for local development and as a historical deployment reference. Its namespace ID and domain route are not evidence of live resources. Local preview does not restore the hosted service; live refresh and review requests depend on the disabled remote jobs.

## Restore hosting deliberately

1. Provision or select a Worker, Pages project, KV namespace, and domain route in the intended Cloudflare account.
2. Update `wrangler.toml` and the namespace IDs in both on-demand workflows to match those resources.
3. Configure the Cloudflare credentials and application secrets described in [the maintenance reference](MAINTENANCE.md).
4. Set `CLOUDFLARE_DEPLOY_ENABLED=true` in the repository's Actions variables and manually run the deployment workflow.
5. Verify the Worker API and Pages site before advertising a live URL again.

The historical report-generation workflow is separate: it only updates repository files and does not deploy to Cloudflare.
