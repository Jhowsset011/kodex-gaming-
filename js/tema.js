// Apply the saved choice before the stylesheet paints. Dark remains the default.
(() => {
  let theme = 'dark';
  try { if (localStorage.getItem('kodex-theme') === 'light') theme = 'light'; } catch {}
  const root = document.documentElement;
  root.dataset.theme = theme;

  function updateTheme() {
    const dark = root.dataset.theme === 'dark';
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', dark ? '#111413' : '#f7f8f5');
    document.querySelectorAll('[data-theme-toggle]').forEach(button => {
      button.setAttribute('aria-checked', String(dark));
      button.title = dark ? 'Cambiar a modo claro' : 'Cambiar a modo oscuro';
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    updateTheme();
    document.querySelectorAll('[data-theme-toggle]').forEach(button => button.addEventListener('click', () => {
      root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
      try { localStorage.setItem('kodex-theme', root.dataset.theme); } catch {}
      updateTheme();
    }));
  });
  window.addEventListener('storage', event => {
    if (event.key !== 'kodex-theme' && event.key !== null) return;
    root.dataset.theme = event.newValue === 'light' ? 'light' : 'dark';
    updateTheme();
  });
})();
