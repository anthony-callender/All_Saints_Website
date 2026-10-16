<?php
namespace ASC_DM;

defined( 'ABSPATH' ) || exit;

/**
 * Sermon custom post type, metadata, and theme-agnostic rendering.
 *
 * Editorial content (summary, scripture, key ideas) lives in normal Gutenberg
 * blocks in post_content. Media + facts live in post meta and are rendered
 * around the content, so editors never hand-edit embed markup.
 */
final class Sermons {

	const POST_TYPE = 'sermon';

	/** meta key => [type, description, public?] */
	const META = array(
		'asc_sermon_date'          => array( 'string', 'Service date (Y-m-d).', true ),
		'asc_preacher'             => array( 'string', 'Preacher as published (e.g. "The Rev. Scott Bailey").', true ),
		'asc_scripture_references' => array( 'array', 'Scripture references, e.g. ["2 Corinthians 13:5-14"].', true ),
		'asc_series'               => array( 'string', 'Sermon series, if any.', true ),
		'asc_youtube_video_id'     => array( 'string', 'YouTube video ID (external unique key).', true ),
		'asc_youtube_url'          => array( 'string', 'YouTube watch URL.', true ),
		'asc_audio_attachment_id'  => array( 'integer', 'Media Library attachment ID of the sermon MP3.', true ),
		'asc_audio_url'            => array( 'string', 'External audio URL (historical imports).', true ),
		'asc_source_published_at'  => array( 'string', 'YouTube publish timestamp (ISO 8601).', true ),
		'asc_source_url'           => array( 'string', 'Legacy Squarespace URL (for redirects).', false ),
		'asc_transcript'           => array( 'string', 'Raw sermon transcript (private; editors only).', false ),
		'asc_pipeline_version'     => array( 'string', 'Sermon worker version that created this post.', false ),
	);

	public static function init(): void {
		add_action( 'init', array( __CLASS__, 'register' ) );
		add_filter( 'the_content', array( __CLASS__, 'wrap_single_content' ), 5 );
		add_shortcode( 'asc_sermon_archive', array( __CLASS__, 'shortcode_archive' ) );
		add_shortcode( 'asc_sermons', array( __CLASS__, 'shortcode_recent' ) );
		add_shortcode( 'asc_latest_sermon', array( __CLASS__, 'shortcode_latest' ) );
		add_action( 'init', array( __CLASS__, 'register_block_templates' ), 20 );
		// The theme ships its own home/archive templates; put ours first in the lookup.
		add_filter( 'home_template_hierarchy', static fn( array $t ): array => array_merge( array( 'asc-news' ), $t ) );
		foreach ( array( 'category', 'tag', 'date', 'author' ) as $type ) {
			add_filter( "{$type}_template_hierarchy", static fn( array $t ): array => array_merge( array( 'asc-news-archive' ), $t ) );
		}
		add_filter( 'template_include', array( __CLASS__, 'classic_templates' ) );
		add_action( 'pre_get_posts', array( __CLASS__, 'order_by_sermon_date' ) );
	}

	public static function register(): void {
		register_post_type( self::POST_TYPE, array(
			'labels'        => array(
				'name'          => __( 'Sermons', 'asc-digital-ministry' ),
				'singular_name' => __( 'Sermon', 'asc-digital-ministry' ),
				'add_new_item'  => __( 'Add New Sermon', 'asc-digital-ministry' ),
				'edit_item'     => __( 'Edit Sermon', 'asc-digital-ministry' ),
				'all_items'     => __( 'All Sermons', 'asc-digital-ministry' ),
			),
			'public'        => true,
			'has_archive'   => true,
			'show_in_rest'  => true,
			'rest_base'     => 'sermons',
			'menu_icon'     => 'dashicons-microphone',
			'menu_position' => 5,
			'rewrite'       => array( 'slug' => 'sermons', 'with_front' => false ),
			'supports'      => array( 'title', 'editor', 'excerpt', 'thumbnail', 'revisions', 'author', 'custom-fields' ),
		) );

		foreach ( self::META as $key => list( $type, $description, $public ) ) {
			$schema = array( 'type' => $type, 'description' => $description );
			if ( 'array' === $type ) {
				$schema['items'] = array( 'type' => 'string' );
			}
			if ( ! $public ) {
				// Present for authenticated edit requests only, never in public view responses.
				$schema['context'] = array( 'edit' );
			}
			register_post_meta( self::POST_TYPE, $key, array(
				'type'              => $type,
				'description'       => $description,
				'single'            => true,
				'default'           => 'array' === $type ? array() : ( 'integer' === $type ? 0 : '' ),
				'show_in_rest'      => array( 'schema' => $schema ),
				'sanitize_callback' => array( __CLASS__, 'sanitize_' . $type ),
				'auth_callback'     => static fn() => current_user_can( 'edit_posts' ),
			) );
		}
	}

