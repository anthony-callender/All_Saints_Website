<?php
/**
 * Single sermon header, in the parish's established format:
 * date + preacher, scripture, the sermon audio (play + download), then a
 * link to the full service video on YouTube.
 *
 * @var array $s
 */
defined( 'ABSPATH' ) || exit;
$watch = $s['video_url'] ?: ( $s['video_id'] ? 'https://www.youtube.com/watch?v=' . $s['video_id'] : '' );
?>
<div class="asc-sermon-header">
	<p class="asc-sermon-meta">
		<time datetime="<?php echo esc_attr( $s['date'] ); ?>"><?php echo esc_html( $s['date_label'] ); ?></time>
		<?php if ( $s['preacher'] ) : ?>
			<span aria-hidden="true">·</span> <span class="asc-sermon-meta__preacher"><?php echo esc_html( $s['preacher'] ); ?></span>
		<?php endif; ?>
	</p>
	<?php if ( $s['scripture'] ) : ?>
		<ul class="asc-chips" aria-label="<?php esc_attr_e( 'Scripture', 'asc-digital-ministry' ); ?>">
			<?php foreach ( $s['scripture'] as $ref ) : ?>
				<li class="asc-chip"><?php echo esc_html( $ref ); ?></li>
			<?php endforeach; ?>
		</ul>
	<?php endif; ?>

	<?php if ( $s['audio_url'] ) : ?>
		<div class="asc-audio">
			<p class="asc-audio__label" id="asc-audio-label-<?php echo (int) $s['id']; ?>"><?php esc_html_e( 'Listen to the sermon', 'asc-digital-ministry' ); ?></p>
			<audio controls preload="none" src="<?php echo esc_url( $s['audio_url'] ); ?>" aria-labelledby="asc-audio-label-<?php echo (int) $s['id']; ?>"></audio>
			<a class="asc-audio__download" href="<?php echo esc_url( $s['audio_url'] ); ?>" download><?php esc_html_e( 'Download', 'asc-digital-ministry' ); ?></a>
		</div>
	<?php endif; ?>

	<?php if ( $watch ) : ?>
		<p class="asc-watch">
			<a href="<?php echo esc_url( $watch ); ?>">
				<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M8 5.5v13l11-6.5z" fill="currentColor"/></svg>
				<?php esc_html_e( 'Watch the full service on YouTube', 'asc-digital-ministry' ); ?>
			</a>
		</p>
	<?php endif; ?>
</div>
