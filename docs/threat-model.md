# Threat model and safety controls

## Assets and trust boundaries

Assets are destination URLs, short-code mappings, click aggregates, workflow requirements/artifacts, and approval records. Unauthenticated HTTP clients are untrusted. Requirements and agent artifacts are data, not executable commands. The SQLite database and local process are trusted only for a single-user demonstration.

## Controls implemented

- Only absolute HTTP/HTTPS URLs are stored; embedded URL credentials and malformed ports are rejected.
- Link creation never makes an outbound request, avoiding server-side request forgery through submitted targets.
- SQL values use bound parameters; short-code uniqueness is enforced by a primary key.
- Workflow changes and approval decisions are recorded with timestamps and requirement/artifact hashes.
- Human approval gates release readiness; repeated stage failures stop with a fallback record.
- Click records exclude client IP and user-agent by default.

## Risks not addressed for production

There is no authentication/authorization, rate limit, custom-domain verification, abuse reporting, phishing/malware classification, data retention job, distributed locking, tamper-evident audit store, or enterprise identity integration. Anyone with access to the local API can create aliases and approve a run. The service should bind to loopback by default and not be exposed to the public internet. Add access control and operational abuse controls before deployment.
