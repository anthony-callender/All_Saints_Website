<?php
namespace ASC_DM;

defined( 'ABSPATH' ) || exit;

/**
 * REST support for the sermon worker.
 *
 *   GET /wp-json/asc/v1/sermons/exists?youtube_video_id=XXXXXXXXXXX
 *
 * Creation itself uses the core endpoint (POST /wp-json/wp/v2/sermons with meta),
 * so editors get ordinary revisions, permissions, and Gutenberg content.
 * A pre-insert guard rejects a second sermon for the same YouTube video (409),
 * making publishing idempotent even if two workers race.
 */
final class Sermon_API {

	const NS = 'asc/v1';

	public static function init(): void {
		add_action( 'rest_api_init', array( __CLASS__, 'routes' ) );
		add_filter( 'rest_pre_insert_' . Sermons::POST_TYPE, array( __CLASS__, 'guard_duplicate' ), 10, 2 );
	}

	public static function routes(): void {
		register_rest_route( self::NS, '/sermons/exists', array(
			'methods'             => \WP_REST_Server::READABLE,
			'callback'            => array( __CLASS__, 'exists' ),
			// Drafts are not public; only authenticated editors (the worker) may ask.
			'permission_callback' => static fn() => current_user_can( 'edit_posts' ),
			'args'                => array(
				'youtube_video_id' => array(
					'required'          => true,
					'type'              => 'string',
					'validate_callback' => static fn( $v ) => Sermons::is_valid_video_id( (string) $v ),
				),
			),
		) );
	}

	public static function exists( \WP_REST_Request $request ): \WP_REST_Response {
		$post_id = Sermons::find_by_video_id( (string) $request['youtube_video_id'] );
		return new \WP_REST_Response( array(
			'exists'  => (bool) $post_id,
			'post_id' => $post_id ?: null,
			'status'  => $post_id ? get_post_status( $post_id ) : null,
			'link'    => $post_id ? get_permalink( $post_id ) : null,
		) );
	}

	/**
	 * @param \stdClass|\WP_Error $prepared
	 * @return \stdClass|\WP_Error
	 */
	public static function guard_duplicate( $prepared, \WP_REST_Request $request ) {
		if ( is_wp_error( $prepared ) || ! empty( $prepared->ID ) ) {
			return $prepared; // Updates are fine.
		}
		$video_id = (string) ( $request['meta']['asc_youtube_video_id'] ?? '' );
		if ( '' === $video_id ) {
			return $prepared;
		}
		if ( ! Sermons::is_valid_video_id( $video_id ) ) {
			return new \WP_Error( 'asc_invalid_video_id', 'Invalid YouTube video ID.', array( 'status' => 400 ) );
		}
		$existing = Sermons::find_by_video_id( $video_id );
		if ( $existing ) {
			return new \WP_Error(
				'asc_duplicate_sermon',
				'A sermon for this YouTube video already exists.',
				array( 'status' => 409, 'post_id' => $existing )
			);
		}
		return $prepared;
	}
}