	public static function sanitize_string( $value ): string {
		return sanitize_textarea_field( (string) $value );
	}

	public static function sanitize_integer( $value ): int {
		return absint( $value );
	}

	public static function sanitize_array( $value ): array {
		return array_values( array_filter( array_map( 'sanitize_text_field', (array) $value ) ) );
	}

	public static function is_valid_video_id( string $id ): bool {
		return (bool) preg_match( '/^[A-Za-z0-9_-]{11}$/', $id );
	}

	/** Find a sermon (any status except trash) by YouTube video ID. */
	public static function find_by_video_id( string $video_id ): int {
		$ids = get_posts( array(
			'post_type'        => self::POST_TYPE,
			'post_status'      => array( 'publish', 'draft', 'pending', 'future', 'private' ),
			'meta_key'         => 'asc_youtube_video_id', // phpcs:ignore WordPress.DB.SlowDBQuery
			'meta_value'       => $video_id,              // phpcs:ignore WordPress.DB.SlowDBQuery
			'fields'           => 'ids',
			'posts_per_page'   => 1,
			'no_found_rows'    => true,
			'suppress_filters' => true,
		) );
		return $ids ? (int) $ids[0] : 0;
	}

	/** Archive ordering: by service date, newest first. */
	public static function order_by_sermon_date( \WP_Query $query ): void {
		if ( ! is_admin() && $query->is_main_query() && $query->is_post_type_archive( self::POST_TYPE ) ) {
			$query->set( 'meta_key', 'asc_sermon_date' );
			$query->set( 'orderby', array( 'meta_value' => 'DESC', 'date' => 'DESC' ) );
		}
	}

	// ---------------------------------------------------------------------
	// Data helpers used by templates.
	// ---------------------------------------------------------------------

	public static function data( int $post_id ): array {
		$date        = (string) get_post_meta( $post_id, 'asc_sermon_date', true );
		$video_id    = (string) get_post_meta( $post_id, 'asc_youtube_video_id', true );
		$attachment  = (int) get_post_meta( $post_id, 'asc_audio_attachment_id', true );
		$audio_url   = $attachment ? (string) wp_get_attachment_url( $attachment ) : (string) get_post_meta( $post_id, 'asc_audio_url', true );
		$scripture   = (array) get_post_meta( $post_id, 'asc_scripture_references', true );
		// Only an editor-chosen Featured Image; otherwise season-coloured date artwork.
		// (YouTube's auto-picked frame is often a hymn-lyrics slide.)
		$thumb       = get_the_post_thumbnail_url( $post_id, 'large' );
		return array(
			'id'         => $post_id,
			'title'      => get_the_title( $post_id ),
			'url'        => get_permalink( $post_id ),
			'date'       => $date,
			'date_label' => $date ? wp_date( 'F j, Y', strtotime( $date . ' 12:00:00' ) ) : get_the_date( '', $post_id ),
			'preacher'   => (string) get_post_meta( $post_id, 'asc_preacher', true ),
			'scripture'  => array_filter( $scripture ),
			'video_id'   => $video_id,
			'video_url'  => (string) get_post_meta( $post_id, 'asc_youtube_url', true ),
			'audio_url'  => $audio_url,
			'thumbnail'  => $thumb ?: '',
			'excerpt'    => has_excerpt( $post_id ) ? get_the_excerpt( $post_id ) : '',
		);
	}

	public static function template( string $name, array $vars = array() ): string {
		ob_start();
		extract( $vars, EXTR_SKIP ); // phpcs:ignore WordPress.PHP.DontExtract
		include ASC_DM_DIR . 'templates/' . $name . '.php';
		// Collapse newlines: shortcode output inside post content passes through
		// wpautop, which would otherwise inject stray <p>/<br> into the markup.
		return (string) preg_replace( '/\s*\n\s*/', ' ', (string) ob_get_clean() );
	}

	// ---------------------------------------------------------------------
	// Rendering.
	// ---------------------------------------------------------------------

	/** Put date/preacher, video and audio above the editable sermon body. */
	public static function wrap_single_content( string $content ): string {
		if ( ! is_singular( self::POST_TYPE ) || ! in_the_loop() || ! is_main_query() ) {
			return $content;
		}
		Frontend::enqueue();
		$header = self::template( 'sermon-media', array( 's' => self::data( get_the_ID() ) ) );
		return $header . '<div class="asc-sermon-body">' . $content . '</div>';
	}

