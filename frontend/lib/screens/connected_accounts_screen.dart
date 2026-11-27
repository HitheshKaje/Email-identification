import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';
import '../models/connected_account.dart';
import '../providers/accounts_provider.dart';
import '../providers/dashboard_provider.dart';
import '../providers/emails_provider.dart';
import '../providers/notifications_provider.dart';
import '../theme/app_colors.dart';
import '../utils/responsive.dart';
import '../widgets/account_card.dart';
import '../widgets/state_views.dart';

/// Screen 7: Manage multiple Gmail accounts connected via Google OAuth 2.0.
class ConnectedAccountsScreen extends StatefulWidget {
  const ConnectedAccountsScreen({super.key});

  @override
  State<ConnectedAccountsScreen> createState() =>
      _ConnectedAccountsScreenState();
}

class _ConnectedAccountsScreenState extends State<ConnectedAccountsScreen>
    with WidgetsBindingObserver {
  bool _awaitingOAuthReturn = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      context.read<AccountsProvider>().loadAccounts();
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && _awaitingOAuthReturn && mounted) {
      _awaitingOAuthReturn = false;
      context.read<AccountsProvider>().loadAccounts();
      context.read<DashboardProvider>().loadDashboard();
    }
  }

  Future<void> _connectGmail() async {
    final provider = context.read<AccountsProvider>();
    final authUrl = await provider.requestGoogleConnectUrl();
    if (!mounted) return;

    if (authUrl == null || authUrl.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            provider.actionError ?? 'Unable to start Google OAuth flow.',
          ),
        ),
      );
      return;
    }

    final uri = Uri.tryParse(authUrl);
    if (uri == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Invalid OAuth authorization URL.')),
      );
      return;
    }

    _awaitingOAuthReturn = true;
    final launched = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!launched && mounted) {
      _awaitingOAuthReturn = false;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Could not launch browser for Google sign-in.'),
        ),
      );
    }
  }

  Future<void> _confirmDisconnect(ConnectedAccount account) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Text('Disconnect Gmail Account?'),
          content: Text(
            'Disconnecting ${account.emailAddress} will stop background synchronization, revoke its Google OAuth tokens, and permanently delete its stored credentials and synced emails from JobMail.',
          ),
          actions: <Widget>[
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              style: FilledButton.styleFrom(backgroundColor: AppColors.error),
              onPressed: () => Navigator.pop(dialogContext, true),
              child: const Text('Disconnect'),
            ),
          ],
        );
      },
    );

    if (confirmed != true || !mounted) return;

    final provider = context.read<AccountsProvider>();
    final ok = await provider.disconnectAccount(account.id);
    if (!mounted) return;
    if (ok) {
      context.read<DashboardProvider>().loadDashboard();
      context.read<EmailsProvider>().loadEmails();
      context.read<NotificationsProvider>().loadNotifications();
    }

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          ok
              ? '${account.emailAddress} disconnected.'
              : (provider.actionError ?? 'Disconnect failed.'),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<AccountsProvider>();
    final maxWidth = Responsive.contentMaxWidth(context);
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Connected Accounts'),
        actions: <Widget>[
          IconButton(
            tooltip: 'Refresh accounts',
            onPressed: provider.isLoading ? null : provider.loadAccounts,
            icon: const Icon(Icons.refresh_rounded),
          ),
        ],
      ),
      body: Align(
        alignment: Alignment.topCenter,
        child: ConstrainedBox(
          constraints: BoxConstraints(maxWidth: maxWidth),
          child: RefreshIndicator(
            onRefresh: provider.loadAccounts,
            child: ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 28),
              children: <Widget>[
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color:
                        isDark ? AppColors.darkSurface : AppColors.lightSurface,
                    borderRadius: BorderRadius.circular(18),
                    border: Border.all(
                      color:
                          isDark ? AppColors.darkBorder : AppColors.lightBorder,
                    ),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Row(
                        children: <Widget>[
                          Container(
                            padding: const EdgeInsets.all(9),
                            decoration: BoxDecoration(
                              color: AppColors.secondary.withAlpha(28),
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: const Icon(
                              Icons.lock_outline_rounded,
                              color: AppColors.secondary,
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Text(
                              'Google OAuth 2.0 Security',
                              style: Theme.of(context).textTheme.titleMedium,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 10),
                      Text(
                        'JobMail requests read-only Gmail access via Google OAuth 2.0. You are never asked for your Gmail password, and you can revoke access at any time.',
                        style: Theme.of(context).textTheme.bodyMedium,
                      ),
                      const SizedBox(height: 14),
                      SizedBox(
                        width: double.infinity,
                        child: FilledButton.icon(
                          onPressed:
                              provider.isConnecting ? null : _connectGmail,
                          icon: provider.isConnecting
                              ? const SizedBox(
                                  width: 16,
                                  height: 16,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                    color: Colors.white,
                                  ),
                                )
                              : const Icon(Icons.add_circle_outline_rounded),
                          label: Text(
                            provider.isConnecting
                                ? 'Opening Google OAuth...'
                                : 'Connect Gmail',
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 20),
                Text(
                  'Linked Gmail Accounts',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                const SizedBox(height: 12),
                _buildAccountsSection(context, provider),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildAccountsSection(
    BuildContext context,
    AccountsProvider provider,
  ) {
    if (provider.isLoading && provider.accounts.isEmpty) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 32),
        child: LoadingStateView(message: 'Loading connected Gmail accounts...'),
      );
    }

    if (provider.errorMessage != null && provider.accounts.isEmpty) {
      return ErrorStateView(
        message: provider.errorMessage!,
        onRetry: provider.loadAccounts,
      );
    }

    if (provider.accounts.isEmpty) {
      return EmptyStateView(
        icon: Icons.alternate_email_rounded,
        title: 'No Gmail accounts connected',
        subtitle:
            'Connect one or more Gmail accounts to start automatically detecting job opportunities and interview invitations.',
        actionLabel: 'Connect Gmail',
        onAction: _connectGmail,
      );
    }

    return Column(
      children: provider.accounts.map((account) {
        return Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: AccountCard(
            account: account,
            isSyncing: provider.syncingAccountId == account.id,
            isVerifying: provider.verifyingAccountId == account.id,
            onReconnect: _connectGmail,
            onVerify: () async {
              final ok = await provider.verifyAccount(account.id);
              if (!context.mounted) return;
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: Text(
                    ok
                        ? '${account.emailAddress} connection verified.'
                        : (provider.actionError ?? 'Verification failed.'),
                  ),
                ),
              );
            },
            onSync: () async {
              final ok = await provider.syncAccount(account.id);
              if (!context.mounted) return;
              if (ok) {
                context.read<DashboardProvider>().loadDashboard();
                context.read<EmailsProvider>().loadEmails();
                context.read<NotificationsProvider>().loadNotifications();
              }
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: Text(
                    ok
                        ? (provider.lastSyncMessage ??
                            'Synced ${account.emailAddress}.')
                        : (provider.actionError ?? 'Sync failed.'),
                  ),
                ),
              );
            },
            onDisconnect: () => _confirmDisconnect(account),
          ),
        );
      }).toList(),
    );
  }
}
