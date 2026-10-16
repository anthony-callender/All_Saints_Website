<?php
/**
 * Integration tests that run inside the real WordPress install (no PHPUnit harness needed).
 *
 *   ddev wp eval-file wp-content/plugins/asc-digital-ministry/tests/run-tests.php
 *
 * Creates its own fixtures and removes them afterwards. Uses the offline
 * embedding provider unless OPENAI_API_KEY is set (no API credits by default).
 */

defined( 'ABSPATH' ) || exit;

use ASC_DM\Chat_API;
use ASC_DM\Embeddings;
use ASC_DM\Sermons;

$GLOBALS['asc_t'] = array( 'pass' => 0, 'fail' => array() );
$GLOBALS['asc_cleanup'] = array();

function t( string $name, bool $ok, string $detail = '' ): void {
	if ( $ok ) {
		++$GLOBALS['asc_t']['pass'];
		WP_CLI::log( "  ✔ $name" );
	} else {
		$GLOBALS['asc_t']['fail'][] = $name;
		WP_CLI::log( "  ✘ $name" . ( $detail ? " — $detail" : '' ) );
	}
}

function rest( string $method, string $route, array $params = array(), array $query = array() ): WP_REST_Response {
	$req = new WP_REST_Request( $method, $route );
	foreach ( $query as $k => $v ) {
		$req->set_query_params( $query );
	}
	if ( $params ) {
		$req->set_header( 'Content-Type', 'application/json' );
		$req->set_body( wp_json_encode( $params ) );
	}
	return rest_ensure_response( rest_do_request( $req ) );
}

$editor = get_user_by( 'login', 'sermon-worker' );
$_SERVER['REMOTE_ADDR'] = '203.0.113.' . wp_rand( 1, 250 ); // unique per run for rate-limit tests

WP_CLI::log( 'Plugin & registration' );
t( 'plugin is active', is_plugin_active( 'asc-digital-ministry/asc-digital-ministry.php' ) );
$sermon = get_post_type_object( 'sermon' );
t( 'sermon CPT is public, archived, in REST, slug "sermons"', $sermon && $sermon->public && $sermon->has_archive && $sermon->show_in_rest && 'sermons' === $sermon->rewrite['slug'] );
t( 'sermon supports title/editor/excerpt/thumbnail/revisions/author', $sermon && ! array_diff( array( 'title', 'editor', 'excerpt', 'thumbnail', 'revisions', 'author' ), array_keys( get_all_post_type_supports( 'sermon' ) ) ) );
$kb = get_post_type_object( 'church_kb' );
t( 'church_kb CPT is private but editable in admin', $kb && ! $kb->public && $kb->show_ui && 'Church Knowledge' === $kb->labels->name );
$registered = get_registered_meta_keys( 'post', 'sermon' );
t( 'all sermon meta registered for REST', ! array_diff( array_keys( Sermons::META ), array_keys( array_filter( $registered, static fn( $m ) => ! empty( $m['show_in_rest'] ) ) ) ) );
t( 'KB meta registered', isset( get_registered_meta_keys( 'post', 'church_kb' )['asc_kb_source_url'], get_registered_meta_keys( 'post', 'church_kb' )['asc_kb_last_verified'] ) );
global $wpdb;
t( 'chunks table exists', (bool) $wpdb->get_var( $wpdb->prepare( 'SHOW TABLES LIKE %s', Embeddings::table() ) ) );
$routes = rest_get_server()->get_routes();
t( 'REST routes exist', isset( $routes['/asc/v1/chat'], $routes['/asc/v1/sermons/exists'], $routes['/wp/v2/sermons'] ) );

