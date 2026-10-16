<?php
/**
 * Seed the local site with migrated All Saints' content. Idempotent (upserts).
 *
 *   ddev wp eval-file scripts/seed.php
 *
 * Content lives in /seed as data (block markup + JSON) — this file only loads it.
 * Images come from migration-assets/images (downloaded on demand from the live
 * site using migration/source/manifests/selected-photos.json).
 */

defined( 'ABSPATH' ) || exit;

$root = dirname( __DIR__ );
$seed = $root . '/seed';

function asc_log( string $msg ): void {
	WP_CLI::log( $msg );
}

/** Upsert a post by post_type + post_name (and parent for pages). */
function asc_upsert( array $postarr ): int {
	$existing = get_posts( array(
		'post_type'      => $postarr['post_type'],
		'name'           => $postarr['post_name'],
		'post_parent'    => $postarr['post_parent'] ?? 0,
		'post_status'    => 'any',
		'posts_per_page' => 1,
		'fields'         => 'ids',
	) );
	if ( $existing ) {
		$postarr['ID'] = $existing[0];
	}
	$id = wp_insert_post( wp_slash( $postarr ), true );
	if ( is_wp_error( $id ) ) {
		WP_CLI::error( $postarr['post_name'] . ': ' . $id->get_error_message() );
	}
	return (int) $id;
}

// ---------------------------------------------------------------------------
// 1. Media (real parish photography + logo)
// ---------------------------------------------------------------------------
require_once ABSPATH . 'wp-admin/includes/media.php';
require_once ABSPATH . 'wp-admin/includes/file.php';
require_once ABSPATH . 'wp-admin/includes/image.php';

$assets   = $root . '/migration-assets/images';
$manifest = json_decode( (string) file_get_contents( $root . '/migration/source/manifests/selected-photos.json' ), true );
$manifest[] = array( 'file' => 'asc-logo.png', 'source' => 'https://images.squarespace-cdn.com/content/v1/5ce2b6cb8a4ea10001630ef1/b666ddf5-b4e2-4847-923d-ca92ac11e36f/ASC+Simple+Logo+%28No+Background%29.png' );
wp_mkdir_p( $assets );

$media = array();
foreach ( $manifest as $item ) {
	$name = pathinfo( $item['file'], PATHINFO_FILENAME );
	$found = get_posts( array( 'post_type' => 'attachment', 'meta_key' => '_asc_seed_key', 'meta_value' => $name, 'fields' => 'ids', 'posts_per_page' => 1, 'post_status' => 'any' ) );
	if ( $found ) {
		$media[ $name ] = (int) $found[0];
		continue;
	}
	$path = $assets . '/' . $item['file'];
	if ( ! file_exists( $path ) ) {
		$res = wp_remote_get( $item['source'] . '?format=2500w', array( 'timeout' => 60 ) );
		if ( is_wp_error( $res ) ) {
			WP_CLI::warning( "Could not download {$item['file']}" );
			continue;
		}
		file_put_contents( $path, wp_remote_retrieve_body( $res ) );
	}
	$tmp = wp_tempnam( $item['file'] );
	copy( $path, $tmp );
	$id = media_handle_sideload( array( 'name' => $item['file'], 'tmp_name' => $tmp ), 0, ucwords( str_replace( '-', ' ', $name ) ) );
	if ( is_wp_error( $id ) ) {
		WP_CLI::warning( $item['file'] . ': ' . $id->get_error_message() );
		continue;
	}
	update_post_meta( $id, '_asc_seed_key', $name );
	update_post_meta( $id, '_asc_source_url', $item['source'] );
	$media[ $name ] = (int) $id;
}
asc_log( 'Media: ' . count( $media ) );

if ( isset( $media['asc-logo'] ) ) {
	update_post_meta( $media['asc-logo'], '_wp_attachment_image_alt', "All Saints' Church" );
	update_option( 'site_logo', $media['asc-logo'] );
	set_theme_mod( 'custom_logo', $media['asc-logo'] );
}

// ---------------------------------------------------------------------------
// 2. Synced patterns (edit once, update everywhere)
// ---------------------------------------------------------------------------
$blocks = array();
foreach ( array( 'service-times' => 'Service Times & Location', 'prayer-cta' => 'Prayer Invitation' ) as $slug => $title ) {
	$markup = (string) file_get_contents( WP_PLUGIN_DIR . "/asc-digital-ministry/patterns/{$slug}.html" );
	$markup = preg_replace( '/^<!--\s*Title:.*?-->\s*/', '', $markup );
	$blocks[ $slug ] = asc_upsert( array(
		'post_type'    => 'wp_block',
		'post_name'    => 'asc-' . $slug,
		'post_title'   => $title,
		'post_status'  => 'publish',
		'post_content' => $markup,
	) );
}

