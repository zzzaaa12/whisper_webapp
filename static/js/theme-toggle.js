// Theme Toggle Functionality - Shared across all pages
(function() {
    'use strict';

    const htmlElement = document.documentElement;

    // Load saved theme from localStorage or default to light
    const savedTheme = localStorage.getItem('theme') || 'light';
    setTheme(savedTheme);

    // Initialize theme toggle buttons when DOM is ready
    document.addEventListener('DOMContentLoaded', function() {
        initThemeToggle();
    });

    function initThemeToggle() {
        // Desktop theme toggle button
        const themeToggleBtn = document.getElementById('theme-toggle-btn');
        const themeIcon = document.getElementById('theme-icon');

        // Mobile theme toggle button
        const themeToggleBtnMobile = document.getElementById('theme-toggle-btn-mobile');
        const themeIconMobile = document.getElementById('theme-icon-mobile');

        // Theme toggle button click handler (Desktop)
        if (themeToggleBtn) {
            themeToggleBtn.addEventListener('click', function() {
                toggleTheme();
            });
        }

        // Theme toggle button click handler (Mobile)
        if (themeToggleBtnMobile) {
            themeToggleBtnMobile.addEventListener('click', function() {
                toggleTheme();
            });
        }

        // Update icons based on current theme
        updateThemeIcons();
    }

    function toggleTheme() {
        const currentTheme = htmlElement.getAttribute('data-theme');
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        setTheme(newTheme);
        localStorage.setItem('theme', newTheme);
        updateThemeIcons();
    }

    function setTheme(theme) {
        htmlElement.setAttribute('data-theme', theme);
    }

    function updateThemeIcons() {
        const theme = htmlElement.getAttribute('data-theme');
        const themeIcon = document.getElementById('theme-icon');
        const themeIconMobile = document.getElementById('theme-icon-mobile');
        const themeToggleBtn = document.getElementById('theme-toggle-btn');

        if (theme === 'dark') {
            if (themeIcon) themeIcon.className = 'bi bi-sun-fill';
            if (themeIconMobile) themeIconMobile.className = 'bi bi-sun-fill';
            if (themeToggleBtn) themeToggleBtn.title = '切換到亮色模式';
        } else {
            if (themeIcon) themeIcon.className = 'bi bi-moon-fill';
            if (themeIconMobile) themeIconMobile.className = 'bi bi-moon-fill';
            if (themeToggleBtn) themeToggleBtn.title = '切換到暗色模式';
        }
    }

    // Expose setTheme function globally if needed
    window.setTheme = setTheme;
})();