WP_CLI::log( 'Chunking & retrieval helpers' );
$para   = str_repeat( 'The nursery is open during both services and the Sunday School hour. ', 6 );
$chunks = Embeddings::chunk( implode( "\n\n", array_fill( 0, 8, $para ) ) );
t( 'long text splits into several chunks', count( $chunks ) > 3, (string) count( $chunks ) );
t( 'chunks respect the max size', max( array_map( 'mb_strlen', $chunks ) ) <= Embeddings::CHUNK_MAX + Embeddings::CHUNK_OVERLAP + 10 );
t( 'consecutive chunks overlap', str_starts_with( $chunks[1], '…' ) );
t( 'empty text yields no chunks', array() === Embeddings::chunk( "  \n " ) );
t( 'cosine of identical vectors is 1', abs( Embeddings::cosine( array( 1, 2, 3 ), array( 1, 2, 3 ) ) - 1 ) < 1e-9 );
t( 'cosine of orthogonal vectors is 0', abs( Embeddings::cosine( array( 1, 0 ), array( 0, 1 ) ) ) < 1e-9 );
$v = Embeddings::local_vector( 'Sunday worship times' );
t( 'local vectors are unit length', abs( sqrt( array_sum( array_map( static fn( $x ) => $x * $x, $v ) ) ) - 1 ) < 1e-6 );

WP_CLI::log( 'Church Knowledge indexing' );
$kb_id = wp_insert_post( array(
	'post_type'    => 'church_kb',
	'post_status'  => 'publish',
	'post_title'   => 'Test: Zephyr choir rehearsal',
	'post_content' => 'The Zephyr choir rehearses on Thursdays at 7 p.m. in the Zephyr room.',
	'meta_input'   => array( 'asc_kb_source_url' => home_url( '/test/' ) ),
) );
$GLOBALS['asc_cleanup'][] = $kb_id;
t( 'publishing a KB entry indexes it', Embeddings::chunk_count( $kb_id ) >= 1 );
$hash_before = $wpdb->get_var( $wpdb->prepare( 'SELECT content_hash FROM ' . Embeddings::table() . ' WHERE kb_post_id=%d', $kb_id ) );
t( 'unchanged content is not re-embedded', 0 === Embeddings::index_post( $kb_id ) );
wp_update_post( array( 'ID' => $kb_id, 'post_content' => 'The Zephyr choir now rehearses on Wednesdays at 6 p.m.' ) );
$hash_after = $wpdb->get_var( $wpdb->prepare( 'SELECT content_hash FROM ' . Embeddings::table() . ' WHERE kb_post_id=%d', $kb_id ) );
t( 'editing content replaces stale chunks', $hash_before !== $hash_after );
$hits = Embeddings::search( 'When does the Zephyr choir rehearse?' );
t( 'search finds the relevant entry first', ! is_wp_error( $hits ) && $hits && $kb_id === $hits[0]['post_id'] );
$none = Embeddings::search( 'quantum chromodynamics lattice gauge' );
t( 'irrelevant query is below threshold', ! is_wp_error( $none ) && ! $none );
wp_update_post( array( 'ID' => $kb_id, 'post_status' => 'draft' ) );
t( 'unpublishing removes chunks', 0 === Embeddings::chunk_count( $kb_id ) );
wp_update_post( array( 'ID' => $kb_id, 'post_status' => 'publish' ) );

