/* Cybernetics — Hedera Edition — main.js */

document.addEventListener('DOMContentLoaded', () => {

  // ── Mobile menu toggle ──────────────────────────────────────────────────
  const mobileBtn  = document.getElementById('mobile-menu-btn');
  const mobileMenu = document.getElementById('mobile-menu');

  if (mobileBtn && mobileMenu) {
    mobileBtn.addEventListener('click', () => {
      mobileMenu.classList.toggle('open');
    });

    // Close on outside click
    document.addEventListener('click', e => {
      if (!mobileBtn.contains(e.target) && !mobileMenu.contains(e.target)) {
        mobileMenu.classList.remove('open');
      }
    });
  }

  // ── Member search ───────────────────────────────────────────────────────
  const searchInput = document.getElementById('memberSearch');
  const membersGrid = document.getElementById('membersGrid');

  if (searchInput && membersGrid) {
    searchInput.addEventListener('input', () => {
      const query = searchInput.value.toLowerCase().trim();
      membersGrid.querySelectorAll('[data-name]').forEach(card => {
        const name   = (card.dataset.name   || '').toLowerCase();
        const status = (card.dataset.status || '').toLowerCase();
        const match  = !query || name.includes(query) || status.includes(query);
        card.style.display = match ? '' : 'none';
      });
    });
  }

  // ── Stagger member card animations ─────────────────────────────────────
  if (membersGrid) {
    membersGrid.querySelectorAll('.h-member-card').forEach((card, i) => {
      card.style.animationDelay = `${i * 0.04}s`;
    });
  }

});
