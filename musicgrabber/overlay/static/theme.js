// Apply the saved theme before first paint, including the boot panel.
// "system" (the default) follows the OS colour scheme; core.js keeps it following.
try {
    const pref = localStorage.getItem('theme') || 'system';
    const theme = pref === 'light' || pref === 'dark' ? pref
        : window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', theme);
} catch (e) {}
