<?php
namespace ASC_DM;

defined( 'ABSPATH' ) || exit;

/**
 * Church Knowledge chunking, embedding storage, and retrieval.
 *
 * Storage: one table ({prefix}asc_kb_chunks) with JSON vectors. Retrieval is a
 * brute-force cosine similarity in PHP, which is appropriate for a parish-sized
 * corpus (tens to low hundreds of passages). No external vector database.
 *
 * Providers:
 *   openai:<model>  when OPENAI_API_KEY is configured (production).
 *   local:hash-512  deterministic hashed bag-of-words fallback for offline
 *                   development and automated tests (no API credits).
 * Each row records its provider so vectors from different models never mix.
 */
final class Embeddings {

	const CHUNK_TARGET   = 700;  // characters
	const CHUNK_MAX      = 1000;
	const CHUNK_OVERLAP  = 150;
	const LOCAL_DIMS     = 512;
	const DB_VERSION     = '1';

	public static function table(): string {
		global $wpdb;
		return $wpdb->prefix . 'asc_kb_chunks';
	}

	public static function install_table(): void {
		global $wpdb;
		require_once ABSPATH . 'wp-admin/includes/upgrade.php';
		$table   = self::table();
		$charset = $wpdb->get_charset_collate();
		dbDelta( "CREATE TABLE {$table} (
			id bigint(20) unsigned NOT NULL AUTO_INCREMENT,
			kb_post_id bigint(20) unsigned NOT NULL,
			chunk_index int(10) unsigned NOT NULL,
			content text NOT NULL,
			content_hash char(64) NOT NULL,
			embedding longtext NOT NULL,
			model varchar(100) NOT NULL,
			source_url varchar(2048) NOT NULL DEFAULT '',
			updated_at datetime NOT NULL,
			PRIMARY KEY  (id),
			KEY kb_post_id (kb_post_id),
			KEY model (model)
		) {$charset};" );
		update_option( 'asc_dm_db_version', self::DB_VERSION );
	}

	public static function provider(): string {
		return OpenAI::is_configured() ? 'openai:' . OpenAI::embedding_model() : 'local:hash-' . self::LOCAL_DIMS;
	}

	/** Similarity floor below which we treat retrieval as "no relevant knowledge". */
	public static function threshold(): float {
		$default = str_starts_with( self::provider(), 'openai:' ) ? '0.30' : '0.18';
		return (float) Plugin::config( 'ASC_KB_SIMILARITY_THRESHOLD', $default );
	}

	// ------------------------------------------------------------------
	// Chunking
	// ------------------------------------------------------------------

	/**
	 * Split text into ~CHUNK_TARGET-character passages on paragraph/sentence
	 * boundaries, carrying ~CHUNK_OVERLAP characters of trailing context forward.
	 *
	 * @return string[]
	 */
	public static function chunk( string $text ): array {
		$text = trim( preg_replace( "/\r\n?/", "\n", $text ) );
		if ( '' === $text ) {
			return array();
		}
		// Units: paragraphs, with over-long paragraphs split into sentences.
		$units = array();
		foreach ( preg_split( "/\n\s*\n/", $text ) as $para ) {
			$para = trim( preg_replace( '/[ \t]+/', ' ', $para ) );
			if ( '' === $para ) {
				continue;
			}
			if ( mb_strlen( $para ) <= self::CHUNK_MAX ) {
				$units[] = $para;
				continue;
			}
			foreach ( preg_split( '/(?<=[.!?])\s+/', $para ) as $sentence ) {
				$units = array_merge( $units, mb_str_split( $sentence, self::CHUNK_MAX ) );
			}
		}

		$chunks  = array();
		$current = '';
		foreach ( $units as $unit ) {
			$candidate = '' === $current ? $unit : $current . "\n\n" . $unit;
			if ( '' !== $current && mb_strlen( $candidate ) > self::CHUNK_TARGET ) {
				$chunks[] = $current;
				$tail     = self::tail( $current );
				$current  = '' === $tail ? $unit : $tail . "\n\n" . $unit;
			} else {
				$current = $candidate;
			}
		}
		if ( '' !== trim( $current ) ) {
			$chunks[] = $current;
		}
		return $chunks;
	}

