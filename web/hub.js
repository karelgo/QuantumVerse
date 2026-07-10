// hub.js — the QuantumVerse hub: a browse surface over a registry's public
// objects (artifacts, capsules, devices, leaderboards). Pure front end over the
// existing REST API; hash-routed, no build step.

const API = './api/v1';

// ---- tiny DOM helpers -------------------------------------------------------

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null) continue;
    if (k === 'class') node.className = v;
    else if (k === 'html') node.innerHTML = v;      // callers pass only escaped/derived HTML
    else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c == null) continue;
    node.append(c.nodeType ? c : document.createTextNode(String(c)));
  }
  return node;
}

const $app = () => document.getElementById('view');

async function api(path) {
  const resp = await fetch(`${API}${path}`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status} for ${path}`);
  return resp.json();
}

async function blobText(digest) {
  const resp = await fetch(`${API}/blobs/${digest}`);
  if (!resp.ok) throw new Error(`blob ${digest} HTTP ${resp.status}`);
  return resp.text();
}

const TRUST = {
  0: { badge: '·', label: 'unsigned', cls: 'trust-0' },
  1: { badge: '✓', label: 'author-signed', cls: 'trust-1' },
  2: { badge: '✓✓', label: 'provider-verified', cls: 'trust-2' },
};

function trustChip(level) {
  const t = TRUST[level] ?? { badge: '?', label: 'unknown', cls: 'trust-0' };
  return el('span', { class: `chip ${t.cls}`, title: `trust level ${level}: ${t.label}` },
    `${t.badge} ${t.label}`);
}

function short(id) {
  return id && id.startsWith('sha256:') ? id.slice(7, 13) : (id || '').slice(0, 6);
}

function typeChip(type) {
  return el('span', { class: 'chip type' }, type);
}

function setActiveNav(route) {
  document.querySelectorAll('nav.hub-nav a').forEach((a) => {
    a.classList.toggle('active', a.dataset.route === route);
  });
}

function loading() {
  $app().replaceChildren(el('p', { class: 'muted mono' }, 'loading…'));
}

function errorView(err) {
  $app().replaceChildren(
    el('div', { class: 'empty' },
      el('h2', {}, 'Nothing to show'),
      el('p', { class: 'muted' }, String(err.message || err)),
      el('p', { class: 'muted small' },
        'Is a registry running? Serve one with ',
        el('code', {}, 'qv-registry --web web/'), ' and seed it with ',
        el('code', {}, 'python seeds/import.py'), '.')));
}

function crumbs(...parts) {
  const row = el('div', { class: 'crumbs mono' });
  parts.forEach((p, i) => {
    if (i) row.append(el('span', { class: 'sep' }, '/'));
    row.append(typeof p === 'string' ? document.createTextNode(p) : p);
  });
  return row;
}

function link(text, href, cls) {
  return el('a', { href, class: cls || 'link' }, text);
}

// ---- artifacts --------------------------------------------------------------

function resourceLine(card) {
  const r = (card && card.resources) || {};
  if (r.num_qubits == null) return null;
  const bits = [
    `${r.num_qubits}q`, `depth ${r.depth}`,
    `2q ${r.two_qubit_gate_count}`, `T ${r.t_count}`,
  ];
  if (r.num_parameters) bits.push(`${r.num_parameters} param${r.num_parameters > 1 ? 's' : ''}`);
  return el('div', { class: 'res mono' }, bits.join(' · '));
}

async function viewArtifacts(params) {
  setActiveNav('artifacts');
  loading();
  const type = params.get('type') || '';
  const { artifacts } = await api(`/artifacts${type ? `?type=${type}` : ''}`);
  const filters = el('div', { class: 'filters' },
    ...['', 'circuit', 'parameters', 'instance', 'noise-model'].map((t) =>
      el('a', {
        href: `#/artifacts${t ? `?type=${t}` : ''}`,
        class: `filter ${t === type ? 'active' : ''}`,
      }, t || 'all')));

  const grid = el('div', { class: 'grid' });
  for (const a of artifacts) {
    const latest = a.versions[a.versions.length - 1];
    const card = (a.cards && a.cards[latest]) || {};
    grid.append(el('a', { href: `#/artifacts/${a.namespace}/${a.name}`, class: 'tile' },
      el('div', { class: 'tile-head' },
        el('span', { class: 'tile-name mono' }, `${a.namespace}/${a.name}`),
        typeChip(a.type)),
      card.summary ? el('p', { class: 'tile-summary' }, card.summary) : null,
      resourceLine(card),
      el('div', { class: 'tile-foot mono' }, `${a.versions.length} version${a.versions.length > 1 ? 's' : ''} · @${latest}`)));
  }
  $app().replaceChildren(
    el('h1', {}, 'Artifacts'),
    el('p', { class: 'muted' }, 'Circuits, trained parameters, problem instances, and noise models.'),
    filters,
    artifacts.length ? grid : el('p', { class: 'muted' }, 'No artifacts yet.'));
}

