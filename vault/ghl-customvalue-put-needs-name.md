---
name: ghl-customvalue-put-needs-name
description: A per-value custom-value PUT requires name as well as value, and fieldKey is the wrapped form with braces AND interior spaces.
metadata:
  type: reference
---

Sending only `value` fails. And **source `name` from the live record you just read, never
from a constant in your own code** — otherwise a value update can silently rename the key
and break every `{{custom_values.*}}` reference on every page and email that used it.

`name` and `fieldKey` are different strings:

- `name` is the bare snake_case key, e.g. `event_date`
- `fieldKey` is the wrapped form, `{{ custom_values.event_date }}` — **with braces AND
  interior spaces**

Matching `fieldKey` by string equality against a bare key returns "all missing" for every
value. Use a regex. The spacing is inconsistent in the wild: `fieldKey` carries spaces,
working page and email markup uses the compact form without them, and a workflow attribute
was observed using them. Both render. **Never depend on the spacing anywhere.**

Two more: a PUT needs an id that already exists, so creating is a separate POST — a
config UI must resolve keys to ids on load and cache the map. And **read-after-write is
consistent** (zero stale reads across a ten-iteration test), so a form can re-hydrate
immediately after saving.

See [[ghl-customvalues-bulk-is-gone]], [[ghl-custom-value-needs-two-surfaces]].