	/** Last ~CHUNK_OVERLAP characters, starting at a word boundary. */
	private static function tail( string $text ): string {
		if ( mb_strlen( $text ) <= self::CHUNK_OVERLAP ) {
			return '';
		}
		$tail  = mb_substr( $text, -self::CHUNK_OVERLAP );
		$space = mb_strpos( $tail, ' ' );
		return false === $space ? $tail : '…' . trim( mb_substr( $tail, $space ) );
	}

	public static function plain_text( \WP_Post $post ): string {
		$html = apply_filters( 'asc_kb_raw_content', $post->post_content, $post );
		$html = preg_replace( '#</(p|li|h[1-6]|div|tr)>#i', "\n\n", $html );
		$text = html_entity_decode( wp_strip_all_tags( $html ), ENT_QUOTES, 'UTF-8' );
		return trim( preg_replace( "/\n{3,}/", "\n\n", $text ) );
	}

	// ------------------------------------------------------------------
	// Indexing
	// ------------------------------------------------------------------

	/** @return int|\WP_Error Number of chunks written (0 if unchanged). */
	public static function index_post( int $post_id, bool $force = false ) {
		global $wpdb;
		$post = get_post( $post_id );
		if ( ! $post || KB::POST_TYPE !== $post->post_type || 'publish' !== $post->post_status ) {
			self::delete_for_post( $post_id );
			return 0;
		}
		$provider = self::provider();
		$source   = (string) get_post_meta( $post_id, 'asc_kb_source_url', true );
		$body     = self::plain_text( $post );
		$hash     = hash( 'sha256', $provider . "\0" . $post->post_title . "\0" . $body . "\0" . $source );

		$existing = $wpdb->get_var( $wpdb->prepare( 'SELECT content_hash FROM ' . self::table() . ' WHERE kb_post_id = %d LIMIT 1', $post_id ) ); // phpcs:ignore WordPress.DB.PreparedSQL.NotPrepared
		if ( ! $force && $existing === $hash ) {
			return 0;
		}

		// Prefix each passage with its title so retrieval and the model both see context.
		$chunks = array_map(
			static fn( $c ) => $post->post_title . "\n" . $c,
			self::chunk( $body )
		);
		if ( ! $chunks ) {
			self::delete_for_post( $post_id );
			return 0;
		}
		$vectors = self::embed( $chunks );
		if ( is_wp_error( $vectors ) ) {
			return $vectors; // Keep the previous index rather than deleting it.
		}

		self::delete_for_post( $post_id );
		$now = current_time( 'mysql', true );
		foreach ( $chunks as $i => $content ) {
			$wpdb->insert( self::table(), array( // phpcs:ignore WordPress.DB.DirectDatabaseQuery
				'kb_post_id'   => $post_id,
				'chunk_index'  => $i,
				'content'      => $content,
				'content_hash' => $hash,
				'embedding'    => wp_json_encode( array_map( static fn( $f ) => round( $f, 6 ), $vectors[ $i ] ) ),
				'model'        => $provider,
				'source_url'   => $source,
				'updated_at'   => $now,
			) );
		}
		return count( $chunks );
	}

	/** @return array{posts:int, chunks:int, errors:string[]} */
	public static function reindex_all( bool $force = false ): array {
		global $wpdb;
		$ids    = get_posts( array( 'post_type' => KB::POST_TYPE, 'post_status' => 'publish', 'numberposts' => -1, 'fields' => 'ids' ) );
		$result = array( 'posts' => 0, 'chunks' => 0, 'errors' => array() );
		foreach ( $ids as $id ) {
			$count = self::index_post( (int) $id, $force );
			if ( is_wp_error( $count ) ) {
				$result['errors'][] = get_the_title( $id ) . ': ' . $count->get_error_message();
				update_post_meta( $id, '_asc_kb_index_error', $count->get_error_message() );
				continue;
			}
			delete_post_meta( $id, '_asc_kb_index_error' );
			++$result['posts'];
			$result['chunks'] += $count;
		}
		// Remove orphans (deleted/unpublished posts) and vectors from other providers.
		$keep = $ids ? implode( ',', array_map( 'intval', $ids ) ) : '0';
		$wpdb->query( 'DELETE FROM ' . self::table() . " WHERE kb_post_id NOT IN ({$keep})" ); // phpcs:ignore WordPress.DB
		$wpdb->query( $wpdb->prepare( 'DELETE FROM ' . self::table() . ' WHERE model <> %s', self::provider() ) ); // phpcs:ignore WordPress.DB
		return $result;
	}