async function viewArtifact(ns, name) {
  setActiveNav('artifacts');
  loading();
  const meta = await api(`/artifacts/${ns}/${name}`);
  const resolved = await api(`/artifacts/${ns}/${name}/resolve?version=latest`);
  const card = resolved.card || {};
  const payloadPath = Object.keys(resolved.files)[0];
  let payload = '';
  try { payload = await blobText(resolved.files[payloadPath]); } catch { /* ignore */ }

  const sections = [];

  // Circuit Card: computed vs claimed vs verified must be visually distinct (RFC-0002)
  if (card.resources) {
    const r = card.resources;
    const rows = [
      ['qubits', r.num_qubits], ['depth', r.depth],
      ['two-qubit gates', r.two_qubit_gate_count], ['T-count', r.t_count],
      ['parameters', r.num_parameters ?? 0],
    ];
    if (r.gate_counts) {
      rows.push(['gate counts', Object.entries(r.gate_counts).map(([g, n]) => `${g}:${n}`).join('  ')]);
    }
    sections.push(el('section', { class: 'card-block computed' },
      el('h3', {}, 'Resources ', el('span', { class: 'tag-computed' }, 'computed')),
      dl(rows)));
  }
  if (card.requirements) {
    const rq = card.requirements;
    sections.push(el('section', { class: 'card-block claimed' },
      el('h3', {}, 'Requirements ', el('span', { class: 'tag-claimed' }, 'declared')),
      dl([
        ['connectivity', rq.connectivity || '—'],
        ['native gates', (rq.native_gates || []).join(', ') || '—'],
      ])));
  }
  if (card.noise_profile) {
    const np = card.noise_profile;
    sections.push(el('section', { class: 'card-block claimed' },
      el('h3', {}, 'Noise profile ', el('span', { class: 'tag-claimed' }, 'declared')),
      dl([
        ['sensitivity', np.sensitivity || '—'],
        ['validated mitigation', (np.validated_mitigation || []).join(', ') || '—'],
      ])));
  }
  if (card.verified_results && card.verified_results.length) {
    sections.push(el('section', { class: 'card-block verified' },
      el('h3', {}, 'Verified results ', el('span', { class: 'tag-verified' }, 'capsule-backed')),
      el('ul', { class: 'plain' }, ...card.verified_results.map((v) =>
        el('li', {}, link(`capsule/${short(v.capsule)}`, `#/capsules/${short(v.capsule)}`, 'mono link'),
          v.backend ? ` on ${v.backend}` : '', v.note ? ` — ${v.note}` : '')))));
  }

  const prov = card.provenance || {};
  sections.push(el('section', { class: 'card-block' },
    el('h3', {}, 'Provenance'),
    dl([
      ['license', prov.license || '—'],
      ['authors', (prov.authors || []).join(', ') || '—'],
      prov.paper ? ['paper', el('a', { href: prov.paper, class: 'link', target: '_blank' }, prov.paper)] : null,
      prov.forked_from ? ['forked from', prov.forked_from] : null,
    ].filter(Boolean))));

  const isCircuit = payloadPath && payloadPath.endsWith('.qasm');
  const actions = el('div', { class: 'actions' },
    el('span', { class: 'mono muted' }, `versions: ${meta.versions.join(', ')}`),
    isCircuit ? el('a', {
      href: `./index.html#load=qv:${ns}/${name}`,
      class: 'btn',
    }, '▶ Run in playground') : null);

  $app().replaceChildren(
    crumbs(link('Artifacts', '#/artifacts'), `${ns}/${name}`),
    el('h1', {}, card.name || `${ns}/${name}`),
    card.summary ? el('p', { class: 'lead' }, card.summary) : null,
    el('div', { class: 'chips' }, typeChip(meta.type),
      ...((card.tags || []).map((t) => el('span', { class: 'chip' }, t)))),
    actions,
    el('div', { class: 'detail-grid' },
      el('div', {}, ...sections),
      el('div', {},
        el('h3', {}, isCircuit ? 'OpenQASM 3' : payloadPath || 'payload'),
        el('pre', { class: 'code' }, payload || '(payload unavailable)'))));
}

