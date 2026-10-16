<?php
namespace ASC_DM;

defined( 'ABSPATH' ) || exit;

/**
 * Minimal OpenAI client (embeddings + chat completions) over wp_remote_post.
 * The API key is read server-side only (constant or env), never sent to browsers.
 */
final class OpenAI {

	const API = 'https://api.openai.com/v1/';

	public static function api_key(): string {
		return Plugin::config( 'OPENAI_API_KEY' );
	}

	public static function is_configured(): bool {
		return '' !== self::api_key();
	}

	public static function chat_model(): string {
		return Plugin::config( 'OPENAI_CHAT_MODEL', 'gpt-5-mini' );
	}

	public static function embedding_model(): string {
		return Plugin::config( 'OPENAI_EMBEDDING_MODEL', 'text-embedding-3-small' );
	}

	/**
	 * @param string[] $inputs
	 * @return float[][]|\WP_Error One vector per input, same order.
	 */
	public static function embed( array $inputs ) {
		$body = self::request( 'embeddings', array(
			'model' => self::embedding_model(),
			'input' => array_values( $inputs ),
		) );
		if ( is_wp_error( $body ) ) {
			return $body;
		}
		$vectors = array();
		foreach ( $body['data'] ?? array() as $row ) {
			$vectors[ (int) $row['index'] ] = array_map( 'floatval', $row['embedding'] );
		}
		ksort( $vectors );
		if ( count( $vectors ) !== count( $inputs ) ) {
			return new \WP_Error( 'asc_openai_embed', 'Embedding response size mismatch.' );
		}
		return array_values( $vectors );
	}

	/**
	 * @param array<int, array{role:string, content:string}> $messages
	 * @return string|\WP_Error
	 */
	public static function chat( array $messages, int $max_tokens = 600 ) {
		$body = self::request( 'chat/completions', self::chat_payload( $messages, $max_tokens ), 45 );
		if ( is_wp_error( $body ) ) {
			return $body;
		}
		$text = trim( (string) ( $body['choices'][0]['message']['content'] ?? '' ) );
		return '' === $text ? new \WP_Error( 'asc_openai_empty', 'The model returned an empty answer.' ) : $text;
	}

	/**
	 * Streamed chat completion: calls $on_delta( string ) for each text fragment as it arrives.
	 * Uses cURL directly because wp_remote_post() cannot stream.
	 *
	 * @param array<int, array{role:string, content:string}> $messages
	 * @return true|\WP_Error
	 */
	public static function stream_chat( array $messages, int $max_tokens, callable $on_delta ) {
		if ( ! self::is_configured() || ! function_exists( 'curl_init' ) ) {
			return new \WP_Error( 'asc_openai_stream', 'Streaming is not available.' );
		}
		$buffer = '';
		$error  = '';
		$ch     = curl_init( self::API . 'chat/completions' ); // phpcs:ignore WordPress.WP.AlternativeFunctions
		curl_setopt_array( $ch, array( // phpcs:ignore WordPress.WP.AlternativeFunctions
			CURLOPT_POST           => true,
			CURLOPT_POSTFIELDS     => wp_json_encode( self::chat_payload( $messages, $max_tokens ) + array( 'stream' => true ) ),
			CURLOPT_HTTPHEADER     => array( 'Authorization: Bearer ' . self::api_key(), 'Content-Type: application/json' ),
			CURLOPT_CONNECTTIMEOUT => 10,
			CURLOPT_TIMEOUT        => 90,
			CURLOPT_WRITEFUNCTION  => static function ( $ch, string $chunk ) use ( &$buffer, &$error, $on_delta ): int {
				if ( curl_getinfo( $ch, CURLINFO_RESPONSE_CODE ) >= 300 ) { // phpcs:ignore WordPress.WP.AlternativeFunctions
					$error .= $chunk;
					return strlen( $chunk );
				}
				$buffer .= $chunk;
				while ( false !== ( $pos = strpos( $buffer, "\n" ) ) ) {
					$line   = trim( substr( $buffer, 0, $pos ) );
					$buffer = substr( $buffer, $pos + 1 );
					if ( ! str_starts_with( $line, 'data:' ) ) {
						continue;
					}
					$event = json_decode( trim( substr( $line, 5 ) ), true );
					$delta = is_array( $event ) ? (string) ( $event['choices'][0]['delta']['content'] ?? '' ) : '';
					if ( '' !== $delta ) {
						$on_delta( $delta );
					}
				}
				return strlen( $chunk );
			},
		) );
		$ok     = curl_exec( $ch ); // phpcs:ignore WordPress.WP.AlternativeFunctions
		$status = (int) curl_getinfo( $ch, CURLINFO_RESPONSE_CODE ); // phpcs:ignore WordPress.WP.AlternativeFunctions
		$curl   = curl_error( $ch ); // phpcs:ignore WordPress.WP.AlternativeFunctions
		curl_close( $ch ); // phpcs:ignore WordPress.WP.AlternativeFunctions
		if ( ! $ok || $status < 200 || $status >= 300 ) {
			$body = json_decode( $error, true );
			error_log( sprintf( '[asc-dm] OpenAI chat stream failed (%d): %s', $status, $body['error']['message'] ?? ( $curl ?: 'unknown error' ) ) );
			return new \WP_Error( 'asc_openai_http', 'The AI service is unavailable right now.', array( 'status' => $status ) );
		}
		return true;
	}

	private static function chat_payload( array $messages, int $max_tokens ): array {
		$model   = self::chat_model();
		$payload = array(
			'model'                 => $model,
			'messages'              => $messages,
			'max_completion_tokens' => $max_tokens,
		);
		// Reasoning models (gpt-5*, o*) take an effort hint; keep latency and cost low.
		if ( preg_match( '/^(gpt-5|o\d)/', $model ) ) {
			$payload['reasoning_effort'] = 'minimal';
		}
		return $payload;
	}

	/** @return array|\WP_Error */
	private static function request( string $endpoint, array $payload, int $timeout = 30 ) {
		if ( ! self::is_configured() ) {
			return new \WP_Error( 'asc_openai_missing_key', 'OPENAI_API_KEY is not configured.' );
		}
		$response = wp_remote_post( self::API . $endpoint, array(
			'timeout' => $timeout,
			'headers' => array(
				'Authorization' => 'Bearer ' . self::api_key(),
				'Content-Type'  => 'application/json',
			),
			'body'    => wp_json_encode( $payload ),
		) );
		if ( is_wp_error( $response ) ) {
			return $response;
		}
		$code = wp_remote_retrieve_response_code( $response );
		$body = json_decode( wp_remote_retrieve_body( $response ), true );
		if ( $code < 200 || $code >= 300 || ! is_array( $body ) ) {
			// Log the provider's message, never the request headers (which hold the key).
			$message = is_array( $body ) ? ( $body['error']['message'] ?? 'unknown error' ) : 'invalid JSON';
			error_log( sprintf( '[asc-dm] OpenAI %s failed (%d): %s', $endpoint, $code, $message ) );
			return new \WP_Error( 'asc_openai_http', 'The AI service is unavailable right now.', array( 'status' => $code ) );
		}
		return $body;
	}
}
