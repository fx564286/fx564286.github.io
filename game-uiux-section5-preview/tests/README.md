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
