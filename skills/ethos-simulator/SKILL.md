---
name: ethos-simulator
description: Run the Rotorflight Ethos Lua suite (rotorflight-lua-ethos-suite) in the FrSky Ethos WASM simulator, operate it with keys and touch, read its Lua log and take screenshots. Use when checking a page, dialog, widget or dashboard change in the Ethos suite, or when a pull request needs simulator screenshots.
---

# Ethos simulator

FrSky provides the simulator runner and an agent skill for it in
[FrSkyRC/ethos-tools](https://github.com/FrSkyRC/ethos-tools); its documentation is
<https://ethos-lua-doc.frsky-rc.com/tools/ai-agents/>. Section 11 of the suite's `AGENTS.md`
holds the Rotorflight-specific steps. Read both; this skill ties them together.

## Install the runner

- **Claude Code:** `/plugin marketplace add FrSkyRC/ethos-tools`, then
  `/plugin install ethos-simulator@ethos-tools`. It adds the `ethos-navigate` skill (start,
  screenshot loop, keys). The suite's `.claude/settings.json` already offers it.
- **Other agents:** clone `FrSkyRC/ethos-tools` and run `node simulation/run_wasm.js --serve`.
  Its README lists the commands (`status`, `screenshot`, `tap`, `swipe`, `press`, `log`, `quit`).

The simulator build (`<BOARD>_<PROTOCOL>.js` + `.wasm`) comes from the Ethos VS Code extension's
cache. The suite's `.vscode/settings.json` (`ethos.board`, `ethos.protocol`) picks which one.

## Loop

1. **Deploy** from the suite:
   `python .vscode/scripts/deploy.py --lang en --step i18n --step soundpack --step sensors`.
   It writes `simulators/<BOARD>_<PROTOCOL>@<release>/scripts/rfsuite`.
2. **Start** the runner with that `simulators/<BOARD>_<PROTOCOL>@<release>/` folder as the root
   directory (`--root-directory`). Only one simulator per folder.
3. **Boot:** dismiss *Select Battery*, *Battery Profile* and *Checklist warning* in turn; keys are
   ignored while a dialog is open.
4. **Open the app:** `SYS`, `PAGE` to System page 2, the **Rotorflight** tile.
5. **Check:** take a screenshot after each step and look at it. Lua errors appear only in `log`.
6. **Redeploy:** shared modules cache themselves in `package.loaded`, so `quit` and start again
   after each deploy. Delete stale `*.luac` files if behaviour does not change.

No flight controller is needed: the suite's simulated sensors (`src/rfsuite/sim/sensors/`) and
`simulatorResponse` tables in `src/rfsuite/lib/msp_*.lua` fill the pages.

## Another board

Test text-heavy changes on the smallest screen (X18S, 480x320). A model saved by a newer Ethos
build does not load on an older one, so give the second board a fresh root folder containing only
`scripts/rfsuite`, finish the *Create model* wizard, then:

1. Model menu page 3, **Lua**: turn **Rotorflight [Background]** on.
2. Model menu page 1, **RF system**, **Internal module**: **State** on.
3. Model menu page 2, **Telemetry**: discover sensors if the list is empty.

Without these, every tile shows *Background task not running*.

## Pitfalls

- Agents running inside VS Code inherit `ELECTRON_RUN_AS_NODE=1`, which breaks FrSky Suite path
  lookups. Unset it for those commands.
- The simulator listens on port 8765; the real-radio server (ethos-real-radio skill) uses 8766,
  so both can run at once.
