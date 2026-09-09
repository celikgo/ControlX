---
date: '2026-02-11'
id: dec_singleflight
title: Refresh is single-flight
---

Concurrent 401s used to trigger a refresh storm that rotated tokens out from
under each other. We now serialize refresh through one in-flight promise per
client and rotate the refresh token exactly once per cycle.
