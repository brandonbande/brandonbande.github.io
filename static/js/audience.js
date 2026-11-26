// Audience context.
// State per group: about | bring | contact, each 'business' or 'events'.
// Precedence: default → ?for= on load → sessionStorage → latest explicit click.
// About click sets all three; offering click sets bring + contact; contact click sets contact.
// Scrolling never writes state; URL updates use replaceState (no history entries).
const VALUES = ['business', 'events'];
const GROUPS = ['about', 'bring', 'contact'];
const KEY = 'bb-audience';
const SCOPE = { all: GROUPS, about: GROUPS, bring: ['bring', 'contact'], contact: ['contact'] };
const EVENTS = { about: 'toggle-about', bring: 'toggle-offering' };

const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const read = () => { try { return JSON.parse(sessionStorage.getItem(KEY)) || {}; } catch { return {}; } };
const write = (s) => { try { sessionStorage.setItem(KEY, JSON.stringify(s)); } catch { /* private mode */ } };

const param = new URLSearchParams(location.search).get('for');
const base = VALUES.includes(param) ? param : 'business';
const stored = read();
const state = Object.fromEntries(GROUPS.map((g) => [g, VALUES.includes(stored[g]) ? stored[g] : base]));

function count(path) {
  if (window.goatcounter && window.goatcounter.count) window.goatcounter.count({ path, title: path, event: true });
}

function apply(group) {
  const tabs = document.querySelectorAll(`[data-tab="${group}"]`);
  tabs.forEach((t) => {
    const on = t.dataset.value === state[group];
    t.setAttribute('aria-selected', String(on));
    t.tabIndex = on ? 0 : -1;
  });
  document.querySelectorAll(`[data-panel="${group}"]`).forEach((p) => {
    const on = p.dataset.value === state[group];
    p.classList.toggle('is-inactive', !on);
    p.toggleAttribute('inert', !on);
  });
}

function set(scope, value) {
  if (!VALUES.includes(value)) return;
  (SCOPE[scope] || [scope]).forEach((g) => { state[g] = value; apply(g); });
  write(state);
  const url = new URL(location.href);
  url.searchParams.set('for', value);
  try { history.replaceState(history.state, '', url); } catch { /* file:// */ }
}

function enhance(group) {
  const list = document.querySelector(`[data-tabs="${group}"]`);
  const panels = document.querySelector(`[data-panels="${group}"]`);
  if (!list || !panels) return;
  list.setAttribute('role', 'tablist');
  const tabs = [...list.querySelectorAll('[data-tab]')];
  tabs.forEach((t) => {
    t.setAttribute('role', 'tab');
    const panel = document.getElementById(t.getAttribute('aria-controls'));
    if (panel) {
      panel.setAttribute('role', 'tabpanel');
      panel.setAttribute('aria-labelledby', t.id);
      panel.tabIndex = -1;
    }
    t.addEventListener('click', () => {
      list.classList.add('is-touched'); // the "Click here" nudge has done its job
      set(group, t.dataset.value);
      if (EVENTS[group]) count(`${EVENTS[group]}-${t.dataset.value}`);
    });
    t.addEventListener('keydown', (e) => {
      const i = tabs.indexOf(t);
      const next = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: tabs.length - 1 }[e.key];
      if (next === undefined) return;
      e.preventDefault();
      const target = tabs[(next + tabs.length) % tabs.length];
      target.focus();
      target.click();
    });
  });
  list.hidden = false;
  list.classList.add('is-ready');
  panels.classList.add('is-ready');
  apply(group);
}

GROUPS.forEach(enhance);

// Links that choose a journey (hero/header CTAs, profile links, offering CTAs).
document.addEventListener('click', (e) => {
  const a = e.target.closest('a[data-audience-set]');
  if (!a || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
  const url = new URL(a.href, location.href);
  if (url.pathname !== location.pathname) return; // another page: let the browser navigate
  e.preventDefault();
  set(a.dataset.audienceSet, a.dataset.value);
  const target = document.getElementById(url.hash.slice(1));
  if (target) {
    target.scrollIntoView({ behavior: reduced() ? 'auto' : 'smooth', block: 'start' });
    const heading = target.querySelector('h2');
    if (heading) { heading.tabIndex = -1; heading.focus({ preventScroll: true }); }
  }
});