	public static function shortcode_archive(): string {
		Frontend::enqueue();
		$preacher = isset( $_GET['preacher'] ) ? sanitize_text_field( wp_unslash( $_GET['preacher'] ) ) : ''; // phpcs:ignore WordPress.Security.NonceVerification
		$paged    = max( 1, (int) get_query_var( 'paged' ), (int) get_query_var( 'page' ) );
		$args     = array(
			'post_type'      => self::POST_TYPE,
			'post_status'    => 'publish',
			'posts_per_page' => 12,
			'paged'          => $paged,
			'meta_key'       => 'asc_sermon_date', // phpcs:ignore WordPress.DB.SlowDBQuery
			'orderby'        => array( 'meta_value' => 'DESC', 'date' => 'DESC' ),
		);
		if ( $preacher ) {
			$args['meta_query'] = array( array( 'key' => 'asc_preacher', 'value' => $preacher ) ); // phpcs:ignore WordPress.DB.SlowDBQuery
		}
		$query = new \WP_Query( $args );
		return self::template( 'sermon-archive', array(
			'query'     => $query,
			'preachers' => self::preachers(),
			'current'   => $preacher,
		) );
	}

	public static function shortcode_recent( $atts ): string {
		Frontend::enqueue();
		$atts = shortcode_atts( array( 'count' => 3, 'offset' => 0 ), $atts, 'asc_sermons' );
		$ids  = self::latest_ids( (int) $atts['count'], (int) $atts['offset'] );
		return self::template( 'sermon-grid', array( 'sermons' => array_map( array( __CLASS__, 'data' ), $ids ) ) );
	}

	public static function shortcode_latest(): string {
		Frontend::enqueue();
		$ids = self::latest_ids( 1 );
		return $ids ? self::template( 'sermon-featured', array( 's' => self::data( $ids[0] ) ) ) : '';
	}

	/** @return int[] */
	public static function latest_ids( int $count, int $offset = 0 ): array {
		return get_posts( array(
			'post_type'      => self::POST_TYPE,
			'post_status'    => 'publish',
			'posts_per_page' => max( 1, min( 24, $count ) ),
			'offset'         => max( 0, $offset ),
			'meta_key'       => 'asc_sermon_date', // phpcs:ignore WordPress.DB.SlowDBQuery
			'orderby'        => array( 'meta_value' => 'DESC', 'date' => 'DESC' ),
			'fields'         => 'ids',
		) );
	}

	/** @return string[] */
	public static function preachers(): array {
		global $wpdb;
		$rows = $wpdb->get_col( $wpdb->prepare(
			"SELECT DISTINCT pm.meta_value FROM {$wpdb->postmeta} pm
			 INNER JOIN {$wpdb->posts} p ON p.ID = pm.post_id
			 WHERE pm.meta_key = %s AND p.post_type = %s AND p.post_status = 'publish' AND pm.meta_value <> ''
			 ORDER BY pm.meta_value",
			'asc_preacher',
			self::POST_TYPE
		) );
		return array_map( 'strval', $rows );
	}

