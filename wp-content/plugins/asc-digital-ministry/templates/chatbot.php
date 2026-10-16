<?php
/**
 * Chatbot widget markup. The launcher stays hidden until chatbot.js runs, so
 * visitors without JavaScript simply don't see a non-working control.
 *
 * @var string   $endpoint
 * @var string[] $suggestions
 */
defined( 'ABSPATH' ) || exit;
?>
<div class="asc-chat" data-asc-chat data-endpoint="<?php echo esc_url( $endpoint ); ?>">
	<button type="button" class="asc-chat__launcher" aria-expanded="false" aria-controls="asc-chat-panel" hidden>
		<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v8a2.5 2.5 0 0 1-2.5 2.5H10l-4.5 4v-4h0A1.5 1.5 0 0 1 4 14.5z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>
		<span><?php esc_html_e( 'Questions?', 'asc-digital-ministry' ); ?></span>
	</button>

	<section id="asc-chat-panel" class="asc-chat__panel" role="dialog" aria-labelledby="asc-chat-title" hidden>
		<header class="asc-chat__header">
			<div>
				<h2 id="asc-chat-title" class="asc-chat__title"><?php esc_html_e( "All Saints' Assistant", 'asc-digital-ministry' ); ?></h2>
				<p class="asc-chat__subtitle"><?php esc_html_e( 'Ask me anything about the church', 'asc-digital-ministry' ); ?></p>
			</div>
			<button type="button" class="asc-chat__reset" data-asc-chat-reset hidden><?php esc_html_e( 'New chat', 'asc-digital-ministry' ); ?></button>
			<button type="button" class="asc-chat__close" data-asc-chat-close>
				<span class="screen-reader-text"><?php esc_html_e( 'Close assistant', 'asc-digital-ministry' ); ?></span>
				<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
			</button>
		</header>

		<div class="asc-chat__log" role="log" aria-live="polite" aria-relevant="additions">
			<div class="asc-chat__msg asc-chat__msg--bot" data-asc-chat-welcome>
				<p><?php esc_html_e( "Hi! I'm the All Saints' assistant. Ask me anything: planning a first visit, service times, kids and youth, ways to get involved, or what Anglican worship is like.", 'asc-digital-ministry' ); ?></p>
			</div>
		</div>

		<div class="asc-chat__suggestions" data-asc-chat-suggestions>
			<?php foreach ( $suggestions as $suggestion ) : ?>
				<button type="button" class="asc-chat__suggestion"><?php echo esc_html( $suggestion ); ?></button>
			<?php endforeach; ?>
		</div>

		<form class="asc-chat__form" novalidate>
			<label class="screen-reader-text" for="asc-chat-input"><?php esc_html_e( 'Your message', 'asc-digital-ministry' ); ?></label>
			<textarea id="asc-chat-input" name="message" rows="1" maxlength="1000" required placeholder="<?php esc_attr_e( 'Message the assistant…', 'asc-digital-ministry' ); ?>"></textarea>
			<button type="submit" class="asc-chat__send">
				<span class="screen-reader-text"><?php esc_html_e( 'Send', 'asc-digital-ministry' ); ?></span>
				<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M4 12l16-8-6 16-2.5-6.5z" fill="currentColor"/></svg>
			</button>
		</form>
		<p class="asc-chat__note"><?php esc_html_e( 'AI assistant using our church information; it can make mistakes. For prayer or pastoral care, please contact the office.', 'asc-digital-ministry' ); ?></p>
	</section>
</div>
