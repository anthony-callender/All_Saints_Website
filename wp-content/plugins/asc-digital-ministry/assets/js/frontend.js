/**
 * Small progressive enhancement (everything works without this file):
 * the sermon archive's preacher <select> submits itself on change.
 */
(() => {
	'use strict';

	document.querySelectorAll('[data-asc-autosubmit]').forEach((select) => {
		select.addEventListener('change', () => select.form && select.form.submit());
		const button = select.form && select.form.querySelector('button[type="submit"]');
		if (button) button.hidden = true;
	});
})();
