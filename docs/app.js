const DATA_URL = './data.json';
const BERLIN_TIMEZONE = 'Europe/Berlin';
const INSTALL_DISMISS_KEY = 'bundesliga-install-dismissed';
const INSTALL_DISMISS_MS = 30 * 24 * 60 * 60 * 1000;

let data = null;
let selectedMatchday = 1;
let currentView = 'matches';
let loadedFromCache = false;
let refreshProblem = false;
let deferredInstallPrompt = null;
let installMode = null;
let hasMeaningfulInteraction = false;

const app = document.getElementById('app');
const meta = document.getElementById('meta');
const installBanner = document.getElementById('install-banner');

function esc(value) {
  return String(value ?? '').replace(/[&<>'"]/g, char => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;' })[char]);
}

function initials(name) {
  return String(name || '?').split(/\s+/).filter(Boolean).slice(0, 2)
    .map(part => part.replace(/[^A-Za-zÄÖÜäöüß0-9]/g, '').charAt(0)).join('').toUpperCase() || '⚽';
}

function teamLogo(team, extraClass = '') {
  const classes = ['club-fallback', extraClass].filter(Boolean).join(' ');
  const fallback = `<span class="${classes}" aria-hidden="true">${esc(initials(team.name))}</span>`;
  if (!team.logo) return fallback;
  return `<span class="club-mark ${esc(extraClass)}"><img src="${esc(team.logo)}" alt="${esc(team.name)} Wappen" loading="lazy" decoding="async" onerror="this.hidden=true;this.nextElementSibling.hidden=false"><span class="club-fallback" hidden aria-hidden="true">${esc(initials(team.name))}</span></span>`;
}

function formatLocalDate(value) {
  return new Intl.DateTimeFormat('de-DE', {
    weekday: 'long', day: 'numeric', month: 'long', timeZone: BERLIN_TIMEZONE
  }).format(new Date(value));
}

function formatKickoffTime(value) {
  return new Intl.DateTimeFormat('de-DE', {
    hour: '2-digit', minute: '2-digit', hour12: false, timeZone: BERLIN_TIMEZONE
  }).format(new Date(value));
}

function localDateKey(value) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    year: 'numeric', month: '2-digit', day: '2-digit', timeZone: BERLIN_TIMEZONE
  }).formatToParts(new Date(value));
  const part = type => parts.find(item => item.type === type)?.value;
  return `${part('year')}-${part('month')}-${part('day')}`;
}

function dateRange(matches) {
  if (!matches.length) return 'Termin noch offen';
  const dates = [...matches].sort((a, b) => new Date(a.kickoff) - new Date(b.kickoff));
  const partMap = value => Object.fromEntries(new Intl.DateTimeFormat('de-DE', {
    day: 'numeric', month: 'long', year: 'numeric', timeZone: BERLIN_TIMEZONE
  }).formatToParts(new Date(value)).map(item => [item.type, item.value]));
  const first = partMap(dates[0].kickoff);
  const last = partMap(dates.at(-1).kickoff);
  if (first.day === last.day && first.month === last.month) return `${first.day}. ${first.month}`;
  if (first.month === last.month) return `${first.day}.–${last.day}. ${first.month}`;
  return `${first.day}. ${first.month}–${last.day}. ${last.month}`;
}

function scoreMarkup(match) {
  if (match.score?.home == null || match.score?.away == null) {
    return `<time class="fixture-kickoff" datetime="${esc(match.kickoff)}">${esc(formatKickoffTime(match.kickoff))}</time>`;
  }
  return `<strong class="fixture-score">${match.score.home}<span>:</span>${match.score.away}</strong>`;
}

function statusMarkup(match) {
  if (match.status === 'LIVE_OR_ONGOING') return '<span class="fixture-state fixture-state--live">Live</span>';
  if (match.status === 'FINISHED') return '<span class="fixture-state fixture-state--finished">Ende</span>';
  if (match.status === 'UNKNOWN') return '<span class="fixture-state">Offen</span>';
  return '';
}

function fixtureAriaLabel(match) {
  const home = match.home.shortName || match.home.name;
  const away = match.away.shortName || match.away.name;
  const result = match.score?.home == null ? `Anstoß ${formatKickoffTime(match.kickoff)}` : `${match.score.home} zu ${match.score.away}`;
  return `${home} gegen ${away}, ${result}`;
}

function renderFixture(match) {
  return `<article class="fixture-row" aria-label="${esc(fixtureAriaLabel(match))}">
    <div class="fixture-team fixture-team--home">${teamLogo(match.home)}<span>${esc(match.home.shortName || match.home.name)}</span></div>
    <div class="fixture-result">${scoreMarkup(match)}${statusMarkup(match)}</div>
    <div class="fixture-team fixture-team--away">${teamLogo(match.away)}<span>${esc(match.away.shortName || match.away.name)}</span></div>
  </article>`;
}

