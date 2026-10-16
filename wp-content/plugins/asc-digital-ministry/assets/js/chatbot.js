/**
 * All Saints' website assistant — vanilla JS, no dependencies.
 * A plain LLM chat: POST /wp-json/asc/v1/chat with stream=true and render the
 * server-sent events as they arrive. Model text is HTML-escaped before the
 * light Markdown formatting is applied. The conversation survives page
 * navigation (sessionStorage) until the visitor starts a new chat.
 */
(() => {
	'use strict';

	const root = document.querySelector('[data-asc-chat]');
	if (!root) return;

	const endpoint = root.dataset.endpoint;
	const launcher = root.querySelector('.asc-chat__launcher');
	const panel = root.querySelector('.asc-chat__panel');
	const log = root.querySelector('.asc-chat__log');
	const form = root.querySelector('.asc-chat__form');
	const input = form.querySelector('textarea');
	const send = form.querySelector('.asc-chat__send');
	const reset = root.querySelector('[data-asc-chat-reset]');
	const suggestions = root.querySelector('[data-asc-chat-suggestions]');
	const STORE = 'asc-chat-v2';
	const MAX_HISTORY = 20; // messages sent back for context (the server trims further)
	let history = [];
	let busy = false;

	// ---- Persistence (best effort; private windows may block storage) ----
	const save = (open = !panel.hidden) => {
		try { sessionStorage.setItem(STORE, JSON.stringify({ history, open })); } catch (e) { /* ignore */ }
	};
	const load = () => {
		try { return JSON.parse(sessionStorage.getItem(STORE)) || {}; } catch (e) { return {}; }
	};

	// ---- Light, safe Markdown: escape first, then bold / links / lists ----
	const escapeHtml = (s) => s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
	const inline = (s) => escapeHtml(s)
		.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
		.replace(/\[([^\]]+)\]\(((?:https?:\/\/|mailto:|tel:|\/)[^\s)]*)\)/g, '<a href="$2">$1</a>')
		.replace(/(^|[\s(])(https?:\/\/[^\s<)]+[^\s<).,!?;:])/g, '$1<a href="$2">$2</a>');
	const markdown = (text) => {
		const html = [];
		let list = null;
		let para = [];
		const flushPara = () => { if (para.length) { html.push(`<p>${para.join('<br>')}</p>`); para = []; } };
		const closeList = () => { if (list) { html.push(`</${list}>`); list = null; } };
		text.split('\n').forEach((raw) => {
			const line = raw.trimEnd();
			const bullet = line.match(/^\s*[-*•]\s+(.*)$/);
			const numbered = line.match(/^\s*\d+[.)]\s+(.*)$/);
			const heading = line.match(/^#{1,6}\s+(.*)$/);
			if (bullet || numbered) {
				flushPara();
				const type = bullet ? 'ul' : 'ol';
				if (list !== type) { closeList(); html.push(`<${type}>`); list = type; }
				// "Label: text" bullets get a bold label so long answers are easy to scan.
				const item = (bullet || numbered)[1].replace(/^([^:*\[\]]{2,40}):\s/, '**$1:** ');
				html.push(`<li>${inline(item)}</li>`);
			} else if (!line.trim()) {
				flushPara(); // a blank line between bullets keeps the list open
			} else if (heading) {
				flushPara(); closeList();
				html.push(`<p><strong>${inline(heading[1])}</strong></p>`);
			} else {
				closeList();
				para.push(inline(line));
			}
		});
		flushPara(); closeList();
		return html.join('');
	};

	// ---- UI ----
	const scrollToEnd = () => { log.scrollTop = log.scrollHeight; };

	const bubble = (role, { error = false } = {}) => {
		const el = document.createElement('div');
		el.className = `asc-chat__msg asc-chat__msg--${role === 'user' ? 'user' : 'bot'}${error ? ' asc-chat__msg--error' : ''}`;
		log.append(el);
		return el;
	};
	const addUser = (text) => {
		const el = bubble('user');
		const p = document.createElement('p');
		p.textContent = text;
		el.append(p);
		scrollToEnd();
	};
	const addBot = (text, opts) => {
		const el = bubble('bot', opts);
		el.innerHTML = markdown(text);
		scrollToEnd();
		return el;
	};
	const typing = () => {
		const el = bubble('bot');
		el.setAttribute('aria-label', 'The assistant is typing');
		el.innerHTML = '<span class="asc-chat__typing" aria-hidden="true"><i></i><i></i><i></i></span>';
		scrollToEnd();
		return el;
	};

	const syncChrome = () => {
		const started = history.length > 0;
		if (suggestions) suggestions.hidden = started;
		reset.hidden = !started;
	};

	const open = (focus = true) => {
		panel.hidden = false;
		launcher.hidden = true;
		launcher.setAttribute('aria-expanded', 'true');
		save(true);
		scrollToEnd();
		if (focus) input.focus();
	};
	const close = () => {
		panel.hidden = true;
		launcher.hidden = false;
		launcher.setAttribute('aria-expanded', 'false');
		save(false);
		launcher.focus();
	};

	const errorMessage = async (response) => {
		const data = await response.json().catch(() => ({}));
		const params = (data.data && data.data.params) || {};
		return params.message || params.history || data.message || 'Sorry, something went wrong. Please try again in a moment.';
	};

	// ---- Send a message and stream the reply ----
	const ask = async (message) => {
		message = message.trim();
		if (!message || busy) return;
		busy = true;
		send.disabled = true;
		addUser(message);
		input.value = '';
		const pending = typing();
		let reply = '';
		let target = null;
		let frame = 0;
		const paint = () => {
			frame = 0;
			if (!target) { pending.remove(); target = addBot(''); target.classList.add('is-streaming'); }
			const nearBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 60;
			target.innerHTML = markdown(reply);
			if (nearBottom) scrollToEnd();
		};

		try {
			const response = await fetch(endpoint, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
				body: JSON.stringify({ message, history: history.slice(-MAX_HISTORY), stream: true }),
			});
			if (!response.ok) {
				pending.remove();
				addBot(await errorMessage(response), { error: true });
				return;
			}
			let failure = '';
			if ((response.headers.get('content-type') || '').includes('text/event-stream') && response.body) {
				const reader = response.body.getReader();
				const decoder = new TextDecoder();
				let buffer = '';
				for (;;) {
					const { value, done } = await reader.read();
					if (done) break;
					buffer += decoder.decode(value, { stream: true });
					let cut;
					while ((cut = buffer.indexOf('\n\n')) !== -1) {
						const line = buffer.slice(0, cut).trim();
						buffer = buffer.slice(cut + 2);
						if (!line.startsWith('data:')) continue;
						const event = JSON.parse(line.slice(5));
						if (event.delta) {
							reply += event.delta;
							if (!frame) frame = requestAnimationFrame(paint);
						}
						if (event.error) failure = event.error;
					}
				}
			} else {
				reply = (await response.json()).answer || ''; // non-streaming fallback
			}
			if (frame) cancelAnimationFrame(frame);
			if (reply) {
				paint();
				target.classList.remove('is-streaming');
				history.push({ role: 'user', content: message }, { role: 'assistant', content: reply });
				history = history.slice(-MAX_HISTORY);
				save();
			} else {
				pending.remove();
				addBot(failure || 'Sorry, something went wrong. Please try again in a moment.', { error: true });
			}
		} catch (err) {
			pending.remove();
			if (target) target.classList.remove('is-streaming');
			addBot('We could not reach the assistant. Please check your connection and try again.', { error: true });
		} finally {
			busy = false;
			send.disabled = false;
			syncChrome();
			input.focus();
		}
	};

	// ---- Wiring ----
	launcher.hidden = false;
	launcher.addEventListener('click', () => open());
	root.querySelector('[data-asc-chat-close]').addEventListener('click', close);
	panel.addEventListener('keydown', (event) => { if (event.key === 'Escape') close(); });

	reset.addEventListener('click', () => {
		if (busy) return;
		history = [];
		log.querySelectorAll('.asc-chat__msg:not([data-asc-chat-welcome])').forEach((el) => el.remove());
		save();
		syncChrome();
		input.focus();
	});

	form.addEventListener('submit', (event) => {
		event.preventDefault();
		ask(input.value);
	});
	// Enter sends; Shift+Enter adds a new line.
	input.addEventListener('keydown', (event) => {
		if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
			event.preventDefault();
			ask(input.value);
		}
	});
	if (suggestions) {
		suggestions.addEventListener('click', (event) => {
			const button = event.target.closest('button');
			if (button) ask(button.textContent);
		});
	}

	// Restore the conversation from earlier pages in this visit.
	const saved = load();
	if (Array.isArray(saved.history)) {
		history = saved.history.filter((m) => m && (m.role === 'user' || m.role === 'assistant') && typeof m.content === 'string').slice(-MAX_HISTORY);
		history.forEach((m) => (m.role === 'user' ? addUser(m.content) : addBot(m.content)));
	}
	syncChrome();
	if (saved.open) open(false);
})();
