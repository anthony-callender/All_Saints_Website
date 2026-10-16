<?php
namespace ASC_DM;

defined( 'ABSPATH' ) || exit;

/**
 * WP-CLI helpers.
 *
 *   wp asc kb reindex [--force]
 *   wp asc kb search "What time is Sunday worship?"
 *   wp asc kb status
 */
final class CLI {

	/**
	 * Reindex all published Church Knowledge entries.
	 *
	 * [--force]
	 * : Re-embed even when content is unchanged.
	 */
	public function reindex( $args, $assoc ): void {
		Embeddings::install_table();
		$result = Embeddings::reindex_all( ! empty( $assoc['force'] ) );
		foreach ( $result['errors'] as $error ) {
			\WP_CLI::warning( $error );
		}
		\WP_CLI::success( sprintf( 'Reindexed %d entries, %d passages written (provider %s).', $result['posts'], $result['chunks'], Embeddings::provider() ) );
	}

	/**
	 * Show retrieval results for a question.
	 *
	 * <query>
	 * : The question.
	 */
	public function search( $args ): void {
		$hits = Embeddings::search( (string) $args[0], 5 );
		if ( is_wp_error( $hits ) ) {
			\WP_CLI::error( $hits->get_error_message() );
		}
		if ( ! $hits ) {
			\WP_CLI::log( sprintf( 'No passages above threshold %.2f.', Embeddings::threshold() ) );
			return;
		}
		\WP_CLI\Utils\format_items( 'table', array_map( static fn( $h ) => array(
			'score'   => $h['score'],
			'title'   => $h['title'],
			'excerpt' => mb_substr( preg_replace( '/\s+/', ' ', $h['content'] ), 0, 80 ),
		), $hits ), array( 'score', 'title', 'excerpt' ) );
	}

	/** Index status. */
	public function status(): void {
		\WP_CLI::log( 'Provider:   ' . Embeddings::provider() );
		\WP_CLI::log( 'Threshold:  ' . Embeddings::threshold() );
		\WP_CLI::log( 'Entries:    ' . (int) wp_count_posts( KB::POST_TYPE )->publish );
		\WP_CLI::log( 'Passages:   ' . Embeddings::chunk_count() );
		\WP_CLI::log( 'OpenAI key: ' . ( OpenAI::is_configured() ? 'configured' : 'not configured (offline mode)' ) );
	}
}

\WP_CLI::add_command( 'asc kb', CLI::class );
