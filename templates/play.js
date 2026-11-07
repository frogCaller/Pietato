"use strict";
// A game from the Pi, played here in EmulatorJS (GPL-3.0, emulatorjs.org): what to play is in this page's address (the
// Screen view puts it there, where the Pi's screen was). Its in-game save comes from the Pi as it starts, and goes
// back to the Pi as the game makes it, and when it's closed, so you can carry on there. Played with the emulator the
// Pi plays it with (moment), where you were comes from the Pi too, and goes back as it's closed.
(() => {
  const q = new URLSearchParams(location.search);
  const CORES = {                                 // the systems it plays, and the core each needs
    fceumm: "fceumm", snes9x: "snes9x", gambatte: "gambatte", mgba: "mgba", segaMD: "genesis_plus_gx",
    segaGG: "genesis_plus_gx", smsplus: "smsplus", mupen64plus_next: "mupen64plus_next",
    pcsx_rearmed: "pcsx_rearmed", melonds: "melonds",
  };
  const core = q.get("core") || "", rom = q.get("rom") || "", bios = q.get("bios") || "";
  const save = /^Saves\/[^/]+\.srm$/.test(q.get("save") || "") ? q.get("save") : "";
  const moment = q.get("moment") === "1" && save ? save.replace(/\.srm$/, ".state.auto") : "";   // (where you are: the
  const pickUp = moment && q.get("state") === moment;                                           //  Pi has one to pick up)
  const color = /^#[0-9a-f]{6}$/i.test(q.get("color") || "") ? q.get("color") : "#60aae4";
  const IDS = { b: 0, y: 1, select: 2, start: 3, up: 4, down: 5, left: 6, right: 7, a: 8, x: 9, l: 10, r: 11,
                l2: 12, r2: 13, l3: 14, r3: 15 };   // (a controller's buttons, by libretro's numbers, as the Pi's)
  const home = (p) => "/api/home/" + p.split("/").map(encodeURIComponent).join("/");
  const note = document.getElementById("note");
  let started = false, sent = null, turn = Promise.resolve();

  function tell(what) {                           // (to the Screen view)
    if (parent !== window) parent.postMessage(Object.assign({ pietato: "game" }, what), location.origin);
  }
  function say(text, bad) {
    note.textContent = text;
    note.hidden = false;
    if (bad) tell({ error: text });
  }
  const same = (a, b) => !!a && !!b && a.length === b.length && a.every((v, i) => v === b[i]);
  const manager = () => window.EJS_emulator && window.EJS_emulator.gameManager;

  async function fromPi() {                       // the save the Pi has, into the game as it starts
    const gm = manager();
    if (!gm || !save) return;
    try {
      const r = await fetch("/api/file?folder=games&download=1&path=" + encodeURIComponent(save), { cache: "no-store" });
      if (!r.ok) return;                          // (none yet)
      const data = new Uint8Array(await r.arrayBuffer());
      if (!data.length) return;
      const path = gm.getSaveFilePath();
      let at = "";
      for (const part of path.split("/").slice(0, -1)) {
        if (!part) continue;
        at += "/" + part;
        if (!gm.FS.analyzePath(at).exists) gm.FS.mkdir(at);
      }
      if (gm.FS.analyzePath(path).exists) gm.FS.unlink(path);
      gm.FS.writeFile(path, data);
      gm.loadSaveFiles();
      sent = data;
    } catch (e) {
      console.warn("The save from the Pi didn't load", e);
    }
  }
  async function momentFromPi() {                 // where you were on the Pi, picked up (once the save's in)
    const gm = manager();
    if (!gm || !pickUp) return;
    try {
      const r = await fetch("/api/file?folder=games&download=1&path=" + encodeURIComponent(moment), { cache: "no-store" });
      if (!r.ok) return;
      const data = new Uint8Array(await r.arrayBuffer());
      if (data.length) gm.loadState(data);
    } catch (e) {
      console.warn("Where you were on the Pi didn't load", e);
    }
  }
  function rawState(s) {                          // the emulator's own state, out of RetroArch's wrapping ("RASTATE",
    const text = (at, n) => String.fromCharCode(...s.subarray(at, at + n));   // then blocks of an id, a size and that
    if (s.length < 8 || text(0, 7) !== "RASTATE") return s;                   // much, each padded to 8 bytes: the
    const dv = new DataView(s.buffer, s.byteOffset, s.byteLength);            // emulator's is MEM's), as the Pi keeps it
    for (let at = 8; at + 8 <= s.length;) {
      const id = text(at, 4), size = dv.getUint32(at + 4, true);
      if (id === "MEM ") return at + 8 + size <= s.length ? s.slice(at + 8, at + 8 + size) : null;
      if (id === "END ") break;
      at += 8 + size + ((8 - size % 8) % 8);
    }
    return null;
  }
  function momentToPi() {                         // where you are, back to the Pi as it's closed (after the save)
    const gm = manager();
    if (!started || !gm || !moment) return Promise.resolve(true);
    let data = null;
    try { data = rawState(gm.getState()); } catch (e) { return Promise.resolve(false); }
    if (!data || !data.length) return Promise.resolve(false);
    turn = turn.then(async () => {
      try {
        const r = await fetch("/api/upload?folder=games&exists=replace&path=" + encodeURIComponent(moment),
          { method: "PUT", body: data, headers: { "Content-Type": "application/octet-stream" } });
        return r.ok;
      } catch (e) {
        return false;
      }
    });
    return turn;
  }
  function toPi(data) {                           // the save back to the Pi, if it's changed (one at a time)
    turn = turn.then(async () => {
      if (!save || !data || !data.length || same(data, sent)) return true;
      try {
        const r = await fetch("/api/upload?folder=games&exists=replace&path=" + encodeURIComponent(save),
          { method: "PUT", body: data, headers: { "Content-Type": "application/octet-stream" } });
        if (r.ok) sent = data.slice();
        return r.ok;
      } catch (e) {
        return false;
      }
    });
    return turn;
  }
  function saveNow() {
    const gm = manager();
    if (!started || !gm) return Promise.resolve(true);
    try { return toPi(gm.getSaveFile()); } catch (e) { return Promise.resolve(false); }
  }

  window.addEventListener("message", async (e) => {
    if (e.source !== parent || e.origin !== location.origin || !e.data) return;
    if (e.data.pietato === "button") {            // the web page's remote (or its keyboard): a button, down or up
      const gm = manager(), name = String(e.data.name);
      if (gm && started && Object.prototype.hasOwnProperty.call(IDS, name)) {
        gm.simulateInput(0, IDS[name], e.data.down ? 1 : 0);
      }
      return;
    }
    if (e.data.pietato === "menu") {              // ...its Hotkey: the emulator's own buttons (save, load...)
      if (started && window.EJS_emulator.menu) window.EJS_emulator.menu.toggle();
      return;
    }
    if (e.data.pietato !== "close") return;
    const saved = await saveNow();
    const moved = await momentToPi();
    tell({ closed: true, saved, moved });
  });
  document.addEventListener("visibilitychange", () => { if (document.hidden) saveNow(); });   // (a phone put away)
  const PAGE_KEYS = new Set(["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Enter", "Escape", "Backspace",
                             "x", "X", "y", "Y", "[", "]"]);   // (the web page's keys for its remote's buttons)
  for (const type of ["keydown", "keyup"]) {      // ...here too: to the web page, which says which buttons they are,
    window.addEventListener(type, (e) => {        //  as it does when it has the keyboard (the emulator's own
      if (!PAGE_KEYS.has(e.key) || e.ctrlKey || e.metaKey || e.altKey) return;   // keys for them aren't its)
      e.preventDefault();
      e.stopImmediatePropagation();
      if (!e.repeat) tell({ key: e.key, down: type === "keydown" });
    }, true);
  }

  async function start() {
    const pkg = CORES[core];
    if (!pkg || !rom) return say("That game can't play here", true);
    say("Getting the emulator ready…");
    let r = null;
    try { r = await fetch("/api/ejs?core=" + encodeURIComponent(pkg), { method: "POST", headers: { "X-Pitato-Page": "1" } }); }
    catch (e) { return say("The Pi isn't answering", true); }
    if (!r.ok) {
      let why = "The Pi couldn't get the emulator";
      try { why = (await r.json()).error || why; } catch (e) {}
      return say(why, true);
    }
    note.hidden = true;
    const touch = matchMedia("(pointer: coarse)").matches;   // (a phone: its Start, tapped, lets its sound play)
    Object.assign(window, {
      EJS_player: "#game", EJS_core: core, EJS_gameUrl: home(rom), EJS_gameName: q.get("name") || "Game",
      EJS_pathtodata: "/ejs/data/", EJS_startOnLoaded: !touch, EJS_startButtonName: "Start",
      EJS_language: "en-US", EJS_disableAutoLang: false, EJS_noAutoFocus: true,   // (the web page keeps the keyboard)
      EJS_color: color, EJS_backgroundColor: "#000000", EJS_biosUrl: bios ? home(bios) : "",
      EJS_defaultOptions: { "save-save-interval": "30",      // (the game's save, every half a minute: to the Pi too)
        "virtual-gamepad": "disabled" },                     // (no buttons of its own: the web page's remote, or a
                                                             //  controller of yours, is the game's)
      EJS_ready: () => window.EJS_emulator.on("saveSaveFiles", (data) => { if (started) toPi(data); }),   // (not
                                                      // before the Pi's save is in: it'd take its place with none)
      EJS_onGameStart: async () => {
        const ejs = window.EJS_emulator;
        if (ejs.toggleVirtualGamepad) ejs.toggleVirtualGamepad(false);   // (a phone's too)
        setTimeout(() => { if (ejs.menu) ejs.menu.close(); }, 100);      // (its own buttons: HOME brings them)
        await fromPi();
        await momentFromPi();
        started = true;
        tell({ started: true });
      },
    });
    const s = document.createElement("script");
    s.src = "/ejs/data/loader.js";
    s.onerror = () => say("The emulator didn't load", true);
    document.body.append(s);
  }
  start();
})();
