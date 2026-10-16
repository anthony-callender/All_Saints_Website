<?php
/**
 * Featured "Latest Sermon" block for the homepage. Updates automatically
 * whenever a newer sermon is published.
 *
 * @var array $s
 */
defined( 'ABSPATH' ) || exit;
?>
<article class="asc-featured-sermon">
	<a class="asc-featured-sermon__media" href="<?php echo esc_url( $s['url'] ); ?>" tabindex="-1" aria-hidden="true">
		<?php if ( $s['thumbnail'] ) : ?>
			<img src="<?php echo esc_url( $s['thumbnail'] ); ?>" alt="" loading="lazy" decoding="async">
		<?php else : ?>
			<?php echo ASC_DM\Frontend::placeholder_art( $s['date'] ); // phpcs:ignore WordPress.Security.EscapeOutput -- static SVG. ?>
		<?php endif; ?>
		<span class="asc-featured-sermon__play"><svg viewBox="0 0 24 24" width="28" height="28" fill="currentColor" aria-hidden="true" focusable="false"><path d="M8 5.5v13l11-6.5z"/></svg></span>
	</a>
	<div class="asc-featured-sermon__body">
		<p class="asc-eyebrow"><?php esc_html_e( 'Latest Sermon', 'asc-digital-ministry' ); ?></p>
		<h3 class="asc-featured-sermon__title"><a href="<?php echo esc_url( $s['url'] ); ?>"><?php echo esc_html( $s['title'] ); ?></a></h3>
		<p class="asc-sermon-meta">
			<time datetime="<?php echo esc_attr( $s['date'] ); ?>"><?php echo esc_html( $s['date_label'] ); ?></time>
			<?php if ( $s['preacher'] ) : ?>
				<span aria-hidden="true">·</span> <?php echo esc_html( $s['preacher'] ); ?>
			<?php endif; ?>
		</p>
		<?php if ( $s['scripture'] ) : ?>
			<p class="asc-featured-sermon__scripture"><?php echo esc_html( implode( ' · ', $s['scripture'] ) ); ?></p>
		<?php endif; ?>
		<?php if ( $s['excerpt'] ) : ?>
			<p class="asc-featured-sermon__summary"><?php echo esc_html( $s['excerpt'] ); ?></p>
		<?php endif; ?>
		<p class="asc-actions">
			<a class="asc-button" href="<?php echo esc_url( $s['url'] ); ?>"><?php esc_html_e( 'Listen to the sermon', 'asc-digital-ministry' ); ?></a>
			<a class="asc-button asc-button--quiet" href="<?php echo esc_url( (string) get_post_type_archive_link( 'sermon' ) ); ?>"><?php esc_html_e( 'All sermons', 'asc-digital-ministry' ); ?></a>
		</p>
	</div>
</article>
