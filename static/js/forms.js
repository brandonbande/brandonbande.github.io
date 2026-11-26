// Enquiry forms. Without JS the forms POST natively with browser validation.
// With JS: accessible inline validation, async submit, success message, analytics event on success.
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

function labelText(field) {
  const label = field.closest('.field')?.querySelector('label');
  return label ? label.firstChild.textContent.trim() : field.name;
}

function check(form, field) {
  const msgs = form.dataset;
  const value = field.value.trim();
  let error = '';
  if (field.required && !value) error = msgs.msgRequired.replace('{label}', labelText(field));
  else if (field.type === 'email' && value && !EMAIL.test(value)) error = msgs.msgEmail;
  const out = document.getElementById(`${field.id}-error`);
  field.setAttribute('aria-invalid', String(Boolean(error)));
  if (out) { out.textContent = error; out.hidden = !error; }
  return !error;
}

for (const form of document.querySelectorAll('form[data-form]')) {
  form.noValidate = true;
  const status = form.querySelector('.form-status');
  const fields = [...form.querySelectorAll('input:not([tabindex="-1"]), select, textarea')];
  let attempted = false;

  fields.forEach((f) => f.addEventListener('input', () => { if (attempted) check(form, f); }));

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    attempted = true;
    const invalid = fields.filter((f) => !check(form, f));
    status.classList.remove('is-error');
    if (invalid.length) {
      status.textContent = form.dataset.msgSummary;
      status.classList.add('is-error');
      invalid[0].focus();
      return;
    }
    if (form.dataset.unconfigured) {
      status.textContent = form.dataset.unconfigured;
      return;
    }
    const honeypot = form.querySelector('.hp input');
    const button = form.querySelector('[type="submit"]');
    button.disabled = true;
    status.textContent = form.dataset.msgSending;
    try {
      if (!honeypot || !honeypot.value) {
        const res = await fetch(form.action, { method: 'POST', body: new FormData(form), headers: { Accept: 'application/json' } });
        if (!res.ok) throw new Error(String(res.status));
      }
      const done = document.createElement('p');
      done.className = 'form-success';
      done.tabIndex = -1;
      done.textContent = form.dataset.msgSuccess;
      form.replaceWith(done);
      done.focus();
      if (window.goatcounter && window.goatcounter.count) {
        window.goatcounter.count({ path: form.dataset.event, title: form.dataset.event, event: true });
      }
    } catch {
      status.textContent = form.dataset.msgFailure;
      status.classList.add('is-error');
      button.disabled = false;
    }
  });
}
