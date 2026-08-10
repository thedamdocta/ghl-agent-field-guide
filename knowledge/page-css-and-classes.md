# Page CSS — Where It Goes, What It Targets, Why It Loses

**For cold readers:** this is the companion to
[`funnel-pages.md`](funnel-pages.md). That document tells you a page's CSS lives in
`section.general.sectionStyles`. This one tells you what the rendered DOM actually
looks like, what selectors reach it, and why a rule that is unquestionably present
does nothing. Everything marked "verified" was read off builder-generated CSS from a
real GoHighLevel (GHL) page or reproduced with the tools in this repo. Anything else
is labelled **UNVERIFIED**.

**The artifacts this document explains ship with the repo.** You do not have to write
a page stylesheet from this prose:

- [`../tools/page-styles.starter.css`](../tools/page-styles.starter.css) — a working,
  brand-neutral page stylesheet with tokens at the top.
- [`../tools/page_shell.py`](../tools/page_shell.py) — puts it on a page correctly and
  checks that it is wired.

**The one thing to internalise:** your stylesheet and GHL's generated CSS live in the
**same specificity tier**, and GHL's is injected **after** yours. Ties lose. Most
"my CSS is being ignored" on this platform is a rule that is present, matched, and
outranked.

---

## 1. Three stylesheets reach the page. You author two of them.

In load order:

| # | Stylesheet | Who writes it | What belongs in it |
|---|---|---|---|
| 1 | GHL's platform sheet | GHL | nothing of yours |
| 2 | your page-level `<style>` | you, via a `custom-code` element | the design **system**: type scale, spacing, buttons, components |
| 3 | `section.general.sectionStyles`, in section order | `css_emitter.py` | per-**element** values: this heading is 76px, this section is `#ffffff` |

Number 3 is emitted last, so it wins every tie against number 2. That single ordering
fact explains nearly every styling failure in this platform, and §4 is the arithmetic.

**Number 2 is a system stylesheet, not a patch.** Write it once, ordered
`containment → layout → type → components → roles → motion → mobile`, and treat any
rule you have to add later as evidence that the system is incomplete rather than as a
fix. The starter is already in that order.

### How number 2 gets onto the page

A `custom-code` element, whose payload field is **`extra.customCode`**. Three rules,
none of them documented by GHL, all of them silent when broken:

- The payload field is `extra.customCode`. Guessing `code` / `html` / `text` gives you
  an element that renders and a script that never runs.
- **`<script>` must not be nested inside a `<div>`.** The `<link>`, `<style>` and
  `<script>` tags must be siblings at the top level of the payload.
- The script must wait for GHL's **`hydrationDone`** event, and page settings must have
  **"Optimise JavaScript" turned OFF** — otherwise hydration defers and your script
  runs against a DOM that is not there yet.

`page_shell.py` emits a payload that satisfies all three:

```bash
python3 page_shell.py --emit                          # print it
python3 page_shell.py --attach page.json --out page.json   # append it as a section
python3 page_shell.py --check page.json               # prove it is wired
```

**Fonts: `<link>` with `preconnect`, never `@import`.** `@import` serialises the font
fetch behind the stylesheet parse and delays first paint. `--font-css <url>` emits the
correct block.

**The section carrying the stylesheet has no visible content and must occupy no
space.** Left alone it keeps whatever padding its exemplar carried — the emitter then
*forces* that padding — and the page ends in a hundred-odd pixels of nothing beneath
the footer. That is what the `.gp-tail` rule in the starter is for.

---

## 2. What GHL actually renders — the class map

Verified by reading builder-generated `sectionStyles` off a real 9-section page.

Every node renders with classes derived from its ids. You cannot know those ids when
you write a stylesheet, so **you target the type prefix by substring match**:

```css
[class*=section-]   [class*=row-]   [class*=column-]
[class*=heading-]   [class*=sub-heading-]   [class*=paragraph-]
[class*=image-]     [class*=divider-]       [class*=custom-code-]
[class*=nav-menu-v2-]   [class*=faq-]   [class*=social-]
```

Each of those matches **both** id namespaces at once (`section-…` and `csection-…`),
which is usually what you want.

Structural classes that are stable and worth knowing:

