(() => {
  'use strict';
  function start() {
    const overlay = document.getElementById('admin-table-loading');
    if (!overlay) return;
    const content = document.getElementById('content-main');
    const hide = () => { overlay.hidden = true; content?.removeAttribute('aria-busy'); };
    window.addEventListener('pageshow', hide);
    window.addEventListener('pagehide', hide);
    document.addEventListener('click', event => {
      const link = event.target.closest('a[href]');
      if (!link || event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey
          || link.hasAttribute('download') || (link.target && link.target !== '_self')) return;
      const url = new URL(link.href, location.href);
      if (url.origin !== location.origin) return;
      const database = link.closest('.admin-db-tabs, .database-list') || /^\/admin\/databases\/[^/]+\/?$/.test(url.pathname);
      if (!database) return;
      overlay.hidden = false;
      content?.setAttribute('aria-busy', 'true');
      // Retain normal links, browser history, and native error pages. No fake
      // percentage or forced delay; the arriving document removes the loader.
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
  else start();
})();