// ---------------------------------------------------------------------------
// 3. Navigation
// ---------------------------------------------------------------------------
$nav_id = asc_upsert( array(
	'post_type'    => 'wp_navigation',
	'post_name'    => 'primary-navigation',
	'post_title'   => 'Primary Navigation',
	'post_status'  => 'publish',
	'post_content' => (string) file_get_contents( $seed . '/navigation.html' ),
) );

// ---------------------------------------------------------------------------
// 4. Pages
// ---------------------------------------------------------------------------
$pages = array();
$fill  = static function ( string $content ) use ( &$media, &$blocks, &$pages ): string {
	return preg_replace_callback( '/\{\{(img|imgid|block|page):([a-z0-9-]+)\}\}/', static function ( $m ) use ( &$media, &$blocks, &$pages ) {
		switch ( $m[1] ) {
			case 'img':
				return isset( $media[ $m[2] ] ) ? (string) wp_get_attachment_image_url( $media[ $m[2] ], 'full' ) : '';
			case 'imgid':
				return (string) ( $media[ $m[2] ] ?? 0 );
			case 'block':
				return (string) ( $blocks[ $m[2] ] ?? 0 );
			case 'page':
				return (string) ( $pages[ $m[2] ] ?? 0 );
		}
		return '';
	}, $content );
};

$upsert_page = static function ( string $path, string $title, string $content, array $meta = array(), string $template = '' ) use ( &$pages, $fill ): int {
	$parts  = explode( '/', $path );
	$slug   = array_pop( $parts );
	$parent = $parts ? ( $pages[ implode( '/', $parts ) ] ?? 0 ) : 0;
	$pages[ $path ] = 0; // reserve so {{page:self}} resolves after insert
	$id = asc_upsert( array(
		'post_type'    => 'page',
		'post_name'    => $slug,
		'post_title'   => $title,
		'post_parent'  => $parent,
		'post_status'  => 'publish',
		'post_content' => '',
	) );
	$pages[ $path ] = $id;
	wp_update_post( wp_slash( array( 'ID' => $id, 'post_content' => $fill( $content ) ) ) );
	foreach ( $meta as $k => $v ) {
		update_post_meta( $id, $k, $v );
	}
	if ( $template ) {
		update_post_meta( $id, '_wp_page_template', $template );
	}
	return $id;
};

$read_page = static function ( string $file ): array {
	$raw = (string) file_get_contents( $file );
	preg_match( '/<!-- title: (.+?) -->/', $raw, $t );
	preg_match( '/<!-- path: (.+?) -->/', $raw, $p );
	$content = trim( preg_replace( '/^(<!-- (title|path): .+? -->\s*)+/', '', $raw ) );
	return array( $p[1], $t[1], $content );
};

// Hubs first so children can find their parents.
foreach ( array( 'about', 'worship', 'ministries' ) as $hub ) {
	list( $path, $title, $content ) = $read_page( "$seed/pages/$hub.html" );
	$upsert_page( $path, $title, $content );
}
foreach ( glob( "$seed/pages/*.html" ) as $file ) {
	if ( in_array( basename( $file, '.html' ), array( 'about', 'worship', 'ministries' ), true ) ) {
		continue;
	}
	list( $path, $title, $content ) = $read_page( $file );
	$upsert_page( $path, $title, $content, array(), 'home' === $path ? 'page-landing' : '' );
}
$migrated = json_decode( (string) file_get_contents( "$seed/migrated-pages.json" ), true );
foreach ( $migrated as $page ) {
	$content = $page['content'];
	if ( 'prayer' === $page['path'] ) {
		// The Squarespace prayer form is not migrated (needs a WordPress form plugin).
		$content .= "\n\n<!-- wp:paragraph -->\n<p>To share a prayer request, please call the church office at <a href=\"tel:+17036700093\">703-670-0093</a>.</p>\n<!-- /wp:paragraph -->";
	}
	$upsert_page( $page['path'], $page['title'], $content, array( '_asc_source_url' => $page['source_url'] ) );
}
asc_log( 'Pages: ' . count( $pages ) );