| Selector | What it is |
|---|---|
| `.hl_page-preview--content` | the wrapper every rule should be scoped under |
| `> .inner` | GHL's flex box **inside** every section and column. It is driven by `#<id> > .inner{flex-direction;justify-content;align-items;flex-wrap}` rules — 49 of them on one page. If a column will not stack the way you want, this is the box you are actually fighting. |
| `div.c-button` | the **wrapper** around a button |
| `button[class*=cbutton]`, `.btn.button-element` | the real `<button>` |
| `.ghl-form-wrap`, `.hl_form-builder--main`, `.form-builder--wrap` | an inline form. **Verified:** a GHL form on a GHL funnel page renders inline in the main document, not in an iframe — page CSS reaches it. The same form embedded on a third-party site *is* iframed and needs [`../tools/form-styles.starter.css`](../tools/form-styles.starter.css) instead. |
| `.form-builder--item`, `.form-control`, `.error` | fields and validation inside that form |
| `.drawer__content`, `.grecaptcha-badge` | GHL furniture rendered outside the content box. On one production page these were the entire 60px of horizontal overflow. |

**A leaked builder style worth knowing about:** `.form-builder--wrap` ships a `1px
dashed` light-blue border into the *rendered* page. On any non-white ground it reads as
a debug rectangle.

### Your own classes on a section

`extra.customClass` exists in the schema. It was `{"value": []}` on all 158 of its occurrences in
the captured corpus, so whether writing to it reaches the rendered DOM is
**UNVERIFIED**. Do not build a design on it without testing it first.

The route that has shipped is to tag sections at **runtime**, from their **content**:

```js
if (i === n-1 || s.querySelector('style,script'))   return 'gp-tail';
if (s.querySelector('.ghl-form-wrap,form,input'))   return 'gp-form-plate';
if (s.querySelector('h1'))                          return 'gp-hero';
if (/all rights reserved/i.test(s.textContent))     return 'gp-foot';
```

`page_shell.py` ships this. Two things about it are load-bearing:

**Roles come from content, never from position.** A positional list is wrong the moment
a page has a different number of sections: a list written for a 9-section page labels
section 3 "the date band" on a 4-section page and applies a date band's treatment to
whatever is there. Content-derived tagging needs no per-page configuration and was
correct on all six pages of a production funnel.

**Order matters in that list.** The tail section carries your stylesheet, whose
*comments* can match a later text test. Identify it first, and by structure
(`querySelector('style,script')`) rather than by words.

And do not reach for `:nth-of-type()` as a substitute.
`[class*=section-]:nth-of-type(2)` matches on element **type**, not on the attribute
selector — so it counts every sibling of that tag, and one injected wrapper moves your
hero styling onto the wrong element. It works by coincidence until it doesn't.

---

## 3. The two ids are independent — do not derive one from the other

**This corrects a claim that was in this repo.** Every node carries an authoring id
(`node.id`) and a rendered id (`node.extra.nodeId`). It is tempting to read the
`c` prefix as the whole relationship. It is not.

**Verified, on a real builder-authored page: `extra.nodeId` was `"c" + id` for 0 of 78
nodes.** They share the *type prefix* and have **different random suffixes**:

```
id = button-bM3DE444_E        nodeId = cbutton-hXqqMDg5w8
id = paragraph-_aVW_3QYq-     nodeId = cparagraph-_eHB3sQOF7
id = custom-code-ZWKk0-9MgA   nodeId = ccustom-code-m4MXXJ1k0T
```

Consequences that bite:

- **Stripping the leading `c` off a scraped rendered id does not give you the authoring
  id.** `cbutton-hXqqMDg5w8` → `button-hXqqMDg5w8` matches nothing. The only link
  between the two is `extra.nodeId` on the authoring node — read the pair off the tree,
  never reconstruct it.
- **Never write a stylesheet rule against an exact id.** Match the type prefix.
- `ghl_generator.py` mints `nodeId = "c" + id` for elements it creates. That is a
  *convention of this repo's generator* — it only has to be unique and `c`-prefixed —
  and not a fact about GHL. Code that assumes it will work on pages you generated and
  break on pages you captured.

### The division of labour between the two ids

Verified from builder output, and it is systematic:

