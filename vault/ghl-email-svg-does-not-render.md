---
name: ghl-email-svg-does-not-render
description: SVG does not render in Gmail, so every vector mark must be rastered to PNG at 2x on an opaque ground before it can travel into an email.
metadata:
  type: reference
---

Anything you designed as vector for the site — a logo, a rule, an ornament, a signature
device — becomes a fixed-size bitmap in the inbox. Three consequences, all of which bite:

- **Render at 2x the display size** and set the display size in the `width`/`height`
  attributes, or it is soft on every modern screen. Outlook reads the attributes, not the
  inline style, so carry both.
- **Render it ON the ground colour, not transparent.** A transparent PNG in a client that
  force-inverts lands as the wrong colour on the wrong field and falls apart. Baking in an
  opaque ground is what makes it survive inversion.
- **Host it in the client's own GHL media library** — upload with the PIT to
  `/medias/upload-file?locationId={locationId}` — not on a third-party generation CDN that
  vanishes when someone deletes a generation upstream, and not a build-server URL that is
  not public. The returned URL is the same form the funnel builder itself uses, so it is
  safe to reference from page CSS too.

Related: `alt` text is load-bearing, because Outlook blocks images by default — anything
present only as a raster is invisible to a real share of your audience. That is the
argument for setting a masthead in live type over a coloured band instead.

See [[ghl-email-html-stored-verbatim]].
