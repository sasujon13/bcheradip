/* Equal, content-sized columns for catalogs only, never database record grids. */
(() => {
  'use strict';
  function start() {
    const catalogs = [...document.querySelectorAll('.admin-tables-grid, #content-main .table-list')];
    document.querySelectorAll('#content-main .module[class*="app-"] table > tbody, #nav-sidebar .module table > tbody').forEach(body => {
      if ([...body.children].some(row => row.querySelector('th'))) catalogs.push(body);
    });
    if (!catalogs.length) return;
    let frame = 0;
    const widths = new WeakMap();
    const dirty = new Set(catalogs);
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(layout);
    };
    function layout() {
      frame = 0;
      catalogs.forEach(catalog => {
        if (!catalog.getClientRects().length || !catalog.clientWidth) return;
        if (dirty.has(catalog)) {
          const probe = catalog.cloneNode(true);
          probe.removeAttribute('id');
          probe.querySelectorAll('[id]').forEach(node => node.removeAttribute('id'));
          probe.classList.add('table-catalog-measure');
          probe.setAttribute('aria-hidden', 'true');
          probe.setAttribute('inert', '');
          catalog.parentNode.appendChild(probe);
          const longest = Math.max(0, ...[...probe.children].map(node => node.getBoundingClientRect().width));
          probe.remove();
          // Rounding headroom avoids clipped final glyphs at fractional zoom.
          if (longest) catalog.style.setProperty('--table-catalog-column-width', `${Math.ceil(longest) + 2}px`);
          dirty.delete(catalog);
        }
        const top = Math.max(0, catalog.getBoundingClientRect().top);
        const height = Math.max(160, window.innerHeight - top - 24);
        catalog.style.setProperty('--table-catalog-height', `${Math.floor(height)}px`);
      });
    }
    catalogs.forEach(catalog => {
      catalog.classList.add('table-catalog');
      // Keyboard users can scroll without tabbing through every table link.
      catalog.tabIndex = 0;
      catalog.setAttribute('aria-label', 'Database tables');
      catalog.querySelectorAll('a').forEach(link => {
        if (!link.title) link.title = link.textContent.trim();
      });
      new MutationObserver(records => {
        if (!records.some(record => record.target !== catalog || record.type !== 'attributes')) return;
        dirty.add(catalog);
        schedule();
      }).observe(catalog, { childList: true, characterData: true, subtree: true, attributes: true, attributeFilter: ['style', 'class', 'hidden'] });
    });
    if (window.ResizeObserver) {
      const observer = new ResizeObserver(entries => {
        let changed = false;
        entries.forEach(entry => {
          const width = entry.contentRect.width;
          if (widths.get(entry.target) !== width) {
            widths.set(entry.target, width);
            changed = true;
          }
        });
        if (changed) schedule();
      });
      catalogs.forEach(catalog => observer.observe(catalog));
    }
    window.addEventListener('resize', () => {
      catalogs.forEach(catalog => dirty.add(catalog));
      schedule();
    }, { passive: true });
    if (document.fonts) document.fonts.ready.then(() => {
      catalogs.forEach(catalog => dirty.add(catalog));
      schedule();
    });
    schedule();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
  else start();
})();
