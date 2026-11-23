/**
 * TrashTrekyx — Universal Theme Switcher Engine
 * Supports Light & Dark modes, system auto-detection, and persistent preference.
 */
(function () {
    'use strict';

    function getSavedTheme() {
        try {
            var saved = localStorage.getItem('trashtrekyx_theme');
            if (saved === 'dark' || saved === 'light') return saved;
        } catch (e) {}
        if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
            return 'dark';
        }
        return 'light';
    }

    function updateIcons(theme) {
        var buttons = document.querySelectorAll('.theme-toggle-btn');
        buttons.forEach(function (btn) {
            var isDark = theme === 'dark';
            btn.setAttribute('aria-label', isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode');
            btn.setAttribute('title', isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode');
            var icon = btn.querySelector('i');
            if (icon) {
                icon.className = isDark ? 'fa-solid fa-sun' : 'fa-solid fa-moon';
                icon.style.color = isDark ? '#fbbf24' : '#64748b';
            }
        });
    }

    function applyTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        try {
            localStorage.setItem('trashtrekyx_theme', theme);
        } catch (e) {}
        updateIcons(theme);
    }

    window.toggleTheme = function () {
        var current = document.documentElement.getAttribute('data-theme') || getSavedTheme();
        var next = current === 'dark' ? 'light' : 'dark';
        applyTheme(next);
    };

    // Apply immediately to prevent FOUC
    var initial = getSavedTheme();
    document.documentElement.setAttribute('data-theme', initial);

    // Sync icons when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            updateIcons(document.documentElement.getAttribute('data-theme') || initial);
        });
    } else {
        updateIcons(initial);
    }

    // Listen to OS-level preference changes if user hasn't explicitly set preference
    if (window.matchMedia) {
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function (e) {
            try {
                if (!localStorage.getItem('trashtrekyx_theme')) {
                    applyTheme(e.matches ? 'dark' : 'light');
                }
            } catch (err) {}
        });
    }
})();