update_option( 'show_on_front', 'page' );
update_option( 'page_on_front', $pages['home'] );
update_option( 'page_for_posts', $pages['news'] );

// ---------------------------------------------------------------------------
// 5. Header/footer template parts (Site Editor → Patterns → Template Parts)
// ---------------------------------------------------------------------------
$theme = get_stylesheet();
foreach ( array( 'header', 'footer' ) as $area ) {
	$content = str_replace( '{{nav:primary}}', (string) $nav_id, (string) file_get_contents( "$seed/template-parts/$area.html" ) );
	$id      = asc_upsert( array(
		'post_type'    => 'wp_template_part',
		'post_name'    => $area,
		'post_title'   => ucfirst( $area ),
		'post_status'  => 'publish',
		'post_content' => $content,
	) );
	wp_set_object_terms( $id, $theme, 'wp_theme' );
	wp_set_object_terms( $id, $area, 'wp_template_part_area' );
}

// ---------------------------------------------------------------------------
// 6. Global Styles = the design tokens (Avada Global Options equivalent)
// ---------------------------------------------------------------------------
if ( wp_is_block_theme() ) {
	$styles = array(
		'version'                     => 3,
		'isGlobalStylesUserThemeJSON' => true,
		'settings'                    => array(
			'layout'     => array( 'contentSize' => '46rem', 'wideSize' => '86rem' ),
			'color'      => array( 'palette' => array( 'custom' => array(
				array( 'slug' => 'asc-parchment', 'name' => 'Parchment', 'color' => '#f8f5ee' ),
				array( 'slug' => 'asc-ink', 'name' => 'Ink', 'color' => '#1b2433' ),
				array( 'slug' => 'asc-red', 'name' => 'Cross Red', 'color' => '#b3141e' ),
				array( 'slug' => 'asc-blue', 'name' => 'Cross Blue', 'color' => '#00539a' ),
				array( 'slug' => 'asc-navy', 'name' => 'Parish Navy', 'color' => '#0b2a60' ),
				array( 'slug' => 'asc-amber', 'name' => 'Amber', 'color' => '#b8741f' ),
				array( 'slug' => 'asc-stone', 'name' => 'Stone', 'color' => '#efe9dd' ),
			) ) ),
			'typography' => array( 'fontFamilies' => array( 'custom' => array(
				array( 'slug' => 'asc-serif', 'name' => 'EB Garamond (headings)', 'fontFamily' => '"EB Garamond", Garamond, serif' ),
				array( 'slug' => 'asc-sans', 'name' => 'Source Sans 3 (body)', 'fontFamily' => '"Source Sans 3", system-ui, sans-serif' ),
			) ) ),
		),
		'styles'                      => array(
			'color'      => array( 'background' => 'var(--wp--preset--color--asc-parchment)', 'text' => 'var(--wp--preset--color--asc-ink)' ),
			'typography' => array( 'fontFamily' => 'var(--wp--preset--font-family--asc-sans)', 'fontSize' => 'var(--asc-text-base)', 'lineHeight' => '1.65', 'letterSpacing' => '0' ),
			'spacing'    => array( 'blockGap' => '1.25rem' ),
			'elements'   => array(
				'heading' => array(
					'typography' => array( 'fontFamily' => 'var(--wp--preset--font-family--asc-serif)', 'fontWeight' => '500', 'lineHeight' => '1.12', 'letterSpacing' => '-0.01em' ),
					'color'      => array( 'text' => 'var(--wp--preset--color--asc-navy)' ),
				),
				'h1'      => array( 'typography' => array( 'fontSize' => 'var(--asc-text-h1)' ) ),
				'h2'      => array( 'typography' => array( 'fontSize' => 'var(--asc-text-h2)' ) ),
				'h3'      => array( 'typography' => array( 'fontSize' => 'var(--asc-text-h3)' ) ),
				'link'    => array( 'color' => array( 'text' => 'var(--wp--preset--color--asc-blue)' ), ':hover' => array( 'color' => array( 'text' => 'var(--wp--preset--color--asc-red)' ) ) ),
				'button'  => array(
					'color'      => array( 'background' => 'var(--wp--preset--color--asc-red)', 'text' => '#ffffff' ),
					'typography' => array( 'fontFamily' => 'var(--wp--preset--font-family--asc-sans)', 'fontWeight' => '600' ),
					'border'     => array( 'radius' => '0.375rem' ),
				),
			),
		),
	);
	// Target the theme's own user-styles post (wp-global-styles-{theme}); the resolver
	// helper can create an unlinked duplicate when called from WP-CLI.
	$gs_id = asc_upsert( array(
		'post_type'    => 'wp_global_styles',
		'post_name'    => 'wp-global-styles-' . urlencode( $theme ),
		'post_title'   => 'Custom Styles',
		'post_status'  => 'publish',
		'post_content' => wp_json_encode( $styles ),
	) );
	wp_set_object_terms( $gs_id, $theme, 'wp_theme' );
	foreach ( get_posts( array( 'post_type' => 'wp_global_styles', 'post_status' => 'any', 'numberposts' => -1, 'exclude' => array( $gs_id ) ) ) as $stray ) {
		if ( ! wp_get_object_terms( $stray->ID, 'wp_theme' ) ) {
			wp_delete_post( $stray->ID, true );
		}
	}
	asc_log( 'Global styles applied to ' . $theme );
}

