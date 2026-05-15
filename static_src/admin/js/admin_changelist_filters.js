/**
 * Changelist #changelist-filter: compact dropdowns with checkboxes (multi) or radios (date ranges).
 * Multi-select uses field__in=a,b (supported by Django admin remaining lookup params).
 * Opening a dropdown closes others.
 */
(function () {
  'use strict';

  function ready(fn) {
    if (document.readyState !== 'loading') fn();
    else document.addEventListener('DOMContentLoaded', fn);
  }

  function parseHrefParams(href) {
    try {
      var u = new URL(href, window.location.href);
      return new URLSearchParams(u.search);
    } catch (e) {
      return new URLSearchParams();
    }
  }

  function slugifyTitle(title) {
    return String(title || '')
      .trim()
      .toLowerCase()
      .replace(/\s+/g, '_')
      .replace(/[^a-z0-9_]/g, '');
  }

  function deleteKeysForFieldPath(params, fieldPath) {
    var fp = String(fieldPath || '');
    if (!fp) return;
    [...params.keys()].forEach(function (k) {
      if (k === fp || k.indexOf(fp + '__') === 0) params.delete(k);
    });
  }

  function fieldPathFromParamKey(pk) {
    var m = String(pk || '').match(/^(.+?)__(?:exact|iexact|in|icontains|gt|gte|lt|lte|isnull)$/);
    return m ? m[1] : '';
  }

  function paramsMatchSubset(current, subset) {
    var ok = true;
    subset.forEach(function (val, key) {
      if (String(current.get(key) || '') !== String(val)) ok = false;
    });
    return ok && [...subset.keys()].length > 0;
  }

  function isDateFilter(anchors) {
    for (var i = 0; i < anchors.length; i++) {
      var h = anchors[i].href;
      if (h.indexOf('__gte') !== -1 || h.indexOf('__lt') !== -1 || h.indexOf('__lte') !== -1) return true;
    }
    return false;
  }

  function isAllLabel(text) {
    var t = (text || '').trim().toLowerCase();
    return t === 'all' || t.indexOf('any date') === 0;
  }

  function inferFieldPathFromAnchors(anchors, titleSlug) {
    for (var i = 0; i < anchors.length; i++) {
      if (isAllLabel(anchors[i].textContent)) continue;
      var w = parseHrefParams(anchors[i].href);
      var ks = [...w.keys()];
      if (ks.length === 1) {
        var fp = fieldPathFromParamKey(ks[0]);
        if (fp) return fp;
      }
    }
    return titleSlug;
  }

  function dateFieldPathFromAnchors(anchors) {
    for (var i = 0; i < anchors.length; i++) {
      var m = String(anchors[i].href || '').match(/([a-z_][a-z0-9_]*)__(?:gte|lt|lte|gt)/i);
      if (m) return m[1];
    }
    return '';
  }

  function closeAllPanels(nav, exceptPanel) {
    nav.querySelectorAll('.admin-filter-dd-panel.is-open').forEach(function (p) {
      if (p !== exceptPanel) {
        p.classList.remove('is-open');
        var b = p.closest('.admin-filter-dd');
        if (b) {
          var btn = b.querySelector('.admin-filter-dd-btn');
          if (btn) btn.setAttribute('aria-expanded', 'false');
        }
      }
    });
  }

  function buildButtonSummary(title, fieldPath, anchors, dateMode) {
    var cur = new URLSearchParams(window.location.search);
    var fp = String(fieldPath || '');
    if (dateMode) {
      for (var i = 0; i < anchors.length; i++) {
        var want = parseHrefParams(anchors[i].href);
        if ([...want.keys()].length && paramsMatchSubset(cur, want)) return title + ': ' + anchors[i].textContent.trim();
      }
      var hasDate = false;
      if (fp) {
        cur.forEach(function (_, k) {
          if (k.indexOf(fp + '__') === 0) hasDate = true;
        });
      }
      for (var d = 0; d < anchors.length; d++) {
        if (isAllLabel(anchors[d].textContent) && !hasDate) return title + ': ' + anchors[d].textContent.trim();
      }
      return title + ': ' + (anchors[0] ? anchors[0].textContent.trim() : '');
    }
    var parts = [];
    for (var j = 0; j < anchors.length; j++) {
      var a = anchors[j];
      if (isAllLabel(a.textContent)) continue;
      var w = parseHrefParams(a.href);
      if ([...w.keys()].length && paramsMatchSubset(cur, w)) parts.push(a.textContent.trim());
    }
    var inKey = fp ? fp + '__in' : '';
    if (inKey && cur.get(inKey)) {
      var n = String(cur.get(inKey)).split(',').filter(Boolean).length;
      if (n > 1) return title + ': ' + n + ' selected';
      if (n === 1) return title + ': 1 selected';
    }
    if (parts.length === 1) return title + ': ' + parts[0];
    if (parts.length > 1) return title + ': ' + parts.length + ' selected';
    return title + ': All';
  }

  var ddCounter = 0;

  function enhanceNav(nav) {
    if (!nav || nav.querySelector('.admin-filter-dd')) return;
    var detailsList = nav.querySelectorAll('details[data-filter-title]');
    if (!detailsList.length) return;

    detailsList.forEach(function (details) {
      var title = (details.getAttribute('data-filter-title') || 'Filter').trim();
      var slug = slugifyTitle(title);
      var anchors = Array.prototype.slice.call(details.querySelectorAll('ul a[href]'));
      if (!anchors.length) return;

      var dateMode = isDateFilter(anchors);
      var fieldPath = inferFieldPathFromAnchors(anchors, slug);
      var dateFp = dateFieldPathFromAnchors(anchors);
      if (dateMode && dateFp) fieldPath = dateFp;
      if (!details.parentNode) return;
      var wrap = document.createElement('div');
      wrap.className = 'admin-filter-dd';
      details.parentNode.insertBefore(wrap, details);

      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'admin-filter-dd-btn';
      btn.setAttribute('aria-expanded', 'false');
      btn.setAttribute('aria-haspopup', 'true');
      var btnLabel = document.createElement('span');
      btnLabel.className = 'admin-filter-dd-label';
      var caret = document.createElement('span');
      caret.className = 'admin-filter-dd-caret';
      caret.textContent = '\u25BC';
      btn.appendChild(btnLabel);
      btn.appendChild(caret);

      var panel = document.createElement('div');
      panel.className = 'admin-filter-dd-panel';

      var radioName = 'admin-filter-dd-r' + ddCounter++;

      if (dateMode) {
        anchors.forEach(function (a, idx) {
          var id = radioName + '-opt-' + idx;
          var lab = document.createElement('label');
          var inp = document.createElement('input');
          inp.type = 'radio';
          inp.name = radioName;
          inp.id = id;
          inp.dataset.applyHref = a.href;
          var want = parseHrefParams(a.href);
          if ([...want.keys()].length === 0) {
            var cur0 = new URLSearchParams(window.location.search);
            var any = false;
            cur0.forEach(function (_, k) {
              if (fieldPath && k.indexOf(fieldPath + '__') === 0) any = true;
            });
            inp.checked = !any;
          } else if (paramsMatchSubset(new URLSearchParams(window.location.search), want)) inp.checked = true;
          lab.appendChild(inp);
          var span = document.createElement('span');
          span.textContent = a.textContent.trim();
          lab.appendChild(span);
          lab.setAttribute('for', id);
          panel.appendChild(lab);
        });
      } else {
        anchors.forEach(function (a) {
          if (isAllLabel(a.textContent)) return;
          var id = radioName + '-cb-' + Math.random().toString(36).slice(2);
          var lab = document.createElement('label');
          var inp = document.createElement('input');
          inp.type = 'checkbox';
          inp.id = id;
          var w = parseHrefParams(a.href);
          var entries = [];
          w.forEach(function (v, k) {
            entries.push({ k: k, v: v });
          });
          if (
            entries.length === 1 &&
            (entries[0].k === fieldPath || (fieldPath && entries[0].k.indexOf(fieldPath + '__') === 0))
          ) {
            inp.dataset.pkey = entries[0].k;
            inp.value = entries[0].v;
          } else {
            inp.dataset.applyHref = a.href;
          }
          var cur = new URLSearchParams(window.location.search);
          if (inp.dataset.pkey) {
            var pk = inp.dataset.pkey;
            if (pk.endsWith('__in')) {
              var arr = String(cur.get(pk) || '').split(',');
              inp.checked = arr.indexOf(inp.value) !== -1;
            } else inp.checked = cur.get(pk) === inp.value;
          } else if (inp.dataset.applyHref) {
            inp.checked = paramsMatchSubset(cur, parseHrefParams(inp.dataset.applyHref));
          }
          lab.appendChild(inp);
          var span = document.createElement('span');
          span.textContent = a.textContent.trim() || '(empty)';
          lab.appendChild(span);
          lab.setAttribute('for', id);
          panel.appendChild(lab);
        });
      }

      var actions = document.createElement('div');
      actions.className = 'admin-filter-dd-actions';
      var clearBtn = document.createElement('button');
      clearBtn.type = 'button';
      clearBtn.className = 'admin-filter-dd-clear';
      clearBtn.textContent = 'Clear';
      var applyBtn = document.createElement('button');
      applyBtn.type = 'button';
      applyBtn.textContent = 'Apply';
      actions.appendChild(clearBtn);
      actions.appendChild(applyBtn);
      panel.appendChild(actions);
      wrap.appendChild(btn);
      wrap.appendChild(panel);

      function refreshLabel() {
        btnLabel.textContent = buildButtonSummary(title, fieldPath, anchors, dateMode);
      }
      refreshLabel();

      btn.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        var open = !panel.classList.contains('is-open');
        closeAllPanels(nav, open ? panel : null);
        panel.classList.toggle('is-open', open);
        btn.setAttribute('aria-expanded', open ? 'true' : 'false');
      });

      clearBtn.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        var allA = anchors[0];
        if (allA && isAllLabel(allA.textContent)) {
          window.location.href = allA.href;
          return;
        }
        var p = new URLSearchParams(window.location.search);
        deleteKeysForFieldPath(p, fieldPath);
        window.location.search = p.toString();
      });

      applyBtn.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        if (dateMode) {
          var r = panel.querySelector('input[type=radio]:checked');
          if (r && r.dataset.applyHref) window.location.href = r.dataset.applyHref;
          return;
        }
        var p = new URLSearchParams(window.location.search);
        deleteKeysForFieldPath(p, fieldPath);

        var hrefApply = [];
        var pairs = [];
        panel.querySelectorAll('input[type=checkbox]').forEach(function (cb) {
          if (!cb.checked) return;
          if (cb.dataset.applyHref) hrefApply.push(cb.dataset.applyHref);
          else if (cb.dataset.pkey) pairs.push({ k: cb.dataset.pkey, v: cb.value });
        });

        if (hrefApply.length) {
          hrefApply.forEach(function (href) {
            parseHrefParams(href).forEach(function (val, key) {
              p.set(key, val);
            });
          });
        }

        if (pairs.length === 1) p.set(pairs[0].k, pairs[0].v);
        else if (pairs.length > 1) {
          var pk0 = pairs[0].k;
          var inKey;
          if (pk0.endsWith('__exact')) inKey = pk0.slice(0, -7) + '__in';
          else if (pk0.endsWith('__iexact')) inKey = pk0.slice(0, -8) + '__in';
          else inKey = fieldPath + '__in';
          var vals = pairs.map(function (x) {
            return x.v;
          });
          p.set(inKey, vals.join(','));
        }

        window.location.search = p.toString();
      });

      document.addEventListener('click', function (ev) {
        if (!wrap.contains(ev.target)) {
          panel.classList.remove('is-open');
          btn.setAttribute('aria-expanded', 'false');
        }
      });
    });

    if (nav.querySelector('.admin-filter-dd')) {
      nav.classList.add('admin-filter-dd-ready');
    }
  }

  function run() {
    try {
      var nav = document.getElementById('changelist-filter');
      if (!nav) return;
      enhanceNav(nav);
    } catch (err) {
      if (typeof console !== 'undefined' && console.error) console.error('admin_changelist_filters:', err);
    }
  }

  ready(run);
})();
