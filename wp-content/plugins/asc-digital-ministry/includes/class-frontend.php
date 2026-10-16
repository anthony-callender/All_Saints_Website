<?php
namespace ASC_DM;

defined( 'ABSPATH' ) || exit;

/**
 * Front-end design-system layer: tokens + component CSS, the chatbot widget,
 * and reusable block patterns ("Service Times", "Prayer CTA", ...).
 *
 * The CSS is theme-agnostic: it styles `asc-*` component classes and maps the
 * tokens onto the active theme. Under Avada, the same tokens are mirrored in
 * Avada Global Options (see README "Design system").
 */
final class Frontend {

	private static bool $chat_rendered = false;

	public static function init(): void {
		add_action( 'wp_enqueue_scripts', array( __CLASS__, 'enqueue_global' ) );
		add_action( 'enqueue_block_editor_assets', array( __CLASS__, 'enqueue_editor' ) );
		add_shortcode( 'asc_chatbot', array( __CLASS__, 'shortcode_chatbot' ) );
		add_action( 'wp_footer', array( __CLASS__, 'sitewide_chatbot' ) );
		add_action( 'init', array( __CLASS__, 'register_patterns' ) );
	}

	private static function asset( string $path ): string {
		return ASC_DM_URL . 'assets/' . $path;
	}

	private static function ver( string $path ): string {
		$file = ASC_DM_DIR . 'assets/' . $path;
		return file_exists( $file ) ? ASC_DM_VERSION . '.' . filemtime( $file ) : ASC_DM_VERSION;
	}

	public static function enqueue_global(): void {
		// Open-licence stand-ins for the brand's Adobe Garamond Pro + Proxima Nova.
		wp_enqueue_style( 'asc-fonts', 'https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,500;0,600;1,500&family=Source+Sans+3:ital,wght@0,400;0,600;0,700;1,400&display=swap', array(), null ); // phpcs:ignore WordPress.WP.EnqueuedResourceParameters.MissingVersion
		foreach ( array( 'tokens', 'base', 'components' ) as $sheet ) {
			$deps = 'tokens' === $sheet ? array( 'asc-fonts' ) : array( 'asc-tokens' );
			wp_enqueue_style( 'asc-' . $sheet, self::asset( "css/{$sheet}.css" ), $deps, self::ver( "css/{$sheet}.css" ) );
		}
		wp_register_style( 'asc-sermons', self::asset( 'css/sermons.css' ), array( 'asc-components' ), self::ver( 'css/sermons.css' ) );
		wp_register_script( 'asc-frontend', self::asset( 'js/frontend.js' ), array(), self::ver( 'js/frontend.js' ), array( 'strategy' => 'defer', 'in_footer' => true ) );
		wp_register_style( 'asc-chatbot', self::asset( 'css/chatbot.css' ), array( 'asc-tokens' ), self::ver( 'css/chatbot.css' ) );
		wp_register_script( 'asc-chatbot', self::asset( 'js/chatbot.js' ), array(), self::ver( 'js/chatbot.js' ), array( 'strategy' => 'defer', 'in_footer' => true ) );

		if ( is_singular( Sermons::POST_TYPE ) || is_post_type_archive( Sermons::POST_TYPE ) || is_front_page() ) {
			self::enqueue();
		}
	}

	/** Sermon/media components + small progressive-enhancement script. */
	public static function enqueue(): void {
		wp_enqueue_style( 'asc-sermons' );
		wp_enqueue_script( 'asc-frontend' );
	}

	public static function enqueue_editor(): void {
		// Let editors see component styling while composing pages in Gutenberg.
		wp_enqueue_style( 'asc-editor-tokens', self::asset( 'css/tokens.css' ), array(), self::ver( 'css/tokens.css' ) );
	}

	// ------------------------------------------------------------------
	// Chatbot widget
	// ------------------------------------------------------------------

	public static function shortcode_chatbot(): string {
		return self::render_chatbot();
	}

	public static function sitewide_chatbot(): void {
		if ( get_option( 'asc_dm_chat_sitewide', '1' ) && ! is_admin() ) {
			echo self::render_chatbot(); // phpcs:ignore WordPress.Security.EscapeOutput -- escaped in template.
		}
	}

	public static function render_chatbot(): string {
		if ( self::$chat_rendered ) {
			return '';
		}
		self::$chat_rendered = true;
		wp_enqueue_style( 'asc-chatbot' );
		wp_enqueue_script( 'asc-chatbot' );
		return Sermons::template( 'chatbot', array(
			'endpoint'    => rest_url( 'asc/v1/chat' ),
			'suggestions' => array(
				__( "I'm visiting for the first time. What should I expect?", 'asc-digital-ministry' ),
				__( 'What time is Sunday worship?', 'asc-digital-ministry' ),
				__( 'What is there for kids?', 'asc-digital-ministry' ),
			),
		) );
	}

	// ------------------------------------------------------------------
	// Shared art + patterns
	// ------------------------------------------------------------------

	/** Liturgical colours: [label, gradient from, gradient to, ink, accent]. */
	private const SEASONS = array(
		'advent'    => array( 'Advent', '#2a2766', '#4a3f8f', '#ffffff', '#e3b46a' ),
		'christmas' => array( 'Christmastide', '#f6efdc', '#e6cc8f', '#0b2a60', '#b3141e' ),
		'epiphany'  => array( 'Epiphany', '#173f31', '#2f6b4f', '#ffffff', '#e3b46a' ),
		'lent'      => array( 'Lent', '#36193f', '#5c2d6c', '#ffffff', '#e3b46a' ),
		'holy-week' => array( 'Holy Week', '#5e0a12', '#a3121c', '#ffffff', '#f3d39a' ),
		'easter'    => array( 'Eastertide', '#f6efdc', '#e6cc8f', '#0b2a60', '#b3141e' ),
		'pentecost' => array( 'Pentecost', '#5e0a12', '#a3121c', '#ffffff', '#f3d39a' ),
		'ordinary'  => array( 'Season after Pentecost', '#173f31', '#2f6b4f', '#ffffff', '#e3b46a' ),
	);