function groupMatches(matches) {
  const groups = [];
  [...matches].sort((a, b) => new Date(a.kickoff) - new Date(b.kickoff)).forEach(match => {
    const key = `${localDateKey(match.kickoff)}-${formatKickoffTime(match.kickoff)}`;
    let group = groups.at(-1);
    if (!group || group.key !== key) {
      group = { key, kickoff: match.kickoff, matches: [] };
      groups.push(group);
    }
    group.matches.push(match);
  });
  return groups;
}

function renderFixtureBoard(matches) {
  if (!matches.length) return '<div class="empty fixture-board"><strong>Keine Spiele geladen.</strong><span>Für diesen Spieltag sind noch keine Begegnungen verfügbar.</span></div>';
  return `<div class="fixture-board">${groupMatches(matches).map(group => `
    <section class="kickoff-group" aria-label="${esc(formatLocalDate(group.kickoff))}, ${esc(formatKickoffTime(group.kickoff))}">
      <h2 class="kickoff-heading"><span>${esc(formatLocalDate(group.kickoff))}</span><time datetime="${esc(group.kickoff)}">${esc(formatKickoffTime(group.kickoff))}</time></h2>
      <div class="kickoff-fixtures">${group.matches.map(renderFixture).join('')}</div>
    </section>`).join('')}</div>`;
}

function hasSeasonStarted() {
  return data.standings.some(row => row.played > 0) || data.matchdays.some(day => day.matches.some(match => match.status === 'FINISHED'));
}

function firstKickoff() {
  return data.matchdays.flatMap(day => day.matches).map(match => match.kickoff).sort()[0] || null;
}

function renderSeasonContext() {
  if (hasSeasonStarted()) return `<section class="desktop-context glass"><div class="league-kicker">Tabellenstand</div><h2>Spitzengruppe</h2>${tableMarkup(data.standings.slice(0, 6), true)}</section>`;
  const opening = data.matchdays.flatMap(day => day.matches).sort((a, b) => new Date(a.kickoff) - new Date(b.kickoff))[0];
  const start = firstKickoff();
  return `<section class="desktop-context glass"><div class="league-kicker">Saisonstart</div><h2>${start ? esc(formatLocalDate(start)) : 'Termin offen'}</h2>
    <p>${opening ? `${esc(opening.home.shortName || opening.home.name)} eröffnet gegen ${esc(opening.away.shortName || opening.away.name)} die Saison.` : 'Der Auftaktspielplan wird geladen.'}</p>
    <div class="season-facts"><span><strong>${Object.keys(data.teams).length}</strong> Clubs</span><span><strong>${data.matchdays.length}</strong> Spieltage</span></div>
  </section>`;
}

function renderMatches() {
  const matchday = data.matchdays.find(item => item.number === selectedMatchday);
  const matches = matchday?.matches || [];
  const minDay = data.matchdays[0]?.number || 1;
  const maxDay = data.matchdays.at(-1)?.number || minDay;
  app.innerHTML = `<section class="league-panel">
    <div class="matchday-hero glass">
      <button id="prev-day" class="matchday-arrow" aria-label="Vorheriger Spieltag" ${selectedMatchday <= minDay ? 'disabled' : ''}><span aria-hidden="true">‹</span></button>
      <div class="matchday-title"><span>${selectedMatchday}. Spieltag</span><strong>${esc(dateRange(matches))}</strong></div>
      <button id="next-day" class="matchday-arrow" aria-label="Nächster Spieltag" ${selectedMatchday >= maxDay ? 'disabled' : ''}><span aria-hidden="true">›</span></button>
    </div>
    <button class="current-day-button" id="current-day" ${selectedMatchday === data.current_matchday ? 'hidden' : ''}>Zum relevanten Spieltag ${data.current_matchday}</button>
    <div class="matches-layout"><div>${renderFixtureBoard(matches)}</div>${renderSeasonContext()}</div>
  </section>`;
  document.getElementById('prev-day').addEventListener('click', () => changeMatchday(-1));
  document.getElementById('next-day').addEventListener('click', () => changeMatchday(1));
  document.getElementById('current-day').addEventListener('click', () => {
    selectedMatchday = data.current_matchday;
    markMeaningfulInteraction();
    renderMatches();
  });
}

function changeMatchday(delta) {
  const minDay = data.matchdays[0]?.number || 1;
  const maxDay = data.matchdays.at(-1)?.number || minDay;
  selectedMatchday = Math.max(minDay, Math.min(maxDay, selectedMatchday + delta));
  markMeaningfulInteraction();
  renderMatches();
  window.scrollTo({ top: 0, behavior: reducedMotion() ? 'auto' : 'smooth' });
}

function teamLookup(id) {
  return data.teams[id] || { name: id, shortName: id, logo: null };
}

