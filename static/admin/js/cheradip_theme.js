'use strict';
{
    // Two themes only: light (default) and dark. Same icon for both.
    function setTheme(mode) {
        if (mode !== 'light' && mode !== 'dark') {
            mode = 'light';
        }
        document.documentElement.dataset.theme = mode;
        localStorage.setItem('theme', mode);
    }

    function cycleTheme() {
        const current = localStorage.getItem('theme') || 'light';
        setTheme(current === 'light' ? 'dark' : 'light');
    }

    function initTheme() {
        const saved = localStorage.getItem('theme');
        setTheme(saved === 'dark' ? 'dark' : 'light');
    }

    window.addEventListener('load', function() {
        Array.from(document.getElementsByClassName('theme-toggle')).forEach(function(btn) {
            btn.addEventListener('click', cycleTheme);
        });
    });

    initTheme();
}
