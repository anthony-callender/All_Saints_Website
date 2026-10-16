<?php
namespace ASC_DM;

defined( 'ABSPATH' ) || exit;

/**
 * Wires the plugin together and provides configuration lookup.
 */
final class Plugin {

	public static function boot(): void {
		Sermons::init();
		Sermon_API::init();
		KB::init();
		Chat_API::init();
		Frontend::init();
		Admin::init();
	}

	public static function activate(): void {
		Embeddings::install_table();
		Sermons::register();
		KB::register();
		flush_rewrite_rules();
	}

	public static function deactivate(): void {
		flush_rewrite_rules();
	}

	/**
	 * Read configuration. Order: PHP constant (wp-config.php) → environment variable → default.
	 * Secrets never live in the database or in front-end output.
	 */
	public static function config( string $key, string $fallback = '' ): string {
		if ( defined( $key ) ) {
			return (string) constant( $key );
		}
		$value = getenv( $key );
		if ( false !== $value && '' !== $value ) {
			return (string) $value;
		}
		return $fallback;
	}
}