	/** Block themes: plugin-provided templates (still overridable in the Site Editor). */
	public static function register_block_templates(): void {
		if ( ! function_exists( 'register_block_template' ) ) {
			return;
		}
		$header = '<!-- wp:template-part {"slug":"header","tagName":"header"} /-->';
		$footer = '<!-- wp:template-part {"slug":"footer","tagName":"footer"} /-->';
		register_block_template( 'asc-digital-ministry//archive-sermon', array(
			'title'       => __( 'Sermon Archive', 'asc-digital-ministry' ),
			'description' => __( 'Media-library style sermon archive.', 'asc-digital-ministry' ),
			'content'     => $header . '
<!-- wp:group {"tagName":"main","className":"asc-page asc-sermon-archive-page","layout":{"type":"constrained","wideSize":"var(--asc-content-wide)"}} -->
<main class="wp-block-group asc-page asc-sermon-archive-page">
<!-- wp:group {"className":"asc-page-intro","layout":{"type":"constrained"}} --><div class="wp-block-group asc-page-intro">
<!-- wp:paragraph {"className":"asc-eyebrow"} --><p class="asc-eyebrow">Worship</p><!-- /wp:paragraph -->
<!-- wp:heading {"level":1} --><h1 class="wp-block-heading">Sermons</h1><!-- /wp:heading -->
<!-- wp:paragraph --><p>Watch or listen to recent preaching at All Saints&#8217; Church.</p><!-- /wp:paragraph -->
</div><!-- /wp:group -->
<!-- wp:html -->[asc_sermon_archive]<!-- /wp:html -->
</main><!-- /wp:group -->' . $footer,
		) );
		register_block_template( 'asc-digital-ministry//page-landing', array(
			'title'       => __( 'Landing Page (full width, no title)', 'asc-digital-ministry' ),
			'description' => __( 'For pages built from full-width sections, like the homepage.', 'asc-digital-ministry' ),
			'post_types'  => array( 'page' ),
			'content'     => $header . '
<!-- wp:group {"tagName":"main","className":"asc-landing","layout":{"type":"default"}} -->
<main class="wp-block-group asc-landing"><!-- wp:post-content {"layout":{"type":"default"}} /--></main>
<!-- /wp:group -->' . $footer,
		) );
		register_block_template( 'asc-digital-ministry//single-sermon', array(
			'title'       => __( 'Single Sermon', 'asc-digital-ministry' ),
			'description' => __( 'Sermon detail: media first, then notes.', 'asc-digital-ministry' ),
			'content'     => $header . '
<!-- wp:group {"tagName":"main","className":"asc-page asc-sermon-single","layout":{"type":"constrained"}} -->
<main class="wp-block-group asc-page asc-sermon-single">
<!-- wp:paragraph {"className":"asc-eyebrow"} --><p class="asc-eyebrow"><a href="/sermons/">Sermons</a></p><!-- /wp:paragraph -->
<!-- wp:post-title {"level":1} /-->
<!-- wp:post-content {"layout":{"type":"constrained"}} /-->
</main><!-- /wp:group -->' . $footer,
		) );

		// News (the posts page) and category archives: cards with an excerpt, not every post in full.
		$intro = array(
			'asc-news'         => '<!-- wp:paragraph {"className":"asc-eyebrow"} --><p class="asc-eyebrow">News</p><!-- /wp:paragraph -->
<!-- wp:heading {"level":1} --><h1 class="wp-block-heading">News &amp; Announcements</h1><!-- /wp:heading -->',
			'asc-news-archive' => '<!-- wp:paragraph {"className":"asc-eyebrow"} --><p class="asc-eyebrow">News</p><!-- /wp:paragraph -->
<!-- wp:query-title {"type":"archive","showPrefix":false} /-->',
		);
		foreach ( $intro as $slug => $heading ) {
			register_block_template( 'asc-digital-ministry//' . $slug, array(
				'title'       => 'asc-news' === $slug ? __( 'News', 'asc-digital-ministry' ) : __( 'News Archive', 'asc-digital-ministry' ),
				'description' => __( 'Posts as cards with a short excerpt.', 'asc-digital-ministry' ),
				'content'     => $header . '
<!-- wp:group {"tagName":"main","className":"asc-page asc-news-page","layout":{"type":"constrained","wideSize":"var(--asc-content-wide)"}} -->
<main class="wp-block-group asc-page asc-news-page">
<!-- wp:group {"className":"asc-page-intro","layout":{"type":"constrained"}} --><div class="wp-block-group asc-page-intro">
' . $heading . '
</div><!-- /wp:group -->
<!-- wp:query {"queryId":1,"query":{"inherit":true},"align":"wide","className":"asc-post-list"} -->
<div class="wp-block-query alignwide asc-post-list">
<!-- wp:post-template {"layout":{"type":"grid","columnCount":3}} -->
<!-- wp:group {"className":"asc-post-card","layout":{"type":"default"}} --><div class="wp-block-group asc-post-card">
<!-- wp:post-date {"className":"asc-post-card__date"} /-->
<!-- wp:post-title {"level":2,"isLink":true,"className":"asc-post-card__title"} /-->
<!-- wp:post-excerpt {"moreText":"Read more","excerptLength":28} /-->
</div><!-- /wp:group -->
<!-- /wp:post-template -->
<!-- wp:query-pagination {"layout":{"type":"flex","justifyContent":"center"}} -->
<!-- wp:query-pagination-previous /--><!-- wp:query-pagination-numbers /--><!-- wp:query-pagination-next /-->
<!-- /wp:query-pagination -->
<!-- wp:query-no-results --><!-- wp:paragraph --><p>No news yet.</p><!-- /wp:paragraph --><!-- /wp:query-no-results -->
</div><!-- /wp:query -->
</main><!-- /wp:group -->' . $footer,
			) );
		}
	}

	/** Classic themes (Avada): use the plugin's PHP templates unless the theme provides its own. */
	public static function classic_templates( string $template ): string {
		if ( wp_is_block_theme() ) {
			return $template;
		}
		if ( is_post_type_archive( self::POST_TYPE ) && ! locate_template( 'archive-sermon.php' ) ) {
			return ASC_DM_DIR . 'templates/archive-sermon.php';
		}
		return $template;
	}
}
