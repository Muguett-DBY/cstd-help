import json
from urllib.parse import urlparse

from workers import Response, WorkerEntrypoint

from worker.cloudflare_adapters import (
    AnalyzerGateway,
    CloudflareCache,
    CloudflareDotaGateway,
    GitHubEvidenceGateway,
    GitHubMatchRefreshGateway,
)
from worker.router import route_request
from worker.service import ReviewService


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        account_id = int(self.env.ACCOUNT_ID)
        cache = CloudflareCache(self.env.REVIEW_CACHE)
        dota = CloudflareDotaGateway()
        analyzer = AnalyzerGateway()
        evidence = GitHubEvidenceGateway(
            token=getattr(self.env, "GITHUB_DISPATCH_TOKEN", ""),
            repository=self.env.GITHUB_REPOSITORY,
            workflow=self.env.GITHUB_EVIDENCE_WORKFLOW,
            ref=self.env.GITHUB_EVIDENCE_REF,
        )
        match_refresh = GitHubMatchRefreshGateway(
            token=getattr(self.env, "GITHUB_DISPATCH_TOKEN", ""),
            repository=self.env.GITHUB_REPOSITORY,
            workflow=self.env.GITHUB_MATCH_REFRESH_WORKFLOW,
            ref=self.env.GITHUB_EVIDENCE_REF,
        )
        service = ReviewService(
            account_id,
            cache,
            dota,
            analyzer=analyzer,
            evidence_gateway=evidence,
            match_refresh_gateway=match_refresh,
        )
        api_response = await route_request(
            request.method,
            urlparse(request.url).path,
            service,
        )
        return Response(
            json.dumps(api_response.payload, ensure_ascii=False, separators=(",", ":")),
            status=api_response.status,
            headers=api_response.headers,
        )