| Selector | Properties it carries |
|---|---|
| `.hl_page-preview--content #<authoringId>` | wrapper box metrics: `margin`, `width`, `height` |
| `#<authoringId> > .inner` | inner flex: `flex-direction`, `justify-content`, `align-items`, `flex-wrap`, `max-width` |
| `.hl_page-preview--content .<authoringId>` | for sections/rows/columns: `padding`, `background-color`, `border-*`, `box-shadow`, `width` |
| `.hl_page-preview--content .<renderedNodeId>` | for elements: **appearance** — `font-family`, `color`, `background-color`, `padding`, `font-weight`, `border-*`, `line-height`, `letter-spacing`, `text-transform`, `text-align` |
| `.<authoringId> a u`, `.<authoringId> a:hover` | link states inside a text element |

Read the button row of that table twice. **A button's fill belongs to the rendered id;
the authoring id is the wrapper.** `css_emitter.py` correctly emits each node's styles
against *both* ids — that is required, because element-level styling keys off the
rendered one — but it means a background declared in `styles` also paints the wrapper.
While the wrapper hugs the button that is invisible. The moment the wrapper spans the
row, you get a full-width slab of accent colour. The starter stylesheet forces
`div.c-button` transparent for exactly this reason; keep that rule when you restyle.

### GHL emits invalid CSS, and that is not your bug

Builder output contains `typography:`, `icon-color:`, `secondary-color:`,
`link-text-color:`, `force-column-layout-for-mobile:false`, and `width:auto%`. Browsers
drop them. Seeing them in a page you captured does not mean the capture is corrupt. It
does mean you should not copy GHL's emitter as a specification — `css_emitter.py`'s
`SKIP` list exists to keep those keys out of *your* output, where a bad declaration can
invalidate a whole rule in some parsers.

---

## 4. The specificity ladder — the arithmetic that decides everything

Selector weights are `(id, class, type)`. Verified rungs, lowest first:

| Selector shape | Weight | Written by |
|---|---|---|
| `.heading-<id>` | (0,1,0) | GHL |
| `.hl_page-preview--content h1` | (0,1,1) | you |
| `.hl_page-preview--content .cheading-<id>` | (0,2,0) | GHL **and** `css_emitter.py` |
| `.hl_page-preview--content div[class*=cform-]` | (0,2,1) | you |
| `.hl_page-preview--content [class*=section-] h1` | (0,2,1) | you |
| `.hl_page-preview--content [class*=section-].gp-hero` | (0,3,0) | you |
| `.hl_page-preview--content #heading-<id>` | **(1,1,0)** | GHL |

Three things follow, and each one has cost real time:

**`!important` does not settle a tie.** It ranks you against *non*-important rules. It
does nothing against a later same-specificity important rule. A form once stayed 333px
wide against a 440px `!important` rule because both selectors were (0,2,0) and GHL's
came second. The fix was a tag qualifier — `div[class*=cform-]` at (0,2,1) — not a
louder `!important`.

**The emitter forces four properties, and they will beat a plain rule of yours.**
`css_emitter.py`'s `FORCE` set is `background-color`, `color`, `padding-top`,
`padding-bottom`, emitted at (0,2,0) with `!important`. That force is *necessary* —
without it GHL's base sheet makes every section transparent and the page flattens to
one colour — but it means:

- A section rule of yours at (0,2,0) loses its padding. Write section rules as
  `[class*=section-].gp-role` = (0,3,0).
- A colour rule at `.hl_page-preview--content h1` = (0,1,1) loses. **Headings take
  whatever `styles.color` their element carries**, which is how a source file that
  plainly says "sepia" ships black text on a black ground. Add one descendant step —
  `[class*=section-] h1` = (0,2,1) — to take ownership back, or set colour per element
  and mean it.

Either fix is legitimate. The failure mode is picking neither, because the rule *looks*
right in the file.

**You cannot beat an `#id` rule with a class.** GHL emitted 77 ID selectors on a
single page, carrying `margin`, `width` and `height` on element wrappers. If a margin or
a width will not move no matter what you do, stop escalating classes: match it with an
`#id` of your own, or change the element's `styles` so the emitter writes the value you
want — which puts you in the same tier instead of under it.

**Match the builder's mobile query verbatim** —
`@media screen and (min-width:0px) and (max-width:480px)` — rather than "improving" it
to a plain `max-width`. Identical query text is what keeps the two stylesheets from
interleaving in a surprising order. Your page-level sheet may use its own layout
breakpoint (the starter uses 768px); just do not merge the two. And remember a media
query adds **no** specificity: a bare `.gp-tail` inside one loses exactly as it would
outside.

