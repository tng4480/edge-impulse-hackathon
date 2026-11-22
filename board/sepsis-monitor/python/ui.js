// Shared helpers for the board pages. Served at /ui.js by main.py and loaded in <head>,
// so the saved theme applies before the first paint.
const $ = id => document.getElementById(id);
const esc = t => String(t ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;'}[c]));
const fmt = (v, d = 0) => v == null ? '–' : Number(v).toFixed(d);

function post(path, body) {
  return fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body || {})});
}

// Theme: follows the system unless the viewer picks one. Stored per browser only.
const THEME_KEY = 'sepsis_theme';
try {
  const saved = localStorage.getItem(THEME_KEY);
  if (saved === 'light' || saved === 'dark') document.documentElement.dataset.theme = saved;
} catch (e) { /* storage blocked: follow the system */ }

function currentTheme() {
  return document.documentElement.dataset.theme ||
    (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
}
function toggleTheme() {
  const next = currentTheme() === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem(THEME_KEY, next); } catch (e) { /* ignore */ }
  labelThemeButton();
}
function labelThemeButton() {
  const b = document.getElementById('theme_btn');
  if (b) b.textContent = currentTheme() === 'dark' ? 'Light theme' : 'Dark theme';
}
document.addEventListener('DOMContentLoaded', labelThemeButton);

// SVG polyline from [[x, y], ...]; empty when there are fewer than two points.
const svgLine = (pts, color, width = 2.6) => pts.length > 1
  ? `<polyline fill="none" stroke="${color}" stroke-width="${width}" stroke-linejoin="round" points="${pts.map(p => p[0] + ',' + p[1]).join(' ')}"/>`
  : '';

