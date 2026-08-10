---
name: ghl-preview-url-is-read-only
description: "The preview URL sites.leadconnectorhq.com/preview/{pageId} is a rendered output you check work against, never a surface you write to. — SYMPTOM: CSS or edits made at the preview URL vanish on reload"
metadata:
  type: reference
---

An inheriting agent lost time trying to apply CSS there. There is nothing at that URL to
modify; anything you appear to change in a browser session is gone on reload. **The page
lives in `pageData`. The preview is a photograph of it.**

The mistake is induced by the documentation, including the repo this note came from: the
preview is described everywhere as "the verification surface", which is true and reads to
a tired agent as "the place the page lives".

What it *is* good for is the thing it is described as. It is public, server-rendered, and
needs no custom domain or auth, so a plain `curl` plus a grep for your changed literal
string is a one-line automated proof that a write landed.

**CSS has exactly two destinations:** page styling goes into a `custom-code` element
inside `pageData` (`extra.customCode`, wrapped in `<style>`); form styling goes into the
form record at `formData.form.fieldCSS`.

The detection habit: **ask what object you are modifying. If the answer is a URL rather
than a record, stop.**

See [[ghl-form-css-lives-in-fieldcss]], [[ghl-custom-code-payload-is-extra-customcode]],
[[ghl-200-is-not-proof]].
