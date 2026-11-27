import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../models/email_category.dart';
import '../models/email_item.dart';
import '../providers/accounts_provider.dart';
import '../providers/app_settings_provider.dart';
import '../providers/dashboard_provider.dart';
import '../providers/emails_provider.dart';
import '../providers/notifications_provider.dart';
import '../theme/app_colors.dart';
import '../utils/responsive.dart';
import '../widgets/email_card.dart';
import '../widgets/jobmail_logo.dart';
import '../widgets/stat_card.dart';
import '../widgets/state_views.dart';
import 'category_emails_screen.dart';
import 'email_detail_screen.dart';
import 'notifications_screen.dart';

/// Screen 3: Executive dashboard with career KPIs and recent classified emails.
class DashboardScreen extends StatefulWidget {
  const DashboardScreen({
    super.key,
    required this.onOpenInbox,
    required this.onOpenAccounts,
    required this.onOpenSettings,
  });

  final VoidCallback onOpenInbox;
  final VoidCallback onOpenAccounts;
  final VoidCallback onOpenSettings;

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      context.read<DashboardProvider>().loadDashboard();
      context.read<AccountsProvider>().loadAccounts();
      context.read<NotificationsProvider>().loadNotifications();
    });
  }

  Future<void> _openEmail(EmailItem email) async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => EmailDetailScreen(initialEmail: email),
      ),
    );
  }

  void _openCategory(EmailCategory category) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => CategoryEmailsScreen(category: category),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final settings = context.watch<AppSettingsProvider>();
    final dashboard = context.watch<DashboardProvider>();
    final accounts = context.watch<AccountsProvider>();
    final notifications = context.watch<NotificationsProvider>();

    final stats = dashboard.stats;
    final unreadNotifications = notifications.unreadCount;
    final maxWidth = Responsive.contentMaxWidth(context);

    return Scaffold(
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: () async {
            await Future.wait<void>(<Future<void>>[
              dashboard.loadDashboard(),
              accounts.loadAccounts(),
              notifications.loadNotifications(),
            ]);
          },
          child: Align(
            alignment: Alignment.topCenter,
            child: ConstrainedBox(
              constraints: BoxConstraints(maxWidth: maxWidth),
              child: ListView(
                physics: const AlwaysScrollableScrollPhysics(),
                padding: const EdgeInsets.fromLTRB(20, 16, 20, 28),
                children: <Widget>[
                  _buildTopBar(
                    context,
                    userName: settings.profileName,
                    unreadCount: unreadNotifications,
                  ),
                  const SizedBox(height: 20),
                  _buildAccountStatusBanner(context, accounts),
                  const SizedBox(height: 20),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: <Widget>[
                      Text(
                        'Overview',
                        style: Theme.of(context).textTheme.titleLarge,
                      ),
                      TextButton.icon(
                        onPressed: dashboard.isSyncing
                            ? null
                            : () async {
                                final ok = await dashboard.syncNow();
                                if (!context.mounted) return;
                                if (ok) {
                                  accounts.loadAccounts();
                                  context.read<EmailsProvider>().loadEmails();
                                  notifications.loadNotifications();
                                }
                                ScaffoldMessenger.of(context).showSnackBar(
                                  SnackBar(
                                    content: Text(
                                      ok
                                          ? (dashboard.lastSyncMessage ??
                                              'Gmail sync complete.')
                                          : (dashboard.errorMessage ??
                                              'Sync failed.'),
                                    ),
                                  ),
                                );
                              },
                        icon: dashboard.isSyncing
                            ? const SizedBox(
                                width: 14,
                                height: 14,
                                child:
                                    CircularProgressIndicator(strokeWidth: 2),
                              )
                            : const Icon(Icons.sync_rounded, size: 18),
                        label: Text(
                            dashboard.isSyncing ? 'Syncing...' : 'Sync Now'),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  GridView(
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                      crossAxisCount: Responsive.gridColumnCount(context),
                      crossAxisSpacing: 12,
                      mainAxisSpacing: 12,
                      mainAxisExtent: Responsive.isCompact(context) ? 164 : 158,
                    ),
                    children: <Widget>[
                      StatCard(
                        title: 'Total Job Emails',
                        value: stats.totalJobEmails,
                        icon: Icons.work_outline_rounded,
                        accentColor: AppColors.primary,
                        onTap: widget.onOpenInbox,
                      ),
                      StatCard(
                        title: 'New Opportunities',
                        value: stats.newOpportunities,
                        icon: Icons.auto_awesome_outlined,
                        accentColor: AppColors.secondary,
                        onTap: () => _openCategory(EmailCategory.job),
                      ),
                      StatCard(
                        title: 'Interview Invitations',
                        value: stats.interviewInvitations,
                        icon: Icons.event_available_outlined,
                        accentColor: AppColors.accentPurple,
                        onTap: () => _openCategory(EmailCategory.interview),
                      ),
                      StatCard(
                        title: 'Assessment Invitations',
                        value: stats.assessmentInvitations,
                        icon: Icons.quiz_outlined,
                        accentColor: AppColors.accentAmber,
                        onTap: () => _openCategory(EmailCategory.assessment),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Wrap(
                    spacing: 10,
                    runSpacing: 8,
                    children: <Widget>[
                      _SummaryPill(
                        icon: Icons.mark_email_read_outlined,
                        label: 'Processed: ${stats.totalProcessedEmails}',
                      ),
                      _SummaryPill(
                        icon: Icons.notifications_active_outlined,
                        label: 'Unread Alerts: $unreadNotifications',
                      ),
                    ],
                  ),
                  const SizedBox(height: 20),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: <Widget>[
                      Text(
                        'Recent Emails',
                        style: Theme.of(context).textTheme.titleLarge,
                      ),
                      TextButton(
                        onPressed: widget.onOpenInbox,
                        child: const Text('View all'),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  _buildRecentEmailsSection(context, dashboard),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildTopBar(
    BuildContext context, {
    required String userName,
    required int unreadCount,
  }) {
    return Row(
      children: <Widget>[
        const JobMailLogo(size: 42),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(
                'Welcome back, $userName',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.titleLarge,
              ),
              Text(
                'Never Miss a Job Opportunity.',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ),
        ),
        IconButton(
          tooltip: 'Notifications',
          onPressed: () {
            Navigator.of(context).push(
              MaterialPageRoute<void>(
                builder: (_) => const NotificationsScreen(),
              ),
            );
          },
          icon: Badge(
            isLabelVisible: unreadCount > 0,
            label: Text(unreadCount > 99 ? '99+' : unreadCount.toString()),
            child: const Icon(Icons.notifications_outlined),
          ),
        ),
        IconButton(
          tooltip: 'Profile & Settings',
          onPressed: widget.onOpenSettings,
          icon: const Icon(Icons.account_circle_outlined, size: 28),
        ),
      ],
    );
  }

  Widget _buildAccountStatusBanner(
    BuildContext context,
    AccountsProvider accounts,
  ) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final hasAccounts = accounts.accounts.isNotEmpty;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: isDark
              ? const <Color>[Color(0xFF172554), Color(0xFF0F3D3E)]
              : const <Color>[Color(0xFFEFF6FF), Color(0xFFECFDF5)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(
          color: AppColors.primary.withAlpha(isDark ? 80 : 45),
        ),
      ),
      child: Row(
        children: <Widget>[
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: AppColors.primary.withAlpha(32),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Icon(
              hasAccounts
                  ? Icons.verified_user_outlined
                  : Icons.add_link_rounded,
              color: isDark ? AppColors.primaryDark : AppColors.primary,
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  hasAccounts
                      ? '${accounts.accounts.length} Gmail account${accounts.accounts.length == 1 ? '' : 's'} connected'
                      : 'Connect your Gmail account',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const SizedBox(height: 2),
                Text(
                  hasAccounts
                      ? 'Monitoring recruitment messages with read-only OAuth.'
                      : 'Authorize read-only Gmail access to automatically detect job opportunities.',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          TextButton(
            onPressed: widget.onOpenAccounts,
            child: Text(hasAccounts ? 'Manage' : 'Connect'),
          ),
        ],
      ),
    );
  }

  Widget _buildRecentEmailsSection(
    BuildContext context,
    DashboardProvider dashboard,
  ) {
    if (dashboard.isLoading && dashboard.recentEmails.isEmpty) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 32),
        child: LoadingStateView(message: 'Fetching recent job emails...'),
      );
    }

    if (dashboard.errorMessage != null && dashboard.recentEmails.isEmpty) {
      return ErrorStateView(
        message: dashboard.errorMessage!,
        onRetry: dashboard.loadDashboard,
        secondaryLabel: 'Connected Accounts',
        onSecondary: widget.onOpenAccounts,
      );
    }

    if (dashboard.recentEmails.isEmpty) {
      return EmptyStateView(
        icon: Icons.mark_email_read_outlined,
        title: 'No recent job emails yet',
        subtitle:
            'Connect a Gmail account or run a sync to populate your intelligent career inbox.',
        actionLabel: 'Connect Gmail',
        onAction: widget.onOpenAccounts,
      );
    }

    return Column(
      children: dashboard.recentEmails
          .map(
            (email) => Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: EmailCard(
                email: email,
                onTap: () => _openEmail(email),
              ),
            ),
          )
          .toList(),
    );
  }
}

class _SummaryPill extends StatelessWidget {
  const _SummaryPill({required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
      decoration: BoxDecoration(
        color: isDark ? AppColors.darkSurface : AppColors.lightSurface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: isDark ? AppColors.darkBorder : AppColors.lightBorder,
        ),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(
            icon,
            size: 15,
            color: Theme.of(context).colorScheme.primary,
          ),
          const SizedBox(width: 6),
          Text(
            label,
            style: Theme.of(context).textTheme.labelLarge,
          ),
        ],
      ),
    );
  }
}