**Replace `sectionStyles` wholesale; never merge into it.** If you append, a stale
hand-edit from the builder survives and silently fights your generated rules, and which
one wins depends on emission order. That is the hardest class of bug here, because the
page looks *almost* right.

---

## 5. A complete worked example, with real values

Every id and CSS string below was produced by running the tools in this repo. Nothing
is illustrative.

### 5.1 The spec

```json
{"sections": [{"background": "#ffffff", "rows": [{"columns": [{"width": 100, "elements": [
  {"kind": "heading",   "html": "<h1>Ship the artifact</h1>",
   "color": "#16181d", "desktopSize": 76, "mobileSize": 38},
  {"kind": "paragraph", "html": "<p class=\"gp-lead\">A description of a stylesheet is not a stylesheet.</p>",
   "color": "#3c4048", "desktopSize": 23},
  {"kind": "button",    "label": "Read the guide", "action": "go-to-next-funnel-step",
   "background": "#2f4858", "color": "#ffffff"}
]}]}]}]}
```

### 5.2 The tree

```bash
python3 ghl_generator.py --spec demo-spec.json --out demo.json
```

```
SECTION  id=section-YHG1MJRzlZ     nodeId=csection-YHG1MJRzlZ
row      id=row-ur_dMIxWN7         nodeId=crow-ur_dMIxWN7
col      id=column-xwx0SZTWUB      nodeId=ccolumn-xwx0SZTWUB
element  id=heading-B_R1JQ52Ul     nodeId=cheading-B_R1JQ52Ul
element  id=paragraph-msPuOE5uTf   nodeId=cparagraph-msPuOE5uTf
element  id=button-1btQocHahj      nodeId=cbutton-1btQocHahj
```

(These `nodeId`s *are* `"c" + id` because this generator mints them that way. A page
captured from the builder will not look like this — see §3.)

### 5.3 Attach the page-level stylesheet, then emit

Order matters: attach **first**, so the shell section gets `sectionStyles` emitted for
it too.

```bash
python3 page_shell.py --attach demo.json --out demo.json
python3 css_emitter.py demo.json --root-vars '{"--gp-ground":"#ffffff","--gp-accent":"#2f4858"}'
```

### 5.4 What actually got written into `sections[0].general.sectionStyles`

Trimmed to the load-bearing declarations:

```css
:root{--gp-ground:#ffffff;--gp-accent:#2f4858}

.hl_page-preview--content .section-YHG1MJRzlZ,
.hl_page-preview--content .csection-YHG1MJRzlZ{
  padding-top:100px!important;padding-bottom:120px!important;
  background-color:#ffffff!important; … }

.hl_page-preview--content .heading-B_R1JQ52Ul,
.hl_page-preview--content .cheading-B_R1JQ52Ul{
  color:#16181d!important;font-size:76px;line-height:1.25;text-align:left; … }

.hl_page-preview--content .button-1btQocHahj,
.hl_page-preview--content .cbutton-1btQocHahj{
  background-color:#2f4858!important;color:#ffffff!important;
  padding-top:18px!important;padding-left:48px;border-radius:6px; … }

@media screen and (min-width:0px) and (max-width:480px){
  .hl_page-preview--content .heading-B_R1JQ52Ul,
  .hl_page-preview--content .cheading-B_R1JQ52Ul{font-size:38px!important}
  .hl_page-preview--content .section-YHG1MJRzlZ{
    padding-top:60px!important;padding-bottom:80px!important} }
```

Read that output against §4 and three predictions fall out, all of which the starter
stylesheet is built to handle:

1. `padding-top:100px!important` on the section at (0,2,0) **beats** a page-level
   `.hl_page-preview--content [class*=section-]{padding:…!important}`, which is also
   (0,2,0) and comes earlier. That is why the starter also carries a (0,3,0) rule.
2. `color:#16181d!important` on `.cheading-…` at (0,2,0) **beats** a page-level
   `.hl_page-preview--content h1{color:…!important}` at (0,1,1). Heading colour is the
   element's, not the stylesheet's, until you raise specificity.
3. `background-color:#2f4858!important` is written to **both** `button-1btQocHahj` (the
   wrapper) and `cbutton-1btQocHahj` (the button). Force the wrapper transparent or a
   full-width wrapper paints a slab.

### 5.5 Verify before injecting, then verify after

```bash
python3 page_shell.py --check demo.json
```

