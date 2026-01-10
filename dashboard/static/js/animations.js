/*
 * Entrance Animations
 * Intersection Observer for scroll-triggered animations
 */

document.addEventListener('DOMContentLoaded', function() {
  // Intersection Observer for entrance animations
  const animateOnScroll = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.remove('paused');
        }
      });
    },
    {
      threshold: 0.1,
      rootMargin: '0px 0px -100px 0px'
    }
  );

  // Observe all animated elements
  const animatedElements = document.querySelectorAll('[data-animate]');
  animatedElements.forEach((el) => {
    el.classList.add('paused');
    animateOnScroll.observe(el);
  });
});