	public static function delete_for_post( int $post_id ): void {
		global $wpdb;
		$wpdb->delete( self::table(), array( 'kb_post_id' => $post_id ), array( '%d' ) ); // phpcs:ignore WordPress.DB.DirectDatabaseQuery
	}

	public static function chunk_count( ?int $post_id = null ): int {
		global $wpdb;
		if ( null === $post_id ) {
			return (int) $wpdb->get_var( $wpdb->prepare( 'SELECT COUNT(*) FROM ' . self::table() . ' WHERE model = %s', self::provider() ) ); // phpcs:ignore WordPress.DB
		}
		return (int) $wpdb->get_var( $wpdb->prepare( 'SELECT COUNT(*) FROM ' . self::table() . ' WHERE kb_post_id = %d', $post_id ) ); // phpcs:ignore WordPress.DB
	}

	// ------------------------------------------------------------------
	// Embedding + retrieval
	// ------------------------------------------------------------------

	/**
	 * @param string[] $texts
	 * @return float[][]|\WP_Error
	 */
	public static function embed( array $texts ) {
		if ( str_starts_with( self::provider(), 'openai:' ) ) {
			return OpenAI::embed( $texts );
		}
		return array_map( array( __CLASS__, 'local_vector' ), $texts );
	}

	/** Deterministic, normalised hashed bag-of-words vector (offline fallback). */
	public static function local_vector( string $text ): array {
		static $stop = null;
		$stop ??= array_flip( explode( ' ', 'a an and are as at be by can do does for from has have how i if in is it its me my of on or our the their there this to us we what when where which who will with you your about all any am was were' ) );
		$vector = array_fill( 0, self::LOCAL_DIMS, 0.0 );
		preg_match_all( '/[a-z0-9]+/', strtolower( $text ), $m );
		foreach ( $m[0] as $word ) {
			if ( isset( $stop[ $word ] ) || strlen( $word ) < 2 ) {
				continue;
			}
			$word   = preg_replace( '/(ing|es|s)$/', '', $word ) ?: $word; // crude stemming
			$h      = crc32( $word );
			$vector[ $h % self::LOCAL_DIMS ] += ( $h & 1 ) ? 1.0 : -1.0;
		}
		$norm = sqrt( array_sum( array_map( static fn( $v ) => $v * $v, $vector ) ) );
		return $norm > 0 ? array_map( static fn( $v ) => $v / $norm, $vector ) : $vector;
	}

	public static function cosine( array $a, array $b ): float {
		$dot = $na = $nb = 0.0;
		$n   = min( count( $a ), count( $b ) );
		for ( $i = 0; $i < $n; $i++ ) {
			$dot += $a[ $i ] * $b[ $i ];
			$na  += $a[ $i ] * $a[ $i ];
			$nb  += $b[ $i ] * $b[ $i ];
		}
		return ( $na > 0 && $nb > 0 ) ? $dot / ( sqrt( $na ) * sqrt( $nb ) ) : 0.0;
	}

	/**
	 * Top-k passages above the similarity threshold.
	 *
	 * @return array<int, array{post_id:int, title:string, content:string, source_url:string, score:float}>|\WP_Error
	 */
	public static function search( string $query, int $k = 5 ) {
		global $wpdb;
		$vectors = self::embed( array( $query ) );
		if ( is_wp_error( $vectors ) ) {
			return $vectors;
		}
		$q    = $vectors[0];
		$rows = $wpdb->get_results( $wpdb->prepare( 'SELECT kb_post_id, content, embedding, source_url FROM ' . self::table() . ' WHERE model = %s', self::provider() ), ARRAY_A ); // phpcs:ignore WordPress.DB
		$hits = array();
		foreach ( $rows as $row ) {
			$score = self::cosine( $q, (array) json_decode( $row['embedding'], true ) );
			if ( $score >= self::threshold() ) {
				$hits[] = array(
					'post_id'    => (int) $row['kb_post_id'],
					'title'      => get_the_title( (int) $row['kb_post_id'] ),
					'content'    => $row['content'],
					'source_url' => $row['source_url'],
					'score'      => round( $score, 4 ),
				);
			}
		}
		usort( $hits, static fn( $x, $y ) => $y['score'] <=> $x['score'] );
		return array_slice( $hits, 0, max( 1, min( 8, $k ) ) );
	}
}
