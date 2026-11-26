(() => {
  const roleElement = document.getElementById('role');
  if (!roleElement) return;

  const roles = ['developer', 'designer', 'community lead'];
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reducedMotion) return;

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
})();
