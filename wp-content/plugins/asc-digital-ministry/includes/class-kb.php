<?php
namespace ASC_DM;

defined( 'ABSPATH' ) || exit;

/**
 * "Church Knowledge": curated, verified facts that are the ONLY authority the
 * public assistant may use. Not publicly routable; editors manage it in wp-admin.
 *
 * Uses the classic editor screen on purpose: each entry is a short plain fact
 * sheet (title, body, source page, last verified), which is simpler for a
 * volunteer than a block canvas.
 */
final class KB {

	const POST_TYPE = 'church_kb';
	const NONCE     = 'asc_kb_meta';

	public static function init(): void {
		add_action( 'init', array( __CLASS__, 'register' ) );
		add_filter( 'use_block_editor_for_post_type', array( __CLASS__, 'classic_editor' ), 10, 2 );
		add_action( 'add_meta_boxes_' . self::POST_TYPE, array( __CLASS__, 'meta_boxes' ) );
		add_action( 'save_post_' . self::POST_TYPE, array( __CLASS__, 'save_meta' ), 10, 2 );
		// Keep the index in sync with publish/update/unpublish/delete.
		add_action( 'save_post_' . self::POST_TYPE, array( __CLASS__, 'sync_index' ), 20, 2 );
		add_action( 'before_delete_post', array( __CLASS__, 'on_delete' ) );
		add_action( 'trashed_post', array( __CLASS__, 'on_delete' ) );
		add_filter( 'manage_' . self::POST_TYPE . '_posts_columns', array( __CLASS__, 'columns' ) );
		add_action( 'manage_' . self::POST_TYPE . '_posts_custom_column', array( __CLASS__, 'column' ), 10, 2 );
	}

	public static function register(): void {
		register_post_type( self::POST_TYPE, array(
			'labels'              => array(
				'name'          => __( 'Church Knowledge', 'asc-digital-ministry' ),
				'singular_name' => __( 'Knowledge Entry', 'asc-digital-ministry' ),
				'menu_name'     => __( 'Church Knowledge', 'asc-digital-ministry' ),
				'add_new_item'  => __( 'Add Knowledge Entry', 'asc-digital-ministry' ),
				'edit_item'     => __( 'Edit Knowledge Entry', 'asc-digital-ministry' ),
				'all_items'     => __( 'All Entries', 'asc-digital-ministry' ),
			),
			'description'         => __( 'Verified facts used by the website assistant.', 'asc-digital-ministry' ),
			'public'              => false,
			'show_ui'             => true,
			'show_in_menu'        => true,
			'show_in_rest'        => true,
			'rest_base'           => 'church-knowledge',
			'exclude_from_search' => true,
			'publicly_queryable'  => false,
			'menu_icon'           => 'dashicons-book-alt',
			'menu_position'       => 6,
			'supports'            => array( 'title', 'editor', 'revisions' ),
		) );

		foreach ( array( 'asc_kb_source_url', 'asc_kb_last_verified' ) as $key ) {
			register_post_meta( self::POST_TYPE, $key, array(
				'type'              => 'string',
				'single'            => true,
				'default'           => '',
				'show_in_rest'      => true,
				'sanitize_callback' => 'asc_kb_source_url' === $key ? 'esc_url_raw' : array( __CLASS__, 'sanitize_date' ),
				'auth_callback'     => static fn() => current_user_can( 'edit_posts' ),
			) );
		}
	}

	public static function sanitize_date( $value ): string {
		$value = sanitize_text_field( (string) $value );
		return preg_match( '/^\d{4}-\d{2}-\d{2}$/', $value ) ? $value : '';
	}

	public static function classic_editor( bool $use, string $post_type ): bool {
		return self::POST_TYPE === $post_type ? false : $use;
	}

	public static function meta_boxes(): void {
		add_meta_box( 'asc-kb-source', __( 'Source & Verification', 'asc-digital-ministry' ), array( __CLASS__, 'render_meta_box' ), self::POST_TYPE, 'side', 'high' );
	}