WP_CLI::log( 'Chat API' );
t( 'empty message rejected', is_wp_error( Chat_API::validate_message( '   ' ) ) );
t( 'over-long message rejected', is_wp_error( Chat_API::validate_message( str_repeat( 'a', Chat_API::MAX_MESSAGE + 1 ) ) ) );
t( 'system-role history rejected', is_wp_error( Chat_API::validate_history( array( array( 'role' => 'system', 'content' => 'x' ) ) ) ) );
t( 'oversized history rejected', is_wp_error( Chat_API::validate_history( array_fill( 0, Chat_API::MAX_HISTORY + 1, array( 'role' => 'user', 'content' => 'x' ) ) ) ) );
t( 'history trimmed to model window', count( Chat_API::clean_history( array_fill( 0, 30, array( 'role' => 'user', 'content' => str_repeat( 'b', 5000 ) ) ) ) ) === Chat_API::MODEL_HISTORY );
t( 'model sees the published church knowledge', str_contains( Chat_API::knowledge(), 'Zephyr choir' ) );
$msgs = Chat_API::messages( 'hi', array( array( 'role' => 'assistant', 'content' => 'Hello!' ) ) );
t( 'messages = system prompt + knowledge + history + visitor message', 'system' === $msgs[0]['role'] && str_contains( $msgs[1]['content'], 'Zephyr choir' ) && 'Hello!' === $msgs[2]['content'] && 'hi' === end( $msgs )['content'] );
wp_set_current_user( 0 );
if ( ! ASC_DM\OpenAI::is_configured() ) {
	$res = rest( 'POST', '/asc/v1/chat', array( 'message' => 'hello' ) );
	t( 'without an API key the assistant says it is unavailable (503)', 503 === $res->get_status() );
}
$res = rest( 'POST', '/asc/v1/chat', array( 'message' => '' ) );
t( 'REST rejects empty message with 400', 400 === $res->get_status() );
$codes = array();
for ( $i = 0; $i < 20; $i++ ) {
	$codes[] = rest( 'POST', '/asc/v1/chat', array( 'message' => 'Zephyr choir?' ) )->get_status();
}
t( 'rate limit returns 429', in_array( 429, $codes, true ), implode( ',', $codes ) );

WP_CLI::log( 'Sermon REST permissions & idempotency' );
wp_set_current_user( 0 );
$res = rest( 'GET', '/asc/v1/sermons/exists', array(), array( 'youtube_video_id' => 'zzzzzzzzzzz' ) );
t( 'anonymous duplicate check is refused', 401 === $res->get_status() );
$res = rest( 'POST', '/wp/v2/sermons', array( 'title' => 'x' ) );
t( 'anonymous sermon create is refused', 401 === $res->get_status() );
wp_set_current_user( $editor->ID );
$res = rest( 'GET', '/asc/v1/sermons/exists', array(), array( 'youtube_video_id' => 'bad id' ) );
t( 'invalid video id rejected', 400 === $res->get_status() );
$create = array( 'title' => 'Test sermon', 'status' => 'draft', 'meta' => array( 'asc_youtube_video_id' => 'TESTvid0001', 'asc_scripture_references' => array( 'John 3:16' ), 'asc_transcript' => 'secret' ) );
$res    = rest( 'POST', '/wp/v2/sermons', $create );
$sid    = (int) ( $res->get_data()['id'] ?? 0 );
$GLOBALS['asc_cleanup'][] = $sid;
t( 'editor can create a sermon with meta', 201 === $res->get_status() && array( 'John 3:16' ) === get_post_meta( $sid, 'asc_scripture_references', true ) );
$res = rest( 'GET', '/asc/v1/sermons/exists', array(), array( 'youtube_video_id' => 'TESTvid0001' ) );
t( 'exists endpoint finds it', $res->get_data()['exists'] && $sid === $res->get_data()['post_id'] );
$res = rest( 'POST', '/wp/v2/sermons', $create );
t( 'duplicate video id is rejected with 409', 409 === $res->get_status() );
wp_update_post( array( 'ID' => $sid, 'post_status' => 'publish' ) );
wp_set_current_user( 0 );
$res = rest( 'GET', "/wp/v2/sermons/$sid" );
t( 'transcript hidden from public REST', 200 === $res->get_status() && ! array_key_exists( 'asc_transcript', $res->get_data()['meta'] ) );

// Cleanup
wp_set_current_user( 0 );
foreach ( $GLOBALS['asc_cleanup'] as $id ) {
	if ( $id ) {
		wp_delete_post( $id, true );
	}
}
delete_transient( 'asc_chat_' . substr( hash_hmac( 'sha256', $_SERVER['REMOTE_ADDR'], wp_salt( 'nonce' ) ), 0, 24 ) );

$fail = $GLOBALS['asc_t']['fail'];
if ( $fail ) {
	WP_CLI::error( sprintf( '%d passed, %d failed: %s', $GLOBALS['asc_t']['pass'], count( $fail ), implode( '; ', $fail ) ) );
}
WP_CLI::success( sprintf( '%d WordPress integration tests passed', $GLOBALS['asc_t']['pass'] ) );
