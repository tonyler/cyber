// Cybernetics Dashboard 3.0 - Main JavaScript

// Mobile scroll and pull-to-refresh fixes
(function() {
    // Prevent double-tap zoom on interactive elements (keeps pinch-zoom)
    let lastTouchEnd = 0;
    document.addEventListener('touchend', function(event) {
        if (!event.cancelable) {
            return;
        }
        const target = event.target && event.target.closest
            ? event.target.closest('a, button, input, select, textarea, .nav-link, .mobile-nav-link')
            : null;
        if (!target) {
            return;
        }
        const now = Date.now();
        if (now - lastTouchEnd <= 300) {
            event.preventDefault();
        }
        lastTouchEnd = now;
    }, { passive: false });

    // Prevent pull-to-refresh
    let startY = 0;
    document.addEventListener('touchstart', function(event) {
        startY = event.touches[0].pageY;
    }, { passive: true });

    document.addEventListener('touchmove', function(event) {
        const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
        const deltaY = event.touches[0].pageY - startY;

        // Prevent pull-to-refresh at top of page
        if (scrollTop === 0 && deltaY > 0) {
            event.preventDefault();
        }
    }, { passive: false });
})();

document.addEventListener('DOMContentLoaded', function() {
    // Mobile menu toggle
    const mobileMenuBtn = document.getElementById('mobile-menu-btn');
    const mobileMenu = document.getElementById('mobile-menu');

    if (mobileMenuBtn && mobileMenu) {
        mobileMenuBtn.addEventListener('click', function() {
            mobileMenu.classList.toggle('hidden');
        });
    }

    // Smooth scroll for anchor links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });

    // Auto-hide mobile menu on navigation
    document.querySelectorAll('.mobile-nav-link').forEach(link => {
        link.addEventListener('click', function() {
            if (mobileMenu) {
                mobileMenu.classList.add('hidden');
            }
        });
    });

    // Add loading state to forms
    document.querySelectorAll('form').forEach(form => {
        form.addEventListener('submit', function() {
            const submitBtn = this.querySelector('button[type="submit"]');
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.innerHTML = '<svg class="animate-spin -ml-1 mr-3 h-5 w-5 text-white inline" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg> Loading...';
            }
        });
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', function(e) {
        // Alt + H for Home
        if (e.altKey && e.key === 'h') {
            e.preventDefault();
            window.location.href = '/';
        }
        // Alt + M for Members
        if (e.altKey && e.key === 'm') {
            e.preventDefault();
            window.location.href = '/members';
        }
        // Alt + A for Activity
        if (e.altKey && e.key === 'a') {
            e.preventDefault();
            window.location.href = '/activity';
        }
    });

    // Toast notification system
    window.showToast = function(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `fixed bottom-4 right-4 px-6 py-3 rounded-lg shadow-lg text-white z-50 transform transition-all duration-300 ${
            type === 'success' ? 'bg-green-500' :
            type === 'error' ? 'bg-red-500' :
            type === 'warning' ? 'bg-yellow-500' :
            'bg-blue-500'
        }`;
        toast.textContent = message;
        toast.style.transform = 'translateY(100px)';
        toast.style.opacity = '0';

        document.body.appendChild(toast);

        // Animate in
        setTimeout(() => {
            toast.style.transform = 'translateY(0)';
            toast.style.opacity = '1';
        }, 10);

        // Animate out and remove
        setTimeout(() => {
            toast.style.transform = 'translateY(100px)';
            toast.style.opacity = '0';
            setTimeout(() => {
                document.body.removeChild(toast);
            }, 300);
        }, 3000);
    };

    // Check for URL parameters that trigger toasts
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.has('success')) {
        showToast(urlParams.get('success'), 'success');
    }
    if (urlParams.has('error')) {
        showToast(urlParams.get('error'), 'error');
    }

    // Add copy to clipboard functionality
    window.copyToClipboard = function(text) {
        navigator.clipboard.writeText(text).then(() => {
            showToast('Copied to clipboard!', 'success');
        }).catch(() => {
            showToast('Failed to copy', 'error');
        });
    };

    // Lazy load images
    if ('IntersectionObserver' in window) {
        const imageObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    if (img.dataset.src) {
                        img.src = img.dataset.src;
                        img.removeAttribute('data-src');
                        observer.unobserve(img);
                    }
                }
            });
        });

        document.querySelectorAll('img[data-src]').forEach(img => {
            imageObserver.observe(img);
        });
    }

    // Add animation class on scroll for elements
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    };

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('animate-in');
            }
        });
    }, observerOptions);

    document.querySelectorAll('.animate-on-scroll').forEach(el => {
        observer.observe(el);
    });

    // Performance monitoring
    if (window.performance && window.performance.timing) {
        window.addEventListener('load', () => {
            const loadTime = window.performance.timing.domContentLoadedEventEnd -
                           window.performance.timing.navigationStart;
            console.log(`Dashboard loaded in ${loadTime}ms`);
        });
    }

    console.log('Cybernetics Dashboard 3.0 initialized ⚡');

    // Members search functionality
    const memberSearch = document.getElementById('memberSearch');
    const membersGrid = document.getElementById('membersGrid');

    if (memberSearch && membersGrid) {
        memberSearch.addEventListener('input', function() {
            const query = this.value.toLowerCase().trim();
            const cards = membersGrid.querySelectorAll('.member-card');

            cards.forEach(card => {
                const name = card.dataset.name || '';
                // Also search in X handle (visible in the card)
                const xHandle = card.querySelector('a[href*="x.com"]');
                const xHandleText = xHandle ? xHandle.textContent.toLowerCase() : '';

                if (name.includes(query) || xHandleText.includes(query)) {
                    card.style.display = '';
                } else {
                    card.style.display = 'none';
                }
            });
        });
    }

    // Back to Top button functionality
    const backToTopButton = document.getElementById('back-to-top');

    if (backToTopButton) {
        window.addEventListener('scroll', () => {
            if (window.scrollY > 200) {
                backToTopButton.classList.remove('scale-0');
            } else {
                backToTopButton.classList.add('scale-0');
            }
        });

        backToTopButton.addEventListener('click', () => {
            window.scrollTo({
                top: 0,
                behavior: 'smooth'
            });
        });
    }
});
