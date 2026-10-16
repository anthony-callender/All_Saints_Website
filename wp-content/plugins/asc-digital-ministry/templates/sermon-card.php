<?php
/**
 * Sermon card (archive + grids).
 *
 * @var array $s Sermon data from ASC_DM\Sermons::data().
 */
defined( 'ABSPATH' ) || exit;
?>
<article class="asc-sermon-card">
	<a class="asc-sermon-card__link" href="<?php echo esc_url( $s['url'] ); ?>">
		<div class="asc-sermon-card__media">
			<?php if ( $s['thumbnail'] ) : ?>
				<img src="<?php echo esc_url( $s['thumbnail'] ); ?>" alt="" loading="lazy" decoding="async">
			<?php else : ?>
				<?php echo ASC_DM\Frontend::placeholder_art( $s['date'] ); // phpcs:ignore WordPress.Security.EscapeOutput -- static SVG. ?>
			<?php endif; ?>
			<?php if ( $s['audio_url'] ) : ?>
				<span class="asc-sermon-card__badge"><?php esc_html_e( 'Audio', 'asc-digital-ministry' ); ?></span>
			<?php endif; ?>
		</div>
		<div class="asc-sermon-card__body">
			<p class="asc-sermon-card__date"><time datetime="<?php echo esc_attr( $s['date'] ); ?>"><?php echo esc_html( $s['date_label'] ); ?></time></p>
			<h3 class="asc-sermon-card__title"><?php echo esc_html( $s['title'] ); ?></h3>
			<?php if ( $s['preacher'] ) : ?>
				<p class="asc-sermon-card__preacher"><?php echo esc_html( $s['preacher'] ); ?></p>
			<?php endif; ?>
			<?php if ( $s['scripture'] ) : ?>
				<p class="asc-sermon-card__scripture"><?php echo esc_html( implode( ' · ', $s['scripture'] ) ); ?></p>
			<?php endif; ?>
		</div>
	</a>
</article>
