<?php
/**
 * Plugin Name:       ASC Digital Ministry
 * Description:       Sermons, Church Knowledge, the grounded website assistant, and the All Saints' design-system layer.
 * Version:           1.0.0
 * Requires at least: 6.7
 * Requires PHP:      8.1
 * Author:            All Saints' Church
 * License:           GPL-2.0-or-later
 * Text Domain:       asc-digital-ministry
 */

defined( 'ABSPATH' ) || exit;

define( 'ASC_DM_VERSION', '1.0.0' );
define( 'ASC_DM_FILE', __FILE__ );
define( 'ASC_DM_DIR', plugin_dir_path( __FILE__ ) );
define( 'ASC_DM_URL', plugin_dir_url( __FILE__ ) );

require_once ASC_DM_DIR . 'includes/class-plugin.php';
require_once ASC_DM_DIR . 'includes/class-openai.php';
require_once ASC_DM_DIR . 'includes/class-sermons.php';
require_once ASC_DM_DIR . 'includes/class-sermon-api.php';
require_once ASC_DM_DIR . 'includes/class-kb.php';
require_once ASC_DM_DIR . 'includes/class-embeddings.php';
require_once ASC_DM_DIR . 'includes/class-chat-api.php';
require_once ASC_DM_DIR . 'includes/class-frontend.php';
require_once ASC_DM_DIR . 'includes/class-admin.php';

if ( defined( 'WP_CLI' ) && WP_CLI ) {
	require_once ASC_DM_DIR . 'includes/class-cli.php';
}

register_activation_hook( __FILE__, array( 'ASC_DM\Plugin', 'activate' ) );
register_deactivation_hook( __FILE__, array( 'ASC_DM\Plugin', 'deactivate' ) );

ASC_DM\Plugin::boot();