```
  sections:                    3
  page shells:                 1
  sections with sectionStyles: 3/3
  OK — shell present once, script wired, every styled role assigned.
```

That is a **static** check: exactly one shell, the script waits for `hydrationDone`,
the `<script>` is not nested in a `<div>`, and every `gp-*` class the stylesheet
targets is one the script actually assigns. A rule that styles a class nobody sets is
invisible in review and does nothing on the page, which is the same failure as a
misspelled selector.

Then inject and prove it on the rendered page:

```bash
python3 inject_page.py --page-data demo.styled.json --page-id <id> --funnel-id <id> \
    --expect "Ship the artifact"
```

---

## 6. Verification — what counts

```
https://sites.leadconnectorhq.com/preview/{pageId}
```

Public, server-rendered, no custom domain needed. **A `201` is not a result.** GHL
compiles pages at save time, so the API echoing your write back proves only that the
write was stored.

For CSS specifically, grepping the HTML is not enough either:

- **Read computed style, not the stylesheet.** A rule that is present and losing looks
  exactly like a rule that is absent. Getting this wrong sends you rewriting a correct
  rule instead of raising its specificity by one class.
- **Walk the ancestor chain.** The winning rule is rarely on the element you suspect.
- **Check at a real viewport, in both orientations.** The mobile block is a different
  layout, not a scaled one, and 480px (the emitter's query) and 768px (a typical layout
  breakpoint) are different worlds.
- **Check horizontal overflow explicitly** — `document.documentElement.scrollWidth >
  window.innerWidth`. GHL furniture rendered outside the content box is the usual
  culprit and it is easy to miss on a desktop screenshot.

---

## 7. Known unknowns

- **UNVERIFIED: `extra.customClass`.** Whether a class written there reaches the
  rendered DOM was never observed; the captured corpus had it empty on every node.
- **UNVERIFIED: durability against builder edits.** The builder regenerates
  `sectionStyles` when a human edits a page. What happens to hand-emitted rules after a
  client opens the page in the builder was never watched through a full cycle. Assume
  your emitted CSS is not durable until you have seen one.
- **The `#id` rules are GHL's to write.** Nothing in this repo emits ID selectors. If
  you need to outrank one, you are writing that rule by hand and you own keeping it in
  sync with an id you did not mint.

## Related

- [`funnel-pages.md`](funnel-pages.md) — the page schema, the write path, `sectionStyles`
- [`../patterns/design-systems-in-ghl.md`](../patterns/design-systems-in-ghl.md) — holding one design system across pages and email
- [`../methodology/design-quality.md`](../methodology/design-quality.md) — measuring instead of eyeballing
- [`../tools/README.md`](../tools/README.md) — the pipeline these tools sit in

---

## Where CSS goes — and the mistake that keeps happening

**Never try to apply CSS at the preview URL.** An inheriting agent lost time to this
and it was entirely avoidable.

```
https://sites.leadconnectorhq.com/preview/{pageId}
```

That is a **rendered output**. It is read-only. It is the surface you *check* your work
on, never a surface you write to — there is nothing there to modify, and anything you
appear to change in a browser session is gone on reload. It is documented all over this
repo as "the verification surface", which is true and evidently easy to misread as "the
place the page lives". The page lives in `pageData`. The preview is a photograph of it.

**CSS has exactly two destinations, and which one depends on what you are styling:**

| styling… | goes into | how |
|---|---|---|
| the **page** — sections, headings, buttons, layout | a `custom-code` element in `pageData` (`extra.customCode`, wrapped in `<style>`) | `page_shell.py --attach`, then `inject_page.py` |
| the **form** — inputs, placeholders, the submit button, dropdowns | the **form record**, at `formData.form.fieldCSS` | `POST backend…/forms/{formId}` |

**They are different documents and neither reaches the other.** A GHL form renders in
its own document — an iframe when embedded on a third-party site — so page CSS cannot
cross into it and form CSS cannot escape it. Put form rules on the page and precisely
nothing happens; the page still returns 201 and the preview still renders, which is why
this failure is quiet.

The practical consequence people miss: **a submit button has to be styled twice.** Once
on the page for the page's own call-to-action, once in `fieldCSS` for the one inside the
form. Style it in one place only and the funnel ships with two different buttons, one of
which you did not design.

### The check

After writing either one, reload the preview URL and confirm the change is *there*.
That is what the preview is for. If you find yourself editing anything at that URL, you
are working on the photograph.
