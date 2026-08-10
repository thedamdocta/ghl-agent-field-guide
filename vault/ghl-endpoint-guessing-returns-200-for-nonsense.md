---
name: ghl-endpoint-guessing-returns-200-for-nonsense
description: Unknown funnel paths fall through to a generic get-by-id route and return 200 echoing your path segment, so a guessed endpoint can look like a discovery.
metadata:
  type: reference
---

`GET /funnels/funnel/ai`, `/funnels/funnel/clone`, `/funnels/funnel/import-clickfunnels`
all return **200** with `{"_id": "<your own path segment>"}`. None of them are AI, clone or
import routes. They are one route politely echoing you back. This was believed twice in
one session, and each false positive was written down as real.

**The control test, which should be the first request of any probing session:** probe a
deliberately nonsense id and compare. `/funnels/funnel/zzzznotreal` returns 200 with an
identical shape — so that route tells you nothing. `/funnels/page/zzzznotreal` returns
400, so *that* route does discriminate and is worth probing.

Two responses that are genuine signals:

- **`403 "This route is not yet supported by the IAM Service"`** — a real route family
  behind a platform wall. Holds for both credentials. Stop probing; find what the UI calls.
- **`401` from a PIT** — possibly just a missing scope. Re-test with the internal JWT.

What actually discovers an endpoint is **capturing real traffic while the GoHighLevel UI
performs the action**. Watching beat guessing every time both were tried.

See [[ghl-mcp-search-describe-execute]], [[ghl-catalogue-gap-is-not-a-platform-limit]].
