## Domain model

- A **Tenant** is the billing boundary. Every invoice belongs to exactly one tenant.
- A **Workspace** belongs to exactly one Tenant and never moves between tenants.
- Users are global identities; membership binds a user to a workspace with a role.

## Error convention

- Every HTTP error body is `application/problem+json`.
- Machine readable codes live in the error code namespace `cx.`, e.g. `cx.auth.token-expired`.
- Never leak an internal stack trace to a client.

## Auth token refresh

- Access tokens live 15 minutes, refresh tokens live 30 days.
- The client refreshes on 401, never on a timer.
- Refresh is single-flight: concurrent 401s wait on one refresh call.
- Every refresh rotates the refresh token and revokes the old one immediately.

## Deploy checklist

- Migrations run before rollout and stay backward compatible for one release.
- Every rollout starts as a canary at 10% for 15 minutes.
- Rollback is a redeploy of the previous image, never a manual database edit.

## API style

- REST only over JSON. GraphQL is not used in this product.
- Resource names are plural nouns; verbs live in the HTTP method.

## Observability

- All logs are structured JSON logs with a trace id field.
- The trace id is propagated across every service hop and returned as X-Trace-Id.