// ---------------------------------------------------------------------------
// 7. Sermons (full live archive) — Sermon CPT
// ---------------------------------------------------------------------------
$sermons = json_decode( (string) file_get_contents( "$seed/sermons.json" ), true );
foreach ( $sermons as $s ) {
	$id = asc_upsert( array(
		'post_type'    => 'sermon',
		'post_name'    => $s['slug'],
		'post_title'   => $s['title'],
		'post_status'  => 'publish',
		'post_date'    => $s['sermon_date'] . ' 11:00:00',
		'post_content' => $s['content'],
	) );
	$meta = array(
		'asc_sermon_date'          => $s['sermon_date'],
		'asc_preacher'             => $s['preacher'],
		'asc_scripture_references' => $s['scripture_references'],
		'asc_series'               => $s['series'],
		'asc_audio_url'            => $s['audio_url'],
		'asc_source_url'           => $s['source_url'],
		'asc_pipeline_version'     => 'migration-2026-10',
	);
	foreach ( $meta as $k => $v ) {
		update_post_meta( $id, $k, $v );
	}
}
asc_log( 'Sermons: ' . count( $sermons ) );

// ---------------------------------------------------------------------------
// 8. News (current announcements) — Posts
// ---------------------------------------------------------------------------
$cat = term_exists( 'Announcements', 'category' ) ?: wp_insert_term( 'Announcements', 'category' );
foreach ( json_decode( (string) file_get_contents( "$seed/news.json" ), true ) as $n ) {
	$id = asc_upsert( array(
		'post_type'     => 'post',
		'post_name'     => $n['slug'],
		'post_title'    => $n['title'],
		'post_status'   => 'publish',
		'post_date'     => $n['date'] ? get_date_from_gmt( gmdate( 'Y-m-d H:i:s', strtotime( $n['date'] ) ) ) : current_time( 'mysql' ),
		'post_content'  => $n['content'],
		'post_category' => array( (int) $cat['term_id'] ),
	) );
	update_post_meta( $id, '_asc_source_url', $n['source_url'] );
}
foreach ( array( 'hello-world' => 'post', 'sample-page' => 'page' ) as $slug => $type ) {
	$p = get_page_by_path( $slug, OBJECT, $type );
	if ( $p ) {
		wp_delete_post( $p->ID, true );
	}
}

// ---------------------------------------------------------------------------
// 9. Church Knowledge + index
// ---------------------------------------------------------------------------
$kb = json_decode( (string) file_get_contents( "$seed/church-knowledge.json" ), true );
foreach ( $kb['entries'] as $entry ) {
	$id = asc_upsert( array(
		'post_type'    => 'church_kb',
		'post_name'    => sanitize_title( $entry['title'] ),
		'post_title'   => $entry['title'],
		'post_status'  => 'publish',
		'post_content' => $entry['body'],
		// meta_input is saved before the save_post hook indexes the entry.
		'meta_input'   => array(
			'asc_kb_source_url'    => home_url( $entry['source'] ),
			'asc_kb_last_verified' => $kb['last_verified'],
			'_asc_legacy_source'   => $entry['legacy'],
		),
	) );
}
$result = ASC_DM\Embeddings::reindex_all(); // unchanged entries are skipped by content hash
asc_log( sprintf( 'Church Knowledge: %d entries, %d passages (%s)', $result['posts'], $result['chunks'], ASC_DM\Embeddings::provider() ) );
foreach ( $result['errors'] as $e ) {
	WP_CLI::warning( $e );
}

flush_rewrite_rules();
WP_CLI::success( 'Seed complete: ' . home_url( '/' ) );
