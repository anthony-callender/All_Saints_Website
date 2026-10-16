<?php
/**
 * Sermon archive body (used by the block template and the classic template).
 *
 * @var WP_Query $query
 * @var string[] $preachers
 * @var string   $current
 */
defined( 'ABSPATH' ) || exit;
?>
<section class="asc-sermon-archive" aria-label="<?php esc_attr_e( 'Sermon archive', 'asc-digital-ministry' ); ?>">
	<?php if ( count( $preachers ) > 1 ) : ?>
		<form class="asc-filter" method="get" action="<?php echo esc_url( get_post_type_archive_link( 'sermon' ) ); ?>">
			<label for="asc-preacher-filter"><?php esc_html_e( 'Preacher', 'asc-digital-ministry' ); ?></label>
			<select id="asc-preacher-filter" name="preacher" data-asc-autosubmit>
				<option value=""><?php esc_html_e( 'All preachers', 'asc-digital-ministry' ); ?></option>
				<?php foreach ( $preachers as $name ) : ?>
					<option value="<?php echo esc_attr( $name ); ?>" <?php selected( $current, $name ); ?>><?php echo esc_html( $name ); ?></option>
				<?php endforeach; ?>
			</select>
			<button type="submit" class="asc-button asc-button--quiet"><?php esc_html_e( 'Filter', 'asc-digital-ministry' ); ?></button>
		</form>
	<?php endif; ?>

	<?php if ( $query->have_posts() ) : ?>
		<?php
		$sermons = array_map( array( 'ASC_DM\Sermons', 'data' ), wp_list_pluck( $query->posts, 'ID' ) );
		include __DIR__ . '/sermon-grid.php';
		?>
		<nav class="asc-pagination" aria-label="<?php esc_attr_e( 'Sermon pages', 'asc-digital-ministry' ); ?>">
			<?php
			echo wp_kses_post( (string) paginate_links( array(
				'total'     => $query->max_num_pages,
				'current'   => max( 1, (int) get_query_var( 'paged' ) ),
				'add_args'  => $current ? array( 'preacher' => $current ) : false,
				'prev_text' => __( 'Newer', 'asc-digital-ministry' ),
				'next_text' => __( 'Older', 'asc-digital-ministry' ),
			) ) );
			?>
		</nav>
	<?php else : ?>
		<p class="asc-empty"><?php esc_html_e( 'No sermons found.', 'asc-digital-ministry' ); ?></p>
	<?php endif; ?>
</section>
<?php
wp_reset_postdata();