function dl(rows) {
  const d = el('dl', { class: 'kv' });
  for (const [k, v] of rows) {
    d.append(el('dt', {}, k), el('dd', { class: 'mono' }, v == null ? '—' : v));
  }
  return d;
}

// ---- capsules ---------------------------------------------------------------

async function viewCapsules() {
  setActiveNav('capsules');
  loading();
  const { capsules } = await api('/capsules');
  const rows = capsules.map((c) =>
    el('a', { href: `#/capsules/${short(c.id)}`, class: 'row' },
      el('span', { class: 'mono row-id' }, `capsule/${short(c.id)}`),
      el('span', { class: 'row-title' }, c.title || '(untitled)'),
      trustChip(c.trust ?? 0),
      el('span', { class: 'mono muted row-date' }, (c.created || '').slice(0, 10))));
  $app().replaceChildren(
    el('h1', {}, 'Capsules'),
    el('p', { class: 'muted' }, 'Content-addressed, replayable experiment records (RFC-0001).'),
    capsules.length ? el('div', { class: 'rows' }, ...rows)
      : el('p', { class: 'muted' }, 'No capsules yet.'));
}

async function viewCapsule(id) {
  setActiveNav('capsules');
  loading();
  const record = await api(`/capsules/${id}`);
  const files = record.files || {};
  const parsed = {};
  for (const name of ['manifest.json', 'device.json', 'execution.json', 'mitigation.json']) {
    if (files[name]) {
      try { parsed[name] = JSON.parse(await blobText(files[name])); } catch { /* ignore */ }
    }
  }
  const manifest = parsed['manifest.json'] || {};
  const device = parsed['device.json'] || {};
  const execution = parsed['execution.json'] || {};
  const backend = device.backend || {};
  const sim = device.simulator;

  const facts = dl([
    ['title', manifest.title],
    ['id', record.id],
    ['authors', (manifest.authors || []).map((a) => a.name || a).join(', ') || '—'],
    ['created', manifest.created],
    ['license', manifest.license],
    ['backend', `${backend.provider || '?'}/${backend.name || '?'} ${sim ? '(simulator)' : '(hardware)'}`],
    ['shots', execution.shots],
    manifest.replay_of ? ['replay of', `capsule/${short(manifest.replay_of)}`] : null,
    manifest.doi ? ['doi', manifest.doi] : null,
  ].filter(Boolean));

  // raw counts as simple bars
  const counts = execution.counts_raw || {};
  const total = Object.values(counts).reduce((a, b) => a + b, 0) || 1;
  const top = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 16);
  const bars = el('div', { class: 'bars' });
  for (const [k, v] of top) {
    bars.append(el('div', { class: 'bar-row' },
      el('span', { class: 'mono bar-key' }, k),
      el('div', { class: 'bar-track' }, el('div', { class: 'bar-fill', style: `width:${Math.max(1, 100 * v / total)}%` })),
      el('span', { class: 'mono muted bar-val' }, v)));
  }

  const fileList = el('ul', { class: 'plain mono small' },
    ...Object.keys(files).sort().map((n) => el('li', {}, n)));

  $app().replaceChildren(
    crumbs(link('Capsules', '#/capsules'), `capsule/${short(record.id)}`),
    el('h1', {}, manifest.title || `capsule/${short(record.id)}`),
    el('div', { class: 'chips' }, trustChip(record.trust ?? 0),
      sim ? el('span', { class: 'chip' }, 'simulator') : el('span', { class: 'chip' }, 'hardware')),
    el('div', { class: 'detail-grid' },
      el('div', {}, el('section', { class: 'card-block' }, el('h3', {}, 'Manifest'), facts),
        el('section', { class: 'card-block' }, el('h3', {}, 'Files'), fileList)),
      el('div', {}, el('section', { class: 'card-block computed' },
        el('h3', {}, 'Raw counts ', el('span', { class: 'tag-computed' }, `${total} shots`)),
        top.length ? bars : el('p', { class: 'muted' }, 'no counts')))));
}

