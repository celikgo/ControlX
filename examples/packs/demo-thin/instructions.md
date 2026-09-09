## Domain model

- A **Tenant** is the billing boundary. Every invoice belongs to exactly one tenant.
- A **Workspace** belongs to exactly one Tenant and never moves between tenants.

## Error convention

- Every HTTP error body is `application/problem+json`.
- Machine readable codes live in the error code namespace `cx.`.

## Observability

- All logs are structured JSON logs.
