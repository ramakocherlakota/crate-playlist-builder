// Spotify for Crate: sign-in (authorization code with PKCE, no client secret), paced API calls that respect
// Spotify's rate limits, loading the user's library, and applying playlist changes. Exposed as window.CrateSpotify.
(function () {
  const CLIENT_ID = "7a1b81580d3842c7aa6c646b75c9a798";
  const REDIRECT_URI = location.origin + "/";
  const SCOPES = "user-library-read playlist-read-private playlist-read-collaborative playlist-modify-private playlist-modify-public";
  const API = "https://api.spotify.com/v1";
  const AUTH_KEY = "crate-spotify-auth", PKCE_KEY = "crate-spotify-pkce";

  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const ls = {
    get: k => { try { return JSON.parse(localStorage.getItem(k) || "null"); } catch (e) { return null; } },
    set: (k, v) => { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} },
  };
  const clock = t => new Date(t).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  const fail = (message, extra) => Object.assign(new Error(message), extra);

  // ---------- sign-in ----------
  const b64url = bytes => btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  const randomString = n => { const a = new Uint8Array(n); crypto.getRandomValues(a); return b64url(a); };
  let auth = ls.get(AUTH_KEY);  // {access, refresh, expiresAt, scope}
  // A sign-in saved before Crate asked for different permissions can't do everything; ask for a fresh one.
  const missingScopes = a => SCOPES.split(" ").filter(x => !(a.scope || "").split(" ").includes(x));
  if (auth && missingScopes(auth).length) { auth = null; ls.set(AUTH_KEY, null); }

  async function connect() {
    const verifier = randomString(64), state = "sp_" + randomString(16);
    const challenge = b64url(new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier))));
    ls.set(PKCE_KEY, { verifier, state });
    const q = new URLSearchParams({ response_type: "code", client_id: CLIENT_ID, scope: SCOPES, redirect_uri: REDIRECT_URI, code_challenge_method: "S256", code_challenge: challenge, state });
    location.assign("https://accounts.spotify.com/authorize?" + q);
  }
  async function tokenRequest(params) {
    const r = await fetch("https://accounts.spotify.com/api/token", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: new URLSearchParams({ client_id: CLIENT_ID, ...params }) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error_description || j.error || "Spotify sign-in failed");
    auth = { access: j.access_token, refresh: j.refresh_token || auth?.refresh, expiresAt: Date.now() + (j.expires_in - 60) * 1000, scope: j.scope || auth?.scope || SCOPES };
    ls.set(AUTH_KEY, auth);
  }
  const isReturningFromSignIn = () => /[?&](code|error)=/.test(location.search) && /[?&]state=sp_/.test(location.search);
  // Completes a sign-in when Spotify has just sent the browser back here. Returns true if it connected.
  async function finishSignIn() {
    if (!isReturningFromSignIn()) return false;
    const q = new URLSearchParams(location.search);
    const pkce = ls.get(PKCE_KEY); ls.set(PKCE_KEY, null);
    history.replaceState(null, "", location.pathname);
    if (q.get("error")) throw fail(q.get("error") === "access_denied" ? "Spotify sign-in was cancelled." : `Spotify sign-in failed: ${q.get("error")}`);
    if (!pkce || pkce.state !== q.get("state")) throw fail("That sign-in reply didn't match this browser. Press Connect Spotify again.");
    await tokenRequest({ grant_type: "authorization_code", code: q.get("code"), redirect_uri: REDIRECT_URI, code_verifier: pkce.verifier });
    return true;
  }
  // One shared refresh: Spotify rotates refresh tokens, so two parallel refreshes would sign the user out.
  let refreshing = null;
  async function accessToken() {
    if (!auth) throw fail("Not connected to Spotify. Press Connect Spotify.", { fatal: true, signedOut: true });
    if (Date.now() > auth.expiresAt) {
      refreshing = refreshing || tokenRequest({ grant_type: "refresh_token", refresh_token: auth.refresh }).finally(() => { refreshing = null; });
      try { await refreshing; }
      catch (e) { disconnect(); throw fail("Your Spotify sign-in expired. Press Connect Spotify again.", { fatal: true, signedOut: true }); }
    }
    return auth.access;
  }
  function disconnect() { auth = null; ls.set(AUTH_KEY, null); }

  // ---------- paced API calls ----------
  // One request at a time with a gap between them. Each "slow down" (429) doubles the gap and backs off
  // (Spotify's Retry-After when readable, otherwise 5s, 10s, 20s… up to 10 minutes); successes shrink the gap
  // again. A spent development-mode quota, or a wait over 15 minutes, stops with an explanation instead.
  const MIN_GAP = 300, MAX_GAP = 5000, MAX_WAIT = 15 * 60 * 1000;
  let pauseUntil = 0, nextSlot = 0, gap = MIN_GAP, slowDowns = 0;
  let onWait = () => {};  // UI hook: called with a message while waiting for Spotify

  // Requests that create or add (POST) are not repeated after a lost response or server error, since Spotify
  // may already have done the work.
  async function api(path, { method = "GET", body, query } = {}) {
    const url = /^https:/.test(path) ? path : API + path + (query ? "?" + new URLSearchParams(query) : "");
    const repeatable = method !== "POST";
    const unsure = () => fail("Spotify didn't confirm the last change, so Crate stopped rather than risk doing it twice. Press Refresh from Spotify to see what's there now, then apply again.", { unsure: true, fatal: true });
    for (let attempt = 0; attempt < 8; ) {
      const start = Math.max(Date.now(), pauseUntil, nextSlot); nextSlot = start + gap;
      if (start > Date.now()) await sleep(start - Date.now());
      if (pauseUntil > Date.now()) continue;
      const token = await accessToken();
      let r;
      try { r = await fetch(url, { method, headers: { Authorization: "Bearer " + token, ...(body ? { "Content-Type": "application/json" } : {}) }, body: body ? JSON.stringify(body) : undefined }); }
      catch (e) { if (!repeatable) throw unsure(); attempt++; await sleep(1500 * attempt); continue; }
      if (r.status === 429) {
        slowDowns++;
        let why = "";
        try { const j = await r.json(); why = [j?.error?.reason, j?.error?.message].filter(Boolean).join(": "); } catch (e) {}
        const told = Number(r.headers.get("Retry-After"));
        if (/quota/i.test(why)) throw fail(`Spotify says the Crate app's development-mode quota is used up, so it's refusing requests for now${told > 0 ? `; it suggests trying again around ${clock(Date.now() + told * 1000)}` : ""}. Retrying sooner won't help. (Spotify said: “${why}”)`, { fatal: true });
        const wait = told > 0 ? told * 1000 + 500 : Math.min(5000 * 2 ** (slowDowns - 1), 10 * 60 * 1000);
        gap = Math.min(MAX_GAP, gap * 2);
        if (wait > MAX_WAIT) throw fail(`Spotify asked Crate to pause until about ${clock(Date.now() + wait)}. Try again after that.${why ? ` (Spotify said: “${why}”)` : ""}`, { fatal: true });
        pauseUntil = Math.max(pauseUntil, Date.now() + wait);
        onWait(`Spotify asked Crate to slow down${told > 0 ? ` for ${told}s` : ""}; continuing around ${clock(pauseUntil)}…`);
        continue;
      }
      slowDowns = 0; gap = Math.max(MIN_GAP, gap * 0.97);
      if (r.status === 401 && attempt === 0 && auth) { attempt++; auth.expiresAt = 0; continue; }
      if (r.status >= 500) { if (!repeatable) throw unsure(); attempt++; await sleep(1500 * attempt); continue; }
      if (!r.ok) {
        let msg = ""; try { msg = (await r.json()).error?.message || ""; } catch (e) {}
        const err = fail(msg || `Spotify answered ${r.status}`, { status: r.status });
        if (r.status === 403) {
          err.fatal = true;
          // Development-mode apps refuse accounts that aren't allowlisted, and everything if the owner lacks Premium.
          err.message = /scope/i.test(msg)
            ? "Spotify says the sign-in is missing a permission (403). Press Disconnect Spotify, then Connect Spotify and approve again."
            : /premium/i.test(msg)
            ? "Spotify says Premium is required (403). The account that owns the Crate developer app needs active Premium; a new subscription can take a few hours to register."
            : /regist|allowlist|whitelist/i.test(msg)
            ? "Spotify says this account isn't allowed to use the app (403). In the Spotify developer dashboard, open the Crate app → User Management and add the name and email of the account you sign in with."
            : "Spotify refused (403). Check that the Crate developer app's owner has Premium and that your account is listed under User Management in the dashboard.";
          if (msg) err.message += ` (Spotify said: “${msg}”)`;
        }
        throw err;
      }
      return r.status === 204 ? null : r.json().catch(() => null);
    }
    throw fail("Spotify kept failing to answer. Try again in a few minutes.", { fatal: true });
  }
  // Follows Spotify's "next" links through a paged list.
  async function allPages(path, query) {
    const out = [];
    let j = await api(path, { query });
    while (j) {
      out.push(...(j.items || []));
      j = j.next ? await api(j.next) : null;
    }
    return out;
  }
  // Playlist entries hold the song under "item" (2026 API) or "track" (older responses).
  const entryTrack = e => { const t = e && (typeof e.item === "object" ? e.item : typeof e.track === "object" ? e.track : null); return t && t.type !== "episode" ? t : null; };

  // ---------- library ----------
  // Builds Crate's library from Liked Songs, saved albums, and the songs in the user's own playlists.
  // Track ids are Spotify track ids and pid is the URI; playlist pid is the Spotify playlist id.
  async function loadLibrary(progress = () => {}) {
    const me = await api("/me");
    const tracks = new Map();
    const add = (t, album, added) => {
      if (!t || !t.id || t.is_local) return null;
      const al = album || t.album || {};
      const prev = tracks.get(t.id);
      if (prev) { if (added && (!prev.added || added < prev.added)) prev.added = added; return prev; }
      const rec = {
        id: t.id, pid: t.uri || `spotify:track:${t.id}`, name: t.name || "Untitled",
        artist: t.artists?.[0]?.name || "", albumArtist: al.artists?.[0]?.name || "", album: al.name || "",
        year: parseInt(al.release_date, 10) || 0, disc: t.disc_number || 1, num: t.track_number || 0, ms: t.duration_ms || 0,
        added: added || "", url: t.external_urls?.spotify || "",
      };
      tracks.set(t.id, rec);
      return rec;
    };
    progress("Loading Liked Songs…");
    for (const e of await allPages("/me/tracks", { limit: "50" })) add(e.track || e.item, null, e.added_at);
    progress(`Loading saved albums… (${tracks.size.toLocaleString()} songs so far)`);
    for (const e of await allPages("/me/albums", { limit: "50" })) {
      const al = e.album; if (!al) continue;
      let items = al.tracks?.items || [];
      if (al.tracks?.next) items = items.concat(await allPages(al.tracks.next));
      for (const t of items) add(t, al, e.added_at);
    }
    progress(`Loading your playlists… (${tracks.size.toLocaleString()} songs so far)`);
    const playlists = [];
    // Only playlists you own or collaborate on can be edited (and only their contents are readable).
    const mine = (await allPages("/me/playlists", { limit: "50" })).filter(p => p && (p.owner?.id === me.id || p.collaborative));
    for (const [i, p] of mine.entries()) {
      progress(`Loading playlist ${i + 1} of ${mine.length}: ${p.name}`);
      const ids = [];
      for (const e of await allPages(`/playlists/${p.id}/items`, { limit: "100" })) { const t = add(entryTrack(e), null, e.added_at); if (t) ids.push(t.id); }
      playlists.push({ name: p.name, pid: p.id, ids, url: p.external_urls?.spotify || "" });
    }
    return { tracks: [...tracks.values()], playlists, account: me.display_name || me.id };
  }

  // ---------- applying changes ----------
  let removeShape = null;  // which body shape Spotify's remove endpoint accepted: "items" or "tracks"
  async function removeFromPlaylist(id, uris) {
    const shapes = removeShape ? [removeShape] : ["items", "tracks"];
    let last;
    for (const shape of shapes) {
      try { await api(`/playlists/${id}/items`, { method: "DELETE", body: { [shape]: uris.map(uri => ({ uri })) } }); removeShape = shape; return; }
      catch (e) { last = e; if (e.fatal || e.status !== 400) throw e; }
    }
    throw last;
  }
  // Applies one playlist's changes: create or rename it, remove unticked songs, append newly ticked ones.
  // Returns the Spotify playlist id and link.
  async function applyPlaylist({ id, name, renamed, addUris, removeUris }, progress = () => {}) {
    let url = "";
    if (!id) {
      const made = await api("/me/playlists", { method: "POST", body: { name, public: false, description: "Made with Crate" } });
      id = made.id; url = made.external_urls?.spotify || "";
    } else if (renamed) {
      await api(`/playlists/${id}`, { method: "PUT", body: { name } });
    }
    for (let i = 0; i < removeUris.length; i += 100) { progress(`${name}: removing songs…`); await removeFromPlaylist(id, removeUris.slice(i, i + 100)); }
    let addReply = null;
    for (let i = 0; i < addUris.length; i += 100) { progress(`${name}: adding songs…`); addReply = await api(`/playlists/${id}/items`, { method: "POST", body: { uris: addUris.slice(i, i + 100) } }); }
    if (addUris.length || removeUris.length) await verifyPlaylist(id, name, addUris, removeUris, addReply, progress);
    return { id, url };
  }
  // Reads the playlist back and confirms Spotify really made the changes (a 2xx alone has proved not to be enough).
  async function verifyPlaylist(id, name, addUris, removeUris, addReply, progress) {
    let entries = [], have = new Set();
    for (let tries = 0; tries < 2; tries++) {
      if (tries) { progress(`${name}: waiting for Spotify to catch up…`); await sleep(3000); }
      progress(`${name}: checking the result…`);
      entries = await allPages(`/playlists/${id}/items`, { limit: "100" });
      have = new Set(entries.map(e => entryTrack(e)?.uri).filter(Boolean));
      if (addUris.every(u => have.has(u)) && removeUris.every(u => !have.has(u))) return;
    }
    const notAdded = addUris.filter(u => !have.has(u)), notRemoved = removeUris.filter(u => have.has(u));
    const parts = [];
    if (notAdded.length) parts.push(`${notAdded.length} of ${addUris.length} added songs aren't there`);
    if (notRemoved.length) parts.push(`${notRemoved.length} of ${removeUris.length} removed songs are still there`);
    // Details for diagnosis: what Spotify answered, and what a playlist entry looks like when read back.
    const sample = entries[0] ? Object.keys(entries[0]).join(", ") : "none";
    throw fail(`Spotify accepted the changes to “${name}”, but reading it back, ${parts.join(" and ")}. Nothing in Crate was marked as applied, so you can try again. (Read back ${entries.length} entries, ${have.size} readable; entry fields: ${sample}; Spotify's reply to adding: ${addReply ? JSON.stringify(addReply).slice(0, 200) : "none"})`, { fatal: true });
  }

  window.CrateSpotify = {
    connected: () => !!auth,
    connect, finishSignIn, isReturningFromSignIn,
    disconnect,
    loadLibrary, applyPlaylist,
    set onWait(fn) { onWait = fn || (() => {}); },
  };
})();