// ---- devices ----------------------------------------------------------------

async function viewDevices() {
  setActiveNav('devices');
  loading();
  const { devices } = await api('/devices');
  const grid = el('div', { class: 'grid' });
  for (const d of devices) {
    const rec = d.record || {};
    const cert = d.certificate;
    grid.append(el('a', { href: `#/devices/${d.namespace}/${d.name}`, class: 'tile' },
      el('div', { class: 'tile-head' },
        el('span', { class: 'tile-name mono' }, `${d.namespace}/${d.name}`),
        el('span', { class: 'chip type' }, rec.modality || '?')),
      rec.summary ? el('p', { class: 'tile-summary' }, rec.summary) : null,
      el('div', { class: 'tile-foot mono' },
        `${d.capsule_count} capsule${d.capsule_count === 1 ? '' : 's'} · ${d.calibration_count} snapshot${d.calibration_count === 1 ? '' : 's'}`),
      cert ? el('div', { class: `cert-badge ${cert.passed ? 'ok' : 'fail'}` },
        cert.passed ? '✓ birth certificate' : '✗ certificate failed') : null));
  }
  $app().replaceChildren(
    el('h1', {}, 'Devices'),
    el('p', { class: 'muted' }, 'A profile page for every machine — cloud-hosted or lab-built (RFC-0004).'),
    devices.length ? grid : el('p', { class: 'muted' }, 'No devices registered yet.'));
}

