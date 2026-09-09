---
id: pmt_release
tags:
- release
- checklist
title: Release Readiness Review
variables:
- service
- version
---

Review {{service}} {{version}} for release readiness.

Confirm each item explicitly:
1. Migrations run before rollout and are backward compatible for one release.
2. The rollout starts as a canary at 10% for 15 minutes.
3. Rollback plan is a redeploy of the previous image.
4. Error bodies still use application/problem+json.

Answer with PASS or BLOCK per item, then one overall verdict.
