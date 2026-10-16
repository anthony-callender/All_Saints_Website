<?php
/**
 * @var array[] $sermons
 */
defined( 'ABSPATH' ) || exit;
if ( ! $sermons ) {
	return;
}
?>
<div class="asc-sermon-grid">
	<?php foreach ( $sermons as $s ) : ?>
		<?php include __DIR__ . '/sermon-card.php'; ?>
	<?php endforeach; ?>
</div>