async function viewDevice(owner, name) {
  setActiveNav('devices');
  loading();
  const card = await api(`/devices/${owner}/${name}`);
  const { calibrations } = await api(`/devices/${owner}/${name}/calibrations?limit=30`);
  let capsules = [];
  try { capsules = (await api(`/devices/${owner}/${name}/capsules`)).capsules; } catch { /* ignore */ }
  const rec = card.record || {};
  const lin = rec.lineage || {};

  const sections = [];
  sections.push(el('section', { class: 'card-block' }, el('h3', {}, 'Record'),
    dl([
      ['modality', rec.modality],
      ['backend id', `${rec.backend.provider}/${rec.backend.name}`],
      ['architecture', lin.architecture || '—'],
      ['fab', lin.fab || '—'],
      ['generation', lin.generation || '—'],
      ['commissioned', lin.commissioned || '—'],
    ])));

  if (card.certificate) {
    const c = card.certificate;
    const checks = el('ul', { class: 'plain mono small' }, ...c.checks.map((ch) =>
      el('li', { class: ch.pass ? 'pass' : 'fail' },
        `${ch.pass ? 'PASS' : 'FAIL'}  ${ch.name}  tv=${ch.tv_distance} (max ${ch.threshold})`)));
    sections.push(el('section', { class: `card-block ${c.passed ? 'verified' : 'claimed'}` },
      el('h3', {}, 'Birth certificate ',
        el('span', { class: c.passed ? 'tag-verified' : 'tag-claimed' }, c.passed ? 'PASSED' : 'FAILED')),
      el('p', { class: 'mono small muted' }, `${c.suite} · width ${c.width} · ${c.issued}`),
      checks));
  }

  // drift timeline
  const drift = el('div', { class: 'timeline' });
  for (const cal of calibrations) {
    const s = cal.summary || {};
    const stat = Object.entries(s).map(([k, v]) => `${k} ${v}`).join(' · ');
    drift.append(el('div', { class: 'tl-row' },
      el('span', { class: 'mono muted tl-when' }, (cal.captured || '').replace('T', ' ').replace('Z', '')),
      el('span', { class: 'mono tl-stat' }, stat || '—'),
      cal.capsule ? link(`capsule/${short(cal.capsule)}`, `#/capsules/${short(cal.capsule)}`, 'mono link small') : el('span', { class: 'muted small' }, 'direct')));
  }

  $app().replaceChildren(
    crumbs(link('Devices', '#/devices'), `${owner}/${name}`),
    el('h1', {}, `${owner}/${name}`),
    rec.summary ? el('p', { class: 'lead' }, rec.summary) : null,
    el('div', { class: 'chips' }, el('span', { class: 'chip type' }, rec.modality || '?'),
      card.certificate ? el('span', { class: `chip ${card.certificate.passed ? 'trust-2' : 'trust-0'}` },
        card.certificate.passed ? '✓ certified' : '✗ certificate failed') : null),
    el('div', { class: 'detail-grid' },
      el('div', {}, ...sections),
      el('div', {}, el('section', { class: 'card-block' },
        el('h3', {}, 'Calibration timeline ', el('span', { class: 'tag-computed' }, 'from capsules')),
        calibrations.length ? drift : el('p', { class: 'muted' }, 'no calibration history yet')))));
}

// ---- leaderboards -----------------------------------------------------------

async function viewBoards() {
  setActiveNav('boards');
  loading();
  const { leaderboards } = await api('/leaderboards');
  const rows = leaderboards.map((b) =>
    el('a', { href: `#/boards/${b.name}`, class: 'row' },
      el('span', { class: 'row-title' }, b.title),
      el('span', { class: 'mono muted' }, b.metric),
      el('span', { class: 'mono muted row-date' }, `${b.entry_count} entr${b.entry_count === 1 ? 'y' : 'ies'}`)));
  $app().replaceChildren(
    el('h1', {}, 'Leaderboards'),
    el('p', { class: 'muted' }, 'Every score recomputed by the registry from a capsule’s raw counts (RFC-0006).'),
    leaderboards.length ? el('div', { class: 'rows' }, ...rows)
      : el('p', { class: 'muted' }, 'No leaderboards yet.'));
}

async function viewBoard(name) {
  setActiveNav('boards');
  loading();
  const board = await api(`/leaderboards/${name}`);
  const table = el('table', { class: 'board' },
    el('thead', {}, el('tr', {},
      el('th', {}, '#'), el('th', {}, 'score'), el('th', {}, 'backend'),
      el('th', {}, 'shots'), el('th', {}, 'trust'), el('th', {}, 'capsule'))));
  const tbody = el('tbody');
  for (const e of board.entries || []) {
    tbody.append(el('tr', {},
      el('td', { class: 'rank' }, `#${e.rank}`),
      el('td', { class: 'mono score' }, e.score.toFixed(6)),
      el('td', { class: 'mono' }, e.backend),
      el('td', { class: 'mono muted' }, e.shots),
      el('td', {}, trustChip(e.trust ?? 0)),
      el('td', {}, link(`capsule/${short(e.capsule)}`, `#/capsules/${short(e.capsule)}`, 'mono link'))));
  }
  table.append(tbody);
  $app().replaceChildren(
    crumbs(link('Leaderboards', '#/boards'), name),
    el('h1', {}, board.title),
    el('p', { class: 'mono muted' }, `${board.metric} on ${board.instance} · ${board.higher_is_better ? 'higher is better' : 'lower is better'}`),
    (board.entries || []).length ? table : el('p', { class: 'muted' }, 'No entries yet.'));
}

