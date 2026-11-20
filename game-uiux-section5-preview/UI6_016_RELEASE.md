# UI6-016 — Android-first UI foreground resume/resynchronization guard

- **Task ID:** `UI6-016`
- **Section:** central 06 UI/UX (conversation alias 05; owner-number conflict awaiting central 01 decision)
- **Date (KST):** 2026-11-21
- **Goal:** Prevent old on-screen game values and unintended control actions after Android WebView-like suspension, background ticks, BFCache restore, or delayed command callbacks.
- **Product context:** Central Android APK-first directive. This is **UI-owned browser-side resilience code**, not a native Android client and not a completed game engine integration.
- **Status:** `LOCAL_CODE_VERIFIED / BROWSER_CONTRACT_TESTED / GIT_PUSHED / NOT_STAGED / NOT_CORE_INTEGRATED / NOT_ANDROID_DEVICE_VERIFIED`

## Source and commits

- `game-uiux-section5-preview/ui6-runtime-adapter.js` — [2929748](https://github.com/fx564286/fx564286.github.io/commit/29297483b92a910e8af1d6b0c9812903a086ab61). SHA-256 `8ef12ca2e23bb39113f9c68dc7a56922dea8bce49975a7c4806ca1a2fa918718`, 15,339 bytes.
- `game-uiux-section5-preview/tests/ui6-016-foreground-resync.cjs` — [c06635f](https://github.com/fx564286/fx564286.github.io/commit/c06635fac775e81c15364a7bd75f0d29fd68c031). SHA-256 `6fbcbae3b01db9e85604b47bda4288c0972890b6e80377a792a67b851ed175fc`, 5,042 bytes.
- `game-uiux-section5-preview/tests/package.json` — [f0f6fb2](https://github.com/fx564286/fx564286.github.io/commit/f0f6fb2869af54e82002ecca45abc9c73ed00fa6) adds `test:port:lifecycle` to the suite.
- `game-uiux-section5-preview/one-screen.html` is unchanged.
- Official Core / 07 Art / 08 Data / 09 Infra source and contracts were not edited.

## Reproduced problem (ECC RED)

In UI6-015, the integration-mode page retained an active `stat.allocate` button after it was backgrounded. On Android Activity return, the UI could continue displaying last-known values and forward a command before receiving an up-to-date game state.

```
node tests/ui6-016-foreground-resync.cjs
# RED: AssertionError: background state must disable inputs
# expected 0, observed 4, test exited 1
```

## Minimal implementation (ECC GREEN)

- Tracks `needsForegroundSnapshot` and `suspended` in the existing UI-only adapter.
- On `document.visibilitychange` (hidden), `window.pagehide`, or BFCache `pageshow({persisted:true})`: mark last-known state as stale, invalidate in-flight command epoch and disable UI-owned mutation-intent buttons.
- Background snapshots may continue to update the read-model but **do not reactivate commands**.
- After foreground return, only a **newer accepted, validated snapshot received while foregrounded** removes the stale banner and re-enables eligible inputs.
- Same-revision or malformed snapshots cannot clear the stale indicator.
- Prior-run and pre-suspension command promises cannot unlock or relabel active session controls on late completion.
- Last-known values remain visible **with stale warnings**, rather than being mistaken for current authoritative state.
- The general demo without `?mode=integration` is unchanged.

### Important limitation

A paused authoritative runtime may legitimately have no higher revision after resume. Under the current proposal, the UI remains locked until 01's approved API supplies a newer revision. This is intentionally fail-closed: **do not infer a valid state or unlock from a timer alone**. Core/Infra must specify resume snapshot revision semantics and command ACK/retry/idempotency rules.

Browser `visibilitychange`, `pagehide` and BFCache are not proof that all Android WebView Activity lifecycle notifications fire. Once the 01 Android client framework is approved, native pause/resume must be explicitly connected to the agreed UI bridge and verified on Android.

## APIs and dependencies

- **Provided, unchanged proposal:** `ui6.view@0.1-proposal`, `ui6.command@0.1-proposal` (UI-side only).
- **Consumes / actual mapping not verified:** 01 `eclipse.playable_state@0.1`, `eclipse.playable_actions@0.1`, `core.combat_event_feed@0.2`. ECL-CORE-004 latest ZIP `ECLIPSE_RPG_Integrated_Playable_v0_1.zip` appears in Space, but the source archive bytes/actual action JSON have not been inspected during this UI task.
- 07 approved sprite/rig, 08 equipment-slot IDs and 09 game-state store, Android export identity and APK are unverified or awaiting central approval.
- No reward/persistence authority was added; game commands remain intents only.

## Verification

Run from `game-uiux-section5-preview` using Node.js + playwright-core + installed Chromium:

```bash
node --check ui6-runtime-adapter.js
node tests/ui6-016-foreground-resync.cjs
node tests/ui6-015-command-lifecycle.cjs
node tests/ui6-014-integration-port.cjs
node tests/ui6-014-rejection-restore.cjs
node tests/ui5-012-one-screen.cjs
node tests/ui5-012-state-and-a11y.cjs
node tests/ui5-013-character-art.cjs
```

**Local:** all 8 commands exit 0. New UI6-016 covers 320, 390, 1365 widths; suspend, background snapshot, fresh foreground snapshot, pre-suspend delayed command, BFCache, no JS errors/overflow. UI6-014/015 and UI5-012/013 adjacent tests also PASS.

**Public deployment:** check the page `https://fx564286.github.io/game-uiux-section5-preview/one-screen.html?mode=integration&build=ui6-016` and its `ui6-runtime-adapter.js` SHA-256. The Git blob was updated, but a CDN/browser may briefly continue serving an older asset. Only claim deployed/browser verified after SHA and remote tests both pass.

**Not performed:** Godot editor/runtime test, Android APK build, actual WebView lifecycle on a device, Core runtime source/API mapping, server persistence, authoritative reward transaction or 02 same-build Android QA.

## Section impact / handoff

- **01 central owner:** finalize official section ownership, Android framework (Godot or approved alternative), single game Git commit, Core action/snapshot revision semantics and resume ACK rules.
- **06 UI:** import adapter into the approved app client, map real Core state, explicitly wire native lifecycle events if WebView is chosen; if Godot native client, implement equivalent Godot UI state machine rather than shipping JS.
- **02 QA:** conduct real process-stop/resume/reload, offline, stale command, persisted stats/equipment, APK install/start on the same SHA.
- **07/08/09:** supply 6-slot art/data model, authorized state/restore contract and APK build/export provenance.
- **Integration judgment:** code + browser tests only. `NOT_STAGED / NOT_PROMOTED / NOT_LOCAL_PLAYABLE_E2E / NOT_ANDROID_VERIFIED`.
