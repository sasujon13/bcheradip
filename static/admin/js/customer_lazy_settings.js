(() => {
  'use strict';
  function start() {
    document.querySelectorAll('[data-lazy-settings]').forEach(panel => {
      const button = panel.querySelector('.lazy-settings-toggle');
      const editor = panel.querySelector('.lazy-settings-editor');
      const text = panel.querySelector('textarea');
      const loaded = panel.querySelector('[data-settings-loaded]');
      const revision = panel.querySelector('[data-settings-revision]');
      const status = panel.querySelector('[role="status"]');
      button.addEventListener('click', async () => {
        if (loaded.value === '1') {
          editor.hidden = !editor.hidden;
          button.textContent = editor.hidden ? 'Show Settings' : 'Hide Settings';
          button.setAttribute('aria-expanded', String(!editor.hidden));
          return;
        }
        button.disabled = true;
        status.textContent = 'Loading Settings…';
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 20000);
        try {
          const response = await fetch(text.dataset.settingsUrl, {
            credentials: 'same-origin', cache: 'no-store', signal: controller.signal,
            headers: { Accept: 'application/json' },
          });
          if (!response.ok || response.redirected) throw new Error('Settings could not be loaded. Check your administrator session and try again.');
          const data = await response.json();
          text.value = JSON.stringify(data.settings, null, 2);
          revision.value = data.revision;
          loaded.value = '1';
          text.disabled = false;
          editor.hidden = false;
          button.textContent = 'Hide Settings';
          button.setAttribute('aria-expanded', 'true');
          status.textContent = '';
        } catch (error) {
          status.textContent = error.name === 'AbortError' ? 'Loading timed out. Select Load Settings to retry.' : error.message;
        } finally {
          clearTimeout(timer);
          button.disabled = false;
        }
      });
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
  else start();
})();