// ---- search + home ----------------------------------------------------------

async function viewSearch(params) {
  setActiveNav('');
  loading();
  const q = params.get('q') || '';
  const { results } = await api(`/search?q=${encodeURIComponent(q)}`);
  const rows = results.map((r) =>
    el('a', { href: `#/artifacts/${r.namespace}/${r.name}`, class: 'row' },
      el('span', { class: 'mono row-id' }, `${r.namespace}/${r.name}`),
      typeChip(r.type),
      el('span', { class: 'row-title' }, r.summary || ''),
      el('span', { class: 'mono muted row-date' }, r.latest ? `@${r.latest}` : '')));
  $app().replaceChildren(
    el('h1', {}, `Search: “${q}”`),
    results.length ? el('div', { class: 'rows' }, ...rows)
      : el('p', { class: 'muted' }, 'No matches.'));
}

async function viewHome() {
  setActiveNav('home');
  loading();
  const [arts, caps, devs, boards] = await Promise.all([
    api('/artifacts').catch(() => ({ artifacts: [] })),
    api('/capsules').catch(() => ({ capsules: [] })),
    api('/devices').catch(() => ({ devices: [] })),
    api('/leaderboards').catch(() => ({ leaderboards: [] })),
  ]);
  const stat = (n, label, href) => el('a', { href, class: 'stat' },
    el('span', { class: 'stat-n' }, n), el('span', { class: 'stat-l' }, label));
  $app().replaceChildren(
    el('div', { class: 'hero' },
      el('h1', {}, 'The home for quantum artifacts'),
      el('p', { class: 'lead' },
        'Browse circuits, trained parameters, verified experiment capsules, the machines that ran them, and the leaderboards that rank them — every result recomputed, never claimed.')),
    el('div', { class: 'stats' },
      stat(arts.artifacts.length, 'artifacts', '#/artifacts'),
      stat(caps.capsules.length, 'capsules', '#/capsules'),
      stat(devs.devices.length, 'devices', '#/devices'),
      stat(boards.leaderboards.length, 'leaderboards', '#/boards')));
}

// ---- router -----------------------------------------------------------------

async function route() {
  const raw = location.hash.slice(1) || '/';
  const [path, query] = raw.split('?');
  const params = new URLSearchParams(query || '');
  const parts = path.split('/').filter(Boolean);
  try {
    if (parts.length === 0) return await viewHome();
    switch (parts[0]) {
      case 'artifacts':
        return parts.length >= 3 ? await viewArtifact(parts[1], parts[2]) : await viewArtifacts(params);
      case 'capsules':
        return parts.length >= 2 ? await viewCapsule(parts[1]) : await viewCapsules();
      case 'devices':
        return parts.length >= 3 ? await viewDevice(parts[1], parts[2]) : await viewDevices();
      case 'boards':
        return parts.length >= 2 ? await viewBoard(parts[1]) : await viewBoards();
      case 'search':
        return await viewSearch(params);
      default:
        return await viewHome();
    }
  } catch (err) {
    errorView(err);
  }
}

export function start() {
  const box = document.getElementById('search-box');
  if (box) {
    box.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && box.value.trim()) {
        location.hash = `#/search?q=${encodeURIComponent(box.value.trim())}`;
      }
    });
  }
  window.addEventListener('hashchange', route);
  route();
}