// Icons: Tabler Icons 3.49.0 outline (MIT, https://tabler.io/icons), copied from the UI Atlas icon set.
const ICONS = {
  'activity': '<path d="M3 12h4l3 8l4 -16l3 8h4" />',
  'alert-triangle': '<path d="M12 9v4" /> <path d="M10.363 3.591l-8.106 13.534a1.914 1.914 0 0 0 1.636 2.871h16.214a1.914 1.914 0 0 0 1.636 -2.87l-8.106 -13.536a1.914 1.914 0 0 0 -3.274 0" /> <path d="M12 16h.01" />',
  'circle-check': '<path d="M3 12a9 9 0 1 0 18 0a9 9 0 1 0 -18 0" /> <path d="M9 12l2 2l4 -4" />',
  'clipboard-list': '<path d="M9 5h-2a2 2 0 0 0 -2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2 -2v-12a2 2 0 0 0 -2 -2h-2" /> <path d="M9 5a2 2 0 0 1 2 -2h2a2 2 0 0 1 2 2a2 2 0 0 1 -2 2h-2a2 2 0 0 1 -2 -2" /> <path d="M9 12l.01 0" /> <path d="M13 12l2 0" /> <path d="M9 16l.01 0" /> <path d="M13 16l2 0" />',
  'cpu': '<path d="M5 6a1 1 0 0 1 1 -1h12a1 1 0 0 1 1 1v12a1 1 0 0 1 -1 1h-12a1 1 0 0 1 -1 -1l0 -12" /> <path d="M9 9h6v6h-6l0 -6" /> <path d="M3 10h2" /> <path d="M3 14h2" /> <path d="M10 3v2" /> <path d="M14 3v2" /> <path d="M21 10h-2" /> <path d="M21 14h-2" /> <path d="M14 21v-2" /> <path d="M10 21v-2" />',
  'device-watch': '<path d="M6 9a3 3 0 0 1 3 -3h6a3 3 0 0 1 3 3v6a3 3 0 0 1 -3 3h-6a3 3 0 0 1 -3 -3v-6" /> <path d="M9 18v3h6v-3" /> <path d="M9 6v-3h6v3" />',
  'droplet': '<path d="M7.502 19.423c2.602 2.105 6.395 2.105 8.996 0c2.602 -2.105 3.262 -5.708 1.566 -8.546l-4.89 -7.26c-.42 -.625 -1.287 -.803 -1.936 -.397a1.376 1.376 0 0 0 -.41 .397l-4.893 7.26c-1.695 2.838 -1.035 6.441 1.567 8.546" />',
  'file-code': '<path d="M14 3v4a1 1 0 0 0 1 1h4" /> <path d="M17 21h-10a2 2 0 0 1 -2 -2v-14a2 2 0 0 1 2 -2h7l5 5v11a2 2 0 0 1 -2 2" /> <path d="M10 13l-1 2l1 2" /> <path d="M14 13l1 2l-1 2" />',
  'first-aid-kit': '<path d="M8 8v-2a2 2 0 0 1 2 -2h4a2 2 0 0 1 2 2v2" /> <path d="M4 10a2 2 0 0 1 2 -2h12a2 2 0 0 1 2 2v8a2 2 0 0 1 -2 2h-12a2 2 0 0 1 -2 -2l0 -8" /> <path d="M10 14h4" /> <path d="M12 12v4" />',
  'heartbeat': '<path d="M19.5 13.572l-7.5 7.428l-2.896 -2.868m-6.117 -8.104a5 5 0 0 1 9.013 -3.022a5 5 0 1 1 7.5 6.572" /> <path d="M3 13h2l2 3l2 -6l1 3h3" />',
  'lungs': '<path d="M6.081 20c1.612 0 2.919 -1.335 2.919 -2.98v-9.763c0 -.694 -.552 -1.257 -1.232 -1.257c-.205 0 -.405 .052 -.584 .15l-.13 .083c-1.46 1.059 -2.432 2.647 -3.404 5.824c-.42 1.37 -.636 2.962 -.648 4.775c-.012 1.675 1.261 3.054 2.877 3.161l.203 .007" /> <path d="M17.92 20c-1.613 0 -2.92 -1.335 -2.92 -2.98v-9.763c0 -.694 .552 -1.257 1.233 -1.257c.204 0 .405 .052 .584 .15l.13 .083c1.46 1.059 2.432 2.647 3.405 5.824c.42 1.37 .636 2.962 .648 4.775c.012 1.675 -1.261 3.054 -2.878 3.161l-.202 .007" /> <path d="M9 12a3 3 0 0 0 3 -3a3 3 0 0 0 3 3" /> <path d="M12 4v5" />',
  'qrcode': '<path d="M4 5a1 1 0 0 1 1 -1h4a1 1 0 0 1 1 1v4a1 1 0 0 1 -1 1h-4a1 1 0 0 1 -1 -1l0 -4" /> <path d="M7 17l0 .01" /> <path d="M14 5a1 1 0 0 1 1 -1h4a1 1 0 0 1 1 1v4a1 1 0 0 1 -1 1h-4a1 1 0 0 1 -1 -1l0 -4" /> <path d="M7 7l0 .01" /> <path d="M4 15a1 1 0 0 1 1 -1h4a1 1 0 0 1 1 1v4a1 1 0 0 1 -1 1h-4a1 1 0 0 1 -1 -1l0 -4" /> <path d="M17 7l0 .01" /> <path d="M14 14l3 0" /> <path d="M20 14l0 .01" /> <path d="M14 14l0 3" /> <path d="M14 20l3 0" /> <path d="M17 17l3 0" /> <path d="M20 17l0 3" />',
  'temperature': '<path d="M10 13.5a4 4 0 1 0 4 0v-8.5a2 2 0 0 0 -4 0v8.5" /> <path d="M10 9l4 0" />',
  'user-check': '<path d="M8 7a4 4 0 1 0 8 0a4 4 0 0 0 -8 0" /> <path d="M6 21v-2a4 4 0 0 1 4 -4h4" /> <path d="M15 19l2 2l4 -4" />',
  'wifi': '<path d="M12 18l.01 0" /> <path d="M9.172 15.172a4 4 0 0 1 5.656 0" /> <path d="M6.343 12.343a8 8 0 0 1 11.314 0" /> <path d="M3.515 9.515c4.686 -4.687 12.284 -4.687 17 0" />',
  'wifi-off': '<path d="M12 18l.01 0" /> <path d="M9.172 15.172a4 4 0 0 1 5.656 0" /> <path d="M6.343 12.343a7.963 7.963 0 0 1 3.864 -2.14m4.163 .155a7.965 7.965 0 0 1 3.287 2" /> <path d="M3.515 9.515a12 12 0 0 1 3.544 -2.455m3.101 -.92a12 12 0 0 1 10.325 3.374" /> <path d="M3 3l18 18" />'
};
const icon = name => ICONS[name]
  ? `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name]}</svg>`
  : '';
// Static markup asks for an icon with <i data-icon="name"></i>.
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('i[data-icon]').forEach(el => { el.outerHTML = icon(el.dataset.icon); });
});

// Hold to confirm (UI Atlas "Hold to confirm"): the action runs only after a full press, so a stray tap
// does nothing. Space or Enter held on the keyboard works the same way. Markup: <button class="btn hold"><i></i><span>…</span></button>
function holdToConfirm(button, ms, onDone) {
  const fill = button.querySelector('i');
  let timer = null;
  const start = e => {
    if (timer || button.disabled) return;
    if (e.type === 'keydown' && e.key !== ' ' && e.key !== 'Enter') return;
    e.preventDefault();
    fill.style.transition = `width ${ms}ms linear`;
    fill.style.width = '100%';
    timer = setTimeout(() => { timer = null; reset(); onDone(); }, ms);
  };
  const reset = () => {
    if (timer) { clearTimeout(timer); timer = null; }
    fill.style.transition = 'width .2s';
    fill.style.width = '0';
  };
  button.addEventListener('pointerdown', start);
  button.addEventListener('keydown', start);
  for (const ev of ['pointerup', 'pointerleave', 'pointercancel', 'keyup', 'blur']) button.addEventListener(ev, reset);
  button.addEventListener('click', e => e.preventDefault());
}
