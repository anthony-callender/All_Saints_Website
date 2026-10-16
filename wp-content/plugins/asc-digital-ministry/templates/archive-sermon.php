<?php
/**
 * Classic-theme (Avada) sermon archive. Block themes use the registered block template instead.
 */
defined( 'ABSPATH' ) || exit;
get_header();
?>
<main id="main" class="asc-page asc-sermon-archive-page">
	<header class="asc-page-intro">
		<p class="asc-eyebrow"><?php esc_html_e( 'Worship', 'asc-digital-ministry' ); ?></p>
		<h1><?php esc_html_e( 'Sermons', 'asc-digital-ministry' ); ?></h1>
	</header>
	<?php echo ASC_DM\Sermons::shortcode_archive(); // phpcs:ignore WordPress.Security.EscapeOutput -- escaped in template. ?>
</main>
<?php
get_footer();