	public static function render_meta_box( \WP_Post $post ): void {
		wp_nonce_field( self::NONCE, self::NONCE . '_nonce' );
		$url      = (string) get_post_meta( $post->ID, 'asc_kb_source_url', true );
		$verified = (string) get_post_meta( $post->ID, 'asc_kb_last_verified', true );
		$chunks   = Embeddings::chunk_count( $post->ID );
		?>
		<p>
			<label for="asc_kb_source_url"><strong><?php esc_html_e( 'Source page', 'asc-digital-ministry' ); ?></strong></label><br>
			<input type="url" class="widefat" id="asc_kb_source_url" name="asc_kb_source_url" value="<?php echo esc_attr( $url ); ?>" placeholder="https://">
			<span class="description"><?php esc_html_e( 'Shown to visitors as the place to read more.', 'asc-digital-ministry' ); ?></span>
		</p>
		<p>
			<label for="asc_kb_last_verified"><strong><?php esc_html_e( 'Last verified', 'asc-digital-ministry' ); ?></strong></label><br>
			<input type="date" id="asc_kb_last_verified" name="asc_kb_last_verified" value="<?php echo esc_attr( $verified ); ?>">
		</p>
		<p>
			<label><input type="checkbox" name="asc_kb_verify_today" value="1"> <?php esc_html_e( 'I checked this today', 'asc-digital-ministry' ); ?></label>
		</p>
		<p class="description">
			<?php
			echo esc_html( $chunks
				? sprintf( /* translators: %d chunk count */ _n( 'Assistant index: %d passage.', 'Assistant index: %d passages.', $chunks, 'asc-digital-ministry' ), $chunks )
				: __( 'Assistant index: not indexed yet (publish to index).', 'asc-digital-ministry' ) );
			?>
		</p>
		<p class="description"><?php esc_html_e( 'Public information only. Never add prayer requests, member details, pastoral notes, or giving records.', 'asc-digital-ministry' ); ?></p>
		<?php
	}

	public static function save_meta( int $post_id, \WP_Post $post ): void {
		if ( ! isset( $_POST[ self::NONCE . '_nonce' ] ) || ! wp_verify_nonce( sanitize_key( wp_unslash( $_POST[ self::NONCE . '_nonce' ] ) ), self::NONCE ) ) {
			return;
		}
		if ( ( defined( 'DOING_AUTOSAVE' ) && DOING_AUTOSAVE ) || ! current_user_can( 'edit_post', $post_id ) ) {
			return;
		}
		if ( isset( $_POST['asc_kb_source_url'] ) ) {
			update_post_meta( $post_id, 'asc_kb_source_url', esc_url_raw( wp_unslash( $_POST['asc_kb_source_url'] ) ) );
		}
		$verified = ! empty( $_POST['asc_kb_verify_today'] )
			? wp_date( 'Y-m-d' )
			: self::sanitize_date( wp_unslash( $_POST['asc_kb_last_verified'] ?? '' ) );
		update_post_meta( $post_id, 'asc_kb_last_verified', $verified );
	}

	public static function sync_index( int $post_id, \WP_Post $post ): void {
		if ( wp_is_post_revision( $post_id ) || wp_is_post_autosave( $post_id ) ) {
			return;
		}
		if ( 'publish' !== $post->post_status ) {
			Embeddings::delete_for_post( $post_id );
			return;
		}
		$result = Embeddings::index_post( $post_id );
		if ( is_wp_error( $result ) ) {
			update_post_meta( $post_id, '_asc_kb_index_error', $result->get_error_message() );
		} else {
			delete_post_meta( $post_id, '_asc_kb_index_error' );
		}
	}

	public static function on_delete( int $post_id ): void {
		if ( self::POST_TYPE === get_post_type( $post_id ) ) {
			Embeddings::delete_for_post( $post_id );
		}
	}

	public static function columns( array $columns ): array {
		$date = $columns['date'] ?? null;
		unset( $columns['date'] );
		$columns['asc_verified'] = __( 'Last verified', 'asc-digital-ministry' );
		$columns['asc_index']    = __( 'Assistant index', 'asc-digital-ministry' );
		if ( $date ) {
			$columns['date'] = $date;
		}
		return $columns;
	}

	public static function column( string $column, int $post_id ): void {
		if ( 'asc_verified' === $column ) {
			$verified = (string) get_post_meta( $post_id, 'asc_kb_last_verified', true );
			$stale    = $verified && strtotime( $verified ) < strtotime( '-6 months' );
			echo $verified ? esc_html( $verified ) . ( $stale ? ' <strong style="color:#b32d2e">' . esc_html__( '(re-check)', 'asc-digital-ministry' ) . '</strong>' : '' ) : '&mdash;';
		}
		if ( 'asc_index' === $column ) {
			$error = (string) get_post_meta( $post_id, '_asc_kb_index_error', true );
			$count = Embeddings::chunk_count( $post_id );
			echo $error ? '<span style="color:#b32d2e">' . esc_html( $error ) . '</span>' : esc_html( $count ? sprintf( '%d ✓', $count ) : '—' );
		}
	}
}
