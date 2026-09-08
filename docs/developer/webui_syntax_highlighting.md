# Syntax Highlighting in the WebUI

The WebUI uses `dcc.Markdown` to display read-only content, such as the current
scan configuration (TOML) in the *View TOML* modal (`view-cfg-content`).
Markdown code fences are highlighted client-side by
[highlight.js](https://highlightjs.org/).

This page documents how highlighting works, how to change the theme (CSS), and
where the relevant pieces live.

## How it works

1. **Code fence** — the TOML is emitted as a fenced code block
   (```` ```toml ````) by the `toggle_view_cfg_modal` callback in
   `src/webui/plantimager/webui/scan.py`. `dcc.Markdown` turns it into a
   `<pre><code class="language-toml">` element.

2. **highlight.js library** — `highlight.min.js` is shipped in the WebUI
   `assets` folder and served by Dash on every page load.

3. **Trigger** — a clientside callback in `scan.py` runs `hljs.highlightElement`
   on every `#view-cfg-content pre code` element each time the markdown content
   is updated (which happens when the modal is opened).

4. **Theme (CSS)** — a highlight.js stylesheet is also placed in `assets` and
   loaded automatically, giving the highlighted tokens their colors.

## Changing the CSS theme

The theme is a single CSS file in the WebUI assets folder:

```
src/webui/plantimager/webui/assets/
├── highlight.min.js                    # the highlight.js engine
└── highlight-stackoverflow-light.min.css  # the color theme
```

To change the theme:

1. Pick a theme from the [highlight.js styles](https://github.com/highlightjs/highlight.js/tree/main/src/styles)
   or preview them at <https://highlightjs.org/static/demo/>.
2. Download the corresponding `*.min.css` from the
   [highlight.js CDN](https://cdnjs.cloudflare.com/ajax/libs/highlight.js/)
   (use the same version as `highlight.min.js`).
3. Copy it into the assets folder above (any filename is fine).
4. Remove the old theme CSS so only one theme is loaded (Dash loads all assets;
   the last-loaded rules win, which can cause surprising mixes otherwise).
5. Restart the WebUI and hard-refresh the browser (the CSS is cached).

## Changing the highlight.js language set

`highlight.min.js` currently ships with the full language set. If bundle size
becomes a concern, build a trimmed package at
<https://highlightjs.org/download/> selecting only the languages you need and
replace `assets/highlight.min.js`.