function tableRowMarkup(row, compact = false) {
  const club = teamLookup(row.team_id);
  const diff = row.goal_difference > 0 ? `+${row.goal_difference}` : row.goal_difference;
  return `<tr><td class="col-position">${row.position}</td><td><div class="table-club">${teamLogo(club, 'club-mark--small')}<span>${esc(club.shortName || club.name)}</span></div></td><td>${row.played}</td>${compact ? '' : `<td class="wide-col">${row.won}</td><td class="wide-col">${row.drawn}</td><td class="wide-col">${row.lost}</td><td class="wide-col goals-col">${row.goals_for}:${row.goals_against}</td>`}<td>${diff}</td><td><strong>${row.points}</strong></td></tr>`;
}

function tableMarkup(rows, compact = false) {
  return `<div class="league-table-scroll"><table class="league-table ${compact ? 'league-table--compact' : ''}">
    <thead><tr><th scope="col">#</th><th scope="col">Club</th><th scope="col">Sp</th>${compact ? '' : '<th class="wide-col" scope="col">S</th><th class="wide-col" scope="col">U</th><th class="wide-col" scope="col">N</th><th class="wide-col goals-col" scope="col">Tore</th>'}<th scope="col">Diff</th><th scope="col">Pkt</th></tr></thead>
    <tbody>${rows.map(row => tableRowMarkup(row, compact)).join('')}</tbody>
  </table></div>`;
}

function renderTable() {
  const start = firstKickoff();
  const preseasonNote = !hasSeasonStarted() && start
    ? `<p class="preseason-note">Die Saison beginnt am ${esc(new Intl.DateTimeFormat('de-DE', { day:'numeric', month:'long', timeZone:BERLIN_TIMEZONE }).format(new Date(start)))}. Bis dahin startet die Tabelle bewusst bei null.</p>`
    : '';
  app.innerHTML = `<section class="league-table-wrap">
    <div class="league-table-head"><div><span class="league-kicker">Bundesliga</span><h2>Tabelle</h2></div><span>${esc(data.competition.season)}</span></div>
    ${preseasonNote}<div class="table-surface">${tableMarkup(data.standings)}</div>
  </section>`;
}

function render() {
  if (!data) return;
  currentView === 'matches' ? renderMatches() : renderTable();
  updateFreshness();
}

function setView(view) {
  if (!['matches', 'table'].includes(view)) return;
  currentView = view;
  document.querySelectorAll('[data-view]').forEach(button => {
    const active = button.dataset.view === view;
    button.classList.toggle('active', active);
    button.setAttribute('aria-selected', String(active));
    button.tabIndex = active ? 0 : -1;
  });
  markMeaningfulInteraction();
  render();
  app.focus({ preventScroll: true });
}