	/** Western Easter (anonymous Gregorian algorithm); avoids needing ext-calendar. */
	private static function easter( int $y ): int {
		$a = $y % 19; $b = intdiv( $y, 100 ); $c = $y % 100;
		$h = ( 19 * $a + $b - intdiv( $b, 4 ) - intdiv( $b - intdiv( $b + 8, 25 ) + 1, 3 ) + 15 ) % 30;
		$l = ( 32 + 2 * ( $b % 4 ) + 2 * intdiv( $c, 4 ) - $h - $c % 4 ) % 7;
		$m = intdiv( $a + 11 * $h + 22 * $l, 451 );
		$n = $h + $l - 7 * $m + 114;
		return gmmktime( 0, 0, 0, intdiv( $n, 31 ), $n % 31 + 1, $y );
	}

	/** Season of the church year for a Y-m-d date. */
	public static function season( string $date ): string {
		$t = strtotime( $date . ' 00:00:00 UTC' );
		if ( ! $t ) {
			return 'ordinary';
		}
		$y      = (int) gmdate( 'Y', $t );
		$day    = DAY_IN_SECONDS;
		$easter = self::easter( $y );
		$xmas   = gmmktime( 0, 0, 0, 12, 25, $y );
		$advent = $xmas - ( ( (int) gmdate( 'w', $xmas ) ?: 7 ) + 21 ) * $day;
		$md     = gmdate( 'm-d', $t );
		return match ( true ) {
			$t >= $xmas || $md <= '01-05'    => 'christmas',
			$t >= $advent                    => 'advent',
			$t < $easter - 46 * $day         => 'epiphany',
			$t < $easter - 7 * $day          => 'lent',
			$t < $easter                     => 'holy-week',
			$t < $easter + 49 * $day         => 'easter',
			$t < $easter + 50 * $day         => 'pentecost',
			default                          => 'ordinary',
		};
	}

	/**
	 * Placeholder art for audio-only sermons: the service date on the colour of
	 * the liturgical season, with a faint Jerusalem Cross. Purely decorative.
	 */
	public static function placeholder_art( string $date = '' ): string {
		static $n = 0;
		$id     = 'asc-art-' . ( ++$n );
		$season = $date ? self::season( $date ) : 'ordinary';
		[ $label, $from, $to, $ink, $accent ] = self::SEASONS[ $season ];
		$t     = $date ? strtotime( $date . ' 12:00:00' ) : false;
		$serif = "font-family:var(--asc-font-serif,Georgia,serif)";
		$sans  = "font-family:var(--asc-font-sans,system-ui,sans-serif)";
		$text  = $t
			? '<text x="14" y="62" fill="' . $ink . '" style="' . $serif . ';font-size:50px;font-weight:500;letter-spacing:-1.5px">' . esc_html( wp_date( 'j', $t ) ) . '</text>'
				. '<text x="15.5" y="77" fill="' . $ink . '" opacity=".85" style="' . $sans . ';font-size:7.5px;font-weight:700;letter-spacing:1.6px">' . esc_html( strtoupper( wp_date( 'F Y', $t ) ) ) . '</text>'
			: '';
		return '<svg class="asc-placeholder-art asc-placeholder-art--' . esc_attr( $season ) . '" viewBox="0 0 160 90" aria-hidden="true" focusable="false" preserveAspectRatio="xMidYMid slice">'
			. '<defs><linearGradient id="' . $id . '" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="' . $from . '"/><stop offset="1" stop-color="' . $to . '"/></linearGradient></defs>'
			. '<rect width="160" height="90" fill="url(#' . $id . ')"/>'
			. '<g transform="translate(124 45) scale(1.5)" fill="none" stroke="' . $ink . '" stroke-width="1.6" opacity=".16">'
			. '<path d="M-6-26h12v20h20v12H6v20H-6V6h-20V-6h20z"/>'
			. '<path d="M-20-22v8m-4-4h8M20-22v8m-4-4h8M-20 14v8m-4-4h8M20 14v8m-4-4h8" stroke-linecap="round"/></g>'
			. '<rect x="15.5" y="12" width="10" height="1.4" fill="' . $accent . '"/>'
			. '<text x="15.5" y="22" fill="' . $ink . '" opacity=".9" style="' . $sans . ';font-size:6.5px;font-weight:700;letter-spacing:1.4px">' . esc_html( strtoupper( $label ) ) . '</text>'
			. $text
			. '</svg>';
	}

	public static function register_patterns(): void {
		register_block_pattern_category( 'all-saints', array( 'label' => __( "All Saints' Sections", 'asc-digital-ministry' ) ) );
		foreach ( glob( ASC_DM_DIR . 'patterns/*.html' ) ?: array() as $file ) {
			$markup = (string) file_get_contents( $file ); // phpcs:ignore WordPress.WP.AlternativeFunctions
			// First line holds the title: <!-- Title: Service Times -->
			if ( ! preg_match( '/^<!--\s*Title:\s*(.+?)\s*-->\s*/', $markup, $m ) ) {
				continue;
			}
			register_block_pattern( 'all-saints/' . basename( $file, '.html' ), array(
				'title'      => $m[1],
				'categories' => array( 'all-saints' ),
				'content'    => substr( $markup, strlen( $m[0] ) ),
			) );
		}
	}
}
