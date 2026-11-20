# UI5 — Browser regression tests

These scripts exercise the standalone UI/UX preview. The mock game transport is not a production server.

## Run

Install Node.js 20+ and Chromium. From this folder:

```bash
npm install
# Set the path to a locally installed Chromium/Chrome binary.
export UI5_CHROME_PATH=/absolute/path/to/chrome
npm test
```

On Windows PowerShell:

```powershell
$env:UI5_CHROME_PATH="C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
npm test
```

By default the tests open `../index.html` locally. To verify the public deployment instead:

```bash
export UI5_PREVIEW_URL="https://fx564286.github.io/game-uiux-section5-preview/?build=ui5-011"
npm test
```

The tests are grouped by concern:

- `test:visual`: 266 browser assertions covering five main screens at 320, 390, 768, and 1365px. Checks typography, action heights, margins, section alignment, responsive nav, overflow, and card dimensions.
- `test:flow`: home, result, modal, battle, character and screen-specific overlap checks at 320, 390, and 1024px.
- `test:craft`: mock crafting, equip, inventory deduction, and character appearance projection.
- `test:render`: preservation of combat scene and navigation DOM identity between automatic combat ticks.

Scope: independent HTML/CSS/JS prototype. This suite does not certify Safari on iPhone, official engine performance, production APIs, or gameplay balance.

## UI5-012 — One-screen portrait UI (new)

The new one-screen preview is `../one-screen.html`, which is kept separate from `../index.html` until the central section approves integration.

```bash
# Run the single-screen UI tests locally
npm run test:single
npm run test:single:a11y

# Run the same tests against the public preview
export UI5_PREVIEW_URL="https://fx564286.github.io/game-uiux-section5-preview/one-screen.html?build=ui5-012"
npm run test:single
npm run test:single:a11y
```

- `test:single`: checks battle above settings, seven enemy DOM units, actual right-to-left X motion, stat allocation, three automatic skill toggles, six equipment slots, two pet slots, mount slot, potion control, 44px controls, and 320/390/768/1365px layouts.
- `test:single:a11y`: checks reversible stat points, mock skill-tree paths, potion threshold, pet/mount unlock proposal preview, persistent battle DOM during settings changes, pinned combat scene when lower panel scrolls, original sprite armor colors, JavaScript errors, and reduced-motion accessibility.

A browser passing these visual tests does not establish actual combat-core, engine, network, Android, Safari or gameplay validation. The demo gold, stats, skill tree, equipment labels, enemy damage, and companion availability are non-authoritative visual fixtures.