function formatUpdatedAt(value) {
  const updated = new Date(value);
  const ageMinutes = Math.max(0, Math.floor((Date.now() - updated.getTime()) / 60000));
  if (ageMinutes < 2) return 'gerade eben';
  if (ageMinutes < 60) return `vor ${ageMinutes} Min.`;
  if (ageMinutes < 12 * 60) return `vor ${Math.floor(ageMinutes / 60)} Std.`;
  return new Intl.DateTimeFormat('de-DE', { day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit', timeZone:BERLIN_TIMEZONE }).format(updated);
}

function updateFreshness() {
  if (!data) return;
  const prefix = !navigator.onLine || loadedFromCache ? 'Offline · Stand' : refreshProblem ? 'Stand · Aktualisierung offen' : 'Aktualisiert';
  meta.textContent = `${prefix} ${formatUpdatedAt(data.updated_at)}`;
  meta.classList.toggle('sync--offline', !navigator.onLine || loadedFromCache || refreshProblem);
}

async function loadData({ preserve = false } = {}) {
  try {
    const response = await fetch(`${DATA_URL}?_=${Date.now()}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    if (payload.competition?.id !== 'bundesliga' || !Array.isArray(payload.matchdays)) throw new Error('Bundesliga-Datenformat nicht verfügbar');
    data = payload;
    loadedFromCache = response.headers.get('X-Bundesliga-Data') === 'cache';
    refreshProblem = false;
    if (!preserve) selectedMatchday = payload.current_matchday || payload.matchdays[0]?.number || 1;
    render();
  } catch (error) {
    refreshProblem = true;
    if (data) {
      updateFreshness();
      return;
    }
    app.innerHTML = `<div class="league-error glass"><strong>Keine Bundesliga-Daten verfügbar.</strong><span>${esc(error.message)}</span><button id="retry-load">Erneut versuchen</button></div>`;
    meta.textContent = navigator.onLine ? 'Aktualisierung fehlgeschlagen' : 'Offline · keine Daten';
    document.getElementById('retry-load').addEventListener('click', () => loadData());
  }
}

function reducedMotion() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

const THEME_ICONS = {
  auto: '<circle cx="12" cy="12" r="5"/><path d="M12 1v3M12 20v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M1 12h3M20 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"/>',
  dark: '<path d="M20.5 15.2A8.5 8.5 0 0 1 8.8 3.5 8.5 8.5 0 1 0 20.5 15.2Z"/>',
  light: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>'
};
const THEME_LABELS = { auto: 'automatisch', dark: 'dunkel', light: 'hell' };
let themeMode = localStorage.getItem('theme') || 'auto';

function applyTheme(mode) {
  document.documentElement.classList.toggle('force-dark', mode === 'dark');
  document.documentElement.classList.toggle('force-light', mode === 'light');
  const button = document.getElementById('theme-toggle');
  button.querySelector('svg').innerHTML = THEME_ICONS[mode];
  button.title = `Design: ${THEME_LABELS[mode]}`;
  button.setAttribute('aria-label', `Design wechseln, aktuell ${THEME_LABELS[mode]}`);
}

function isInstalled() {
  return window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
}

function installDismissed() {
  const dismissedAt = Number(localStorage.getItem(INSTALL_DISMISS_KEY));
  return dismissedAt && Date.now() - dismissedAt < INSTALL_DISMISS_MS;
}

function detectInstallMode() {
  if (isInstalled() || installDismissed()) return null;
  if (deferredInstallPrompt) return 'chromium';
  if (typeof navigator.standalone !== 'boolean') return null;
  return /Safari/.test(navigator.userAgent) && !/CriOS|FxiOS|EdgiOS|OPiOS/.test(navigator.userAgent) ? 'ios-safari' : null;
}

function maybeShowInstallBanner() {
  installMode = detectInstallMode();
  if (!hasMeaningfulInteraction || !installMode) return;
  document.getElementById('install-banner-text').textContent = 'Bundesliga-App installieren';
  installBanner.hidden = false;
}

function markMeaningfulInteraction() {
  hasMeaningfulInteraction = true;
  maybeShowInstallBanner();
}

function dismissInstallBanner() {
  installBanner.hidden = true;
  localStorage.setItem(INSTALL_DISMISS_KEY, String(Date.now()));
}

function openIOSSheet() {
  const sheet = document.getElementById('ios-install-sheet');
  sheet.hidden = false;
  requestAnimationFrame(() => sheet.classList.add('open'));
  document.getElementById('ios-install-close').focus();
}

function closeIOSSheet() {
  const sheet = document.getElementById('ios-install-sheet');
  sheet.classList.remove('open');
  if (reducedMotion()) sheet.hidden = true;
  else sheet.addEventListener('transitionend', () => { sheet.hidden = true; }, { once: true });
  document.getElementById('install-action').focus();
}

window.addEventListener('beforeinstallprompt', event => {
  event.preventDefault();
  deferredInstallPrompt = event;
  maybeShowInstallBanner();
});
window.addEventListener('appinstalled', () => { installBanner.hidden = true; deferredInstallPrompt = null; });
window.addEventListener('online', () => { loadedFromCache = false; loadData({ preserve: true }); });
window.addEventListener('offline', updateFreshness);

document.getElementById('install-action').addEventListener('click', async () => {
  if (installMode === 'chromium' && deferredInstallPrompt) {
    await deferredInstallPrompt.prompt();
    deferredInstallPrompt = null;
    installBanner.hidden = true;
  } else if (installMode === 'ios-safari') openIOSSheet();
});
document.getElementById('install-dismiss').addEventListener('click', dismissInstallBanner);
document.getElementById('ios-install-close').addEventListener('click', closeIOSSheet);
document.querySelector('[data-close-install]').addEventListener('click', closeIOSSheet);
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && !document.getElementById('ios-install-sheet').hidden) closeIOSSheet();
});

document.getElementById('theme-toggle').addEventListener('click', () => {
  themeMode = themeMode === 'auto' ? 'dark' : themeMode === 'dark' ? 'light' : 'auto';
  localStorage.setItem('theme', themeMode);
  applyTheme(themeMode);
});
applyTheme(themeMode);

document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => setView(button.dataset.view)));
document.querySelector('[role="tablist"]').addEventListener('keydown', event => {
  if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
  event.preventDefault();
  const view = event.key === 'ArrowLeft' ? 'matches' : 'table';
  document.querySelector(`[data-view="${view}"]`).focus();
  setView(view);
});

const params = new URLSearchParams(location.search);
if (params.has('dark')) { themeMode = 'dark'; applyTheme(themeMode); }
if (params.get('view') === 'table') setView('table');

if ('serviceWorker' in navigator) navigator.serviceWorker.register('./sw.js').catch(() => {});
setInterval(updateFreshness, 60000);
loadData();
