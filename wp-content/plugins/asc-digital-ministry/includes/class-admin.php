<?php
namespace ASC_DM;

defined( 'ABSPATH' ) || exit;

/**
 * Church Knowledge → Assistant Settings: index status, "Reindex Church
 * Knowledge" button, and the two editable assistant settings.
 * Shows whether keys are configured, never their values.
 */
final class Admin {

	const SLUG = 'asc-assistant';
	const CAP  = 'edit_others_posts'; // Editors (e.g. the site manager) and admins.

	public static function init(): void {
		add_action( 'admin_menu', array( __CLASS__, 'menu' ) );
		add_action( 'admin_post_asc_kb_reindex', array( __CLASS__, 'handle_reindex' ) );
		add_action( 'admin_post_asc_assistant_settings', array( __CLASS__, 'handle_settings' ) );
		add_action( 'admin_notices', array( __CLASS__, 'notices' ) );
	}

	public static function menu(): void {
		add_submenu_page(
			'edit.php?post_type=' . KB::POST_TYPE,
			__( 'Assistant Settings', 'asc-digital-ministry' ),
			__( 'Assistant Settings', 'asc-digital-ministry' ),
			self::CAP,
			self::SLUG,
			array( __CLASS__, 'render' )
		);
	}

	public static function render(): void {
		if ( ! current_user_can( self::CAP ) ) {
			return;
		}
		$entries = (int) wp_count_posts( KB::POST_TYPE )->publish;
		?>
		<div class="wrap">
			<h1><?php esc_html_e( 'Website Assistant', 'asc-digital-ministry' ); ?></h1>
			<p><?php esc_html_e( 'The assistant answers visitor questions using only the published Church Knowledge entries. Entries are re-indexed automatically when you save them; use the button below after bulk changes.', 'asc-digital-ministry' ); ?></p>

			<table class="widefat striped" style="max-width:48rem">
				<tbody>
					<tr><th><?php esc_html_e( 'Published entries', 'asc-digital-ministry' ); ?></th><td><?php echo esc_html( (string) $entries ); ?></td></tr>
					<tr><th><?php esc_html_e( 'Indexed passages', 'asc-digital-ministry' ); ?></th><td><?php echo esc_html( (string) Embeddings::chunk_count() ); ?></td></tr>
					<tr><th><?php esc_html_e( 'Embedding provider', 'asc-digital-ministry' ); ?></th><td><code><?php echo esc_html( Embeddings::provider() ); ?></code></td></tr>
					<tr><th><?php esc_html_e( 'Chat model', 'asc-digital-ministry' ); ?></th><td><code><?php echo esc_html( OpenAI::is_configured() ? OpenAI::chat_model() : __( 'offline (extractive answers)', 'asc-digital-ministry' ) ); ?></code></td></tr>
					<tr><th><?php esc_html_e( 'OpenAI key configured', 'asc-digital-ministry' ); ?></th><td><?php echo OpenAI::is_configured() ? '✅' : esc_html__( 'No — set OPENAI_API_KEY in the server environment', 'asc-digital-ministry' ); ?></td></tr>
				</tbody>
			</table>

			<form method="post" action="<?php echo esc_url( admin_url( 'admin-post.php' ) ); ?>" style="margin-top:1.5rem">
				<?php wp_nonce_field( 'asc_kb_reindex' ); ?>
				<input type="hidden" name="action" value="asc_kb_reindex">
				<?php submit_button( __( 'Reindex Church Knowledge', 'asc-digital-ministry' ), 'primary', 'submit', false ); ?>
			</form>

			<h2 style="margin-top:2.5rem"><?php esc_html_e( 'Settings', 'asc-digital-ministry' ); ?></h2>
			<form method="post" action="<?php echo esc_url( admin_url( 'admin-post.php' ) ); ?>">
				<?php wp_nonce_field( 'asc_assistant_settings' ); ?>
				<input type="hidden" name="action" value="asc_assistant_settings">
				<table class="form-table" role="presentation">
					<tr>
						<th scope="row"><?php esc_html_e( 'Show on every page', 'asc-digital-ministry' ); ?></th>
						<td><label><input type="checkbox" name="asc_dm_chat_sitewide" value="1" <?php checked( (bool) get_option( 'asc_dm_chat_sitewide', '1' ) ); ?>> <?php esc_html_e( 'Show the “Questions?” button site-wide (otherwise use the [asc_chatbot] shortcode on chosen pages).', 'asc-digital-ministry' ); ?></label></td>
					</tr>
					<tr>
						<th scope="row"><label for="asc_dm_contact_line"><?php esc_html_e( 'Office contact sentence', 'asc-digital-ministry' ); ?></label></th>
						<td>
							<textarea id="asc_dm_contact_line" name="asc_dm_contact_line" rows="2" class="large-text"><?php echo esc_textarea( Chat_API::contact_line() ); ?></textarea>
							<p class="description"><?php esc_html_e( 'Used when the assistant cannot answer a question.', 'asc-digital-ministry' ); ?></p>
						</td>
					</tr>
				</table>
				<?php submit_button( __( 'Save Settings', 'asc-digital-ministry' ) ); ?>
			</form>
		</div>
		<?php
	}

	public static function handle_reindex(): void {
		if ( ! current_user_can( self::CAP ) ) {
			wp_die( esc_html__( 'Sorry, you are not allowed to do that.', 'asc-digital-ministry' ), 403 );
		}
		check_admin_referer( 'asc_kb_reindex' );
		$result = Embeddings::reindex_all( true );
		set_transient( 'asc_dm_notice_' . get_current_user_id(), $result, 60 );
		wp_safe_redirect( admin_url( 'edit.php?post_type=' . KB::POST_TYPE . '&page=' . self::SLUG ) );
		exit;
	}

	public static function handle_settings(): void {
		if ( ! current_user_can( self::CAP ) ) {
			wp_die( esc_html__( 'Sorry, you are not allowed to do that.', 'asc-digital-ministry' ), 403 );
		}
		check_admin_referer( 'asc_assistant_settings' );
		update_option( 'asc_dm_chat_sitewide', empty( $_POST['asc_dm_chat_sitewide'] ) ? '0' : '1' );
		update_option( 'asc_dm_contact_line', sanitize_textarea_field( wp_unslash( $_POST['asc_dm_contact_line'] ?? '' ) ) );
		wp_safe_redirect( admin_url( 'edit.php?post_type=' . KB::POST_TYPE . '&page=' . self::SLUG . '&updated=1' ) );
		exit;
	}

	public static function notices(): void {
		$key    = 'asc_dm_notice_' . get_current_user_id();
		$result = get_transient( $key );
		if ( ! $result ) {
			return;
		}
		delete_transient( $key );
		$class = $result['errors'] ? 'notice-warning' : 'notice-success';
		printf(
			'<div class="notice %s is-dismissible"><p>%s</p>%s</div>',
			esc_attr( $class ),
			esc_html( sprintf( /* translators: 1 entries 2 passages */ __( 'Reindexed %1$d entries into %2$d passages.', 'asc-digital-ministry' ), $result['posts'], $result['chunks'] ) ),
			$result['errors'] ? '<p>' . esc_html( implode( ' | ', $result['errors'] ) ) . '</p>' : ''
		);
	}
}
