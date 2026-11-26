import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../models/notification_item.dart';
import '../models/notification_preferences.dart';
import '../providers/notifications_provider.dart';
import '../theme/app_colors.dart';
import '../utils/date_formatter.dart';
import '../utils/responsive.dart';
import '../widgets/state_views.dart';
import 'email_detail_screen.dart';

/// Screen 8: Recruitment alert feed and category notification preferences.
class NotificationsScreen extends StatefulWidget {
  const NotificationsScreen({super.key});

  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends State<NotificationsScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      context.read<NotificationsProvider>().loadNotifications();
    });
  }

  Future<void> _openNotification(NotificationItem item) async {
    await context.read<NotificationsProvider>().markAsRead(item.id);
    if (!mounted) return;
    if (item.emailId.isNotEmpty) {
      await Navigator.of(context).push(
        MaterialPageRoute<void>(
          builder: (_) => EmailDetailScreen(emailId: item.emailId),
        ),
      );
    }
  }

  Future<void> _openPreferencesSheet() async {
    await showNotificationPreferencesSheet(context);
  }

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<NotificationsProvider>();
    final maxWidth = Responsive.contentMaxWidth(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Notifications'),
        actions: <Widget>[
          IconButton(
            tooltip: 'Notification preferences',
            onPressed: _openPreferencesSheet,
            icon: const Icon(Icons.tune_rounded),
          ),
        ],
      ),
      body: Align(
        alignment: Alignment.topCenter,
        child: ConstrainedBox(
          constraints: BoxConstraints(maxWidth: maxWidth),
          child: RefreshIndicator(
            onRefresh: provider.loadNotifications,
            child: _buildBody(context, provider),
          ),
        ),
      ),
    );
  }

  Widget _buildBody(BuildContext context, NotificationsProvider provider) {
    if (provider.isLoading && provider.notifications.isEmpty) {
      return const LoadingStateView(message: 'Loading job notifications...');
    }

    if (provider.errorMessage != null && provider.notifications.isEmpty) {
      return ListView(
        children: <Widget>[
          ErrorStateView(
            message: provider.errorMessage!,
            onRetry: provider.loadNotifications,
            secondaryLabel: 'Alert Preferences',
            onSecondary: _openPreferencesSheet,
          ),
        ],
      );
    }

    if (provider.notifications.isEmpty) {
      return ListView(
        children: <Widget>[
          EmptyStateView(
            icon: Icons.notifications_none_rounded,
            title: 'No notifications yet',
            subtitle:
                'When JobMail detects new interviews, assessments, offer letters, or job openings, alerts will appear here.',
            actionLabel: 'Configure Preferences',
            onAction: _openPreferencesSheet,
          ),
        ],
      );
    }

    final isDark = Theme.of(context).brightness == Brightness.dark;
    final surface = isDark ? AppColors.darkSurface : AppColors.lightSurface;
    final border = isDark ? AppColors.darkBorder : AppColors.lightBorder;

    return ListView.separated(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
      itemCount: provider.notifications.length,
      separatorBuilder: (_, __) => const SizedBox(height: 10),
      itemBuilder: (context, index) {
        final item = provider.notifications[index];
        final accent = item.category.color;

        return Material(
          color: surface,
          borderRadius: BorderRadius.circular(18),
          child: InkWell(
            onTap: () => _openNotification(item),
            borderRadius: BorderRadius.circular(18),
            child: Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(18),
                border: Border.all(
                  color: item.isRead ? border : accent.withAlpha(110),
                ),
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Container(
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: accent.withAlpha(28),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Icon(item.category.icon, color: accent, size: 22),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Row(
                          children: <Widget>[
                            Expanded(
                              child: Text(
                                item.title,
                                style: Theme.of(context)
                                    .textTheme
                                    .titleMedium
                                    ?.copyWith(
                                      fontWeight: item.isRead
                                          ? FontWeight.w600
                                          : FontWeight.w700,
                                    ),
                              ),
                            ),
                            if (!item.isRead)
                              Container(
                                width: 8,
                                height: 8,
                                decoration: BoxDecoration(
                                  color: accent,
                                  shape: BoxShape.circle,
                                ),
                              ),
                          ],
                        ),
                        const SizedBox(height: 4),
                        Text(
                          item.message,
                          style: Theme.of(context).textTheme.bodyMedium,
                        ),
                        const SizedBox(height: 8),
                        Text(
                          DateFormatter.formatRelative(item.createdAt),
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}

/// Reusable bottom sheet for editing notification category preferences.
Future<void> showNotificationPreferencesSheet(BuildContext context) async {
  await showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (sheetContext) {
      return const _NotificationPreferencesSheet();
    },
  );
}

class _NotificationPreferencesSheet extends StatefulWidget {
  const _NotificationPreferencesSheet();

  @override
  State<_NotificationPreferencesSheet> createState() =>
      _NotificationPreferencesSheetState();
}

class _NotificationPreferencesSheetState
    extends State<_NotificationPreferencesSheet> {
  late NotificationPreferences _draft;

  @override
  void initState() {
    super.initState();
    _draft = context.read<NotificationsProvider>().preferences;
  }

  Future<void> _save() async {
    final ok = await context
        .read<NotificationsProvider>()
        .updatePreferences(_draft);
    if (!mounted) return;
    Navigator.pop(context);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          ok
              ? 'Notification preferences updated.'
              : 'Saved locally; could not reach server.',
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final saving = context.watch<NotificationsProvider>().isSavingPreferences;

    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 4, 20, 20),
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(
                'Notification Preferences',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 4),
              Text(
                'Choose which recruitment updates trigger push alerts.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
              const SizedBox(height: 12),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Enable Push Notifications'),
                subtitle: const Text('Master toggle for Firebase alerts'),
                value: _draft.pushEnabled,
                onChanged: (val) =>
                    setState(() => _draft = _draft.copyWith(pushEnabled: val)),
              ),
              const Divider(),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('New Job Opportunities'),
                value: _draft.jobOpportunities,
                onChanged: _draft.pushEnabled
                    ? (val) => setState(
                        () => _draft = _draft.copyWith(jobOpportunities: val))
                    : null,
              ),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Internship Opportunities'),
                value: _draft.internshipOpportunities,
                onChanged: _draft.pushEnabled
                    ? (val) => setState(() => _draft =
                        _draft.copyWith(internshipOpportunities: val))
                    : null,
              ),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Interview Invitations'),
                value: _draft.interviewInvitations,
                onChanged: _draft.pushEnabled
                    ? (val) => setState(() => _draft =
                        _draft.copyWith(interviewInvitations: val))
                    : null,
              ),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Online Assessments'),
                value: _draft.onlineAssessments,
                onChanged: _draft.pushEnabled
                    ? (val) => setState(
                        () => _draft = _draft.copyWith(onlineAssessments: val))
                    : null,
              ),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Recruitment Drives'),
                value: _draft.recruitmentDrives,
                onChanged: _draft.pushEnabled
                    ? (val) => setState(
                        () => _draft = _draft.copyWith(recruitmentDrives: val))
                    : null,
              ),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Offer Letters'),
                value: _draft.offerLetters,
                onChanged: _draft.pushEnabled
                    ? (val) => setState(
                        () => _draft = _draft.copyWith(offerLetters: val))
                    : null,
              ),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Application Status Updates'),
                value: _draft.applicationUpdates,
                onChanged: _draft.pushEnabled
                    ? (val) => setState(
                        () => _draft = _draft.copyWith(applicationUpdates: val))
                    : null,
              ),
              const SizedBox(height: 12),
              SizedBox(
                width: double.infinity,
                child: FilledButton(
                  onPressed: saving ? null : _save,
                  child: Text(saving ? 'Saving...' : 'Save Preferences'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
