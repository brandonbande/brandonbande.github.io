(() => {
  const roleElement = document.getElementById('role');
  if (roleElement) {
    const roles = ['developer', 'designer', 'community lead'];
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    if (!reducedMotion) {
      let roleIndex = 0;
      let characterIndex = roles[0].length;
      let deleting = false;

      function animateRole() {
        const currentRole = roles[roleIndex];
        roleElement.textContent = currentRole.slice(0, characterIndex);

        if (!deleting && characterIndex === currentRole.length) {
          deleting = true;
          window.setTimeout(animateRole, 1500);
          return;
        }

        if (deleting && characterIndex === 0) {
          deleting = false;
          roleIndex = (roleIndex + 1) % roles.length;
        }

        characterIndex += deleting ? -1 : 1;
        window.setTimeout(animateRole, deleting ? 55 : 100);
      }

      window.setTimeout(animateRole, 1800);
    }
  }

  const targetDate = new Date('2027-01-01T00:00:00');
  const units = {
    days: document.getElementById('countdown-days'),
    hours: document.getElementById('countdown-hours'),
    minutes: document.getElementById('countdown-minutes'),
    seconds: document.getElementById('countdown-seconds')
  };

  if (!units.days || !units.hours || !units.minutes || !units.seconds) return;

  function updateCountdown() {
    const remaining = Math.max(0, targetDate.getTime() - Date.now());
    const totalSeconds = Math.floor(remaining / 1000);
    const days = Math.floor(totalSeconds / 86400);
    const hours = Math.floor((totalSeconds % 86400) / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;

    units.days.textContent = String(days).padStart(3, '0');
    units.hours.textContent = String(hours).padStart(2, '0');
    units.minutes.textContent = String(minutes).padStart(2, '0');
    units.seconds.textContent = String(seconds).padStart(2, '0');
  }

  updateCountdown();
  window.setInterval(updateCountdown, 1000);
})();
