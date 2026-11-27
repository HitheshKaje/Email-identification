import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../models/connected_account.dart';
import '../models/security_models.dart';
import '../providers/accounts_provider.dart';
import '../providers/app_settings_provider.dart';
import '../providers/dashboard_provider.dart';
import '../providers/emails_provider.dart';
import '../providers/notifications_provider.dart';
import '../theme/app_colors.dart';
import '../utils/api_config.dart';
import '../utils/date_formatter.dart';
import '../utils/responsive.dart';
import '../widgets/security_dialogs.dart';
import 'auth_screen.dart';
import 'notifications_screen.dart';

/// Screen 9: Application settings, Account Security, Active Sessions, Connected Accounts, Privacy & Logout.
class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key, required this.onOpenAccounts});

  final VoidCallback onOpenAccounts;

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      context.read<AppSettingsProvider>().refreshProfile();
      final accounts = context.read<AccountsProvider>();
      if (accounts.accounts.isEmpty) {
        accounts.loadAccounts();
      }
    });
  }

  Future<void> _editProfile(AppSettingsProvider settings) async {
    final nameCtrl = TextEditingController(text: settings.profileName);
    final saved = await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Text('Edit Profile'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              TextField(
                controller: nameCtrl,
                decoration: const InputDecoration(
                  labelText: 'Display Name',
                  prefixIcon: Icon(Icons.person_outline_rounded),
                ),
              ),
              const SizedBox(height: 12),
              Text(
                'Primary Email: ${settings.profileEmail.isNotEmpty ? settings.profileEmail : 'Not set'}',
                style: Theme.of(dialogContext).textTheme.bodySmall,
              ),
            ],
          ),
          actions: <Widget>[
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(dialogContext, true),
              child: const Text('Save'),
            ),
          ],
        );
      },
    );

    if (saved == true && mounted) {
      await settings.updateProfile(name: nameCtrl.text);
    }
    nameCtrl.dispose();
  }

  Future<void> _editBackendUrl(AppSettingsProvider settings) async {
    final urlCtrl = TextEditingController(text: settings.apiBaseUrl);
    final saved = await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Text('Backend Server URL'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(
                ApiConfig.allowLocalHttpInCurrentBuild
                    ? 'Point JobMail to your HTTPS API URL or local LAN backend during development.'
                    : 'Point JobMail to your HTTPS production FastAPI backend URL.',
                style: Theme.of(dialogContext).textTheme.bodySmall,
              ),
              const SizedBox(height: 12),
              TextField(
                controller: urlCtrl,
                keyboardType: TextInputType.url,
                decoration: InputDecoration(
                  labelText: 'API Base URL',
                  hintText: ApiConfig.endpointHint,
                ),
              ),
            ],
          ),
          actions: <Widget>[
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(dialogContext, true),
              child: const Text('Update'),
            ),
          ],
        );
      },
    );

    if (saved == true && mounted) {
      final ok = await settings.updateApiBaseUrl(urlCtrl.text);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              ok
                  ? 'Backend API URL updated.'
                  : (ApiConfig.allowLocalHttpInCurrentBuild
                        ? 'Invalid URL. Use HTTPS or a local LAN/loopback HTTP address.'
                        : 'Invalid URL. Release builds require an HTTPS backend URL.'),
            ),
          ),
        );
      }
    }
    urlCtrl.dispose();
  }

  Future<void> _showPrivacyDialog(AppSettingsProvider settings) async {
    PrivacyOverview? overview;
    try {
      overview = await settings.getPrivacyOverview();
    } catch (_) {}
    if (!mounted) return;

    await showDialog<void>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Text('Privacy Policy & Data Protection'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              const Text('• Read-only Gmail scope (gmail.readonly) via OAuth 2.0 PKCE.'),
              const SizedBox(height: 8),
              const Text('• Gmail passwords are never requested or stored.'),
              const SizedBox(height: 8),
              const Text('• OAuth refresh tokens & sensitive email fields encrypted at rest via MultiFernet.'),
              const SizedBox(height: 8),
              const Text('• Strict user isolation & Google Limited Use compliance (no cross-user model training).'),
              if (overview != null) ...<Widget>[
                const Divider(height: 20),
                Text(
                  'Stored records: ${overview.emailsStored} email(s), '
                  '${overview.connectedAccounts} account(s), '
                  '${overview.notificationsStored} alert(s) • Retention: ${overview.dataRetentionDays} days',
                  style: Theme.of(dialogContext).textTheme.bodySmall,
                ),
              ],
            ],
          ),
          actions: <Widget>[
            FilledButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('Close'),
            ),
          ],
        );
      },
    );
  }

  Future<void> _disconnectAccountQuick(
    ConnectedAccount account,
    AccountsProvider accounts,
  ) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Text('Revoke & Disconnect Gmail?'),
          content: Text(
            'This revokes Google OAuth tokens for ${account.emailAddress} and permanently deletes its synced emails from JobMail.',
          ),
          actions: <Widget>[
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              style: FilledButton.styleFrom(backgroundColor: AppColors.error),
              onPressed: () => Navigator.pop(dialogContext, true),
              child: const Text('Revoke & Disconnect'),
            ),
          ],
        );
      },
    );
    if (confirmed != true || !mounted) return;
    final ok = await accounts.disconnectAccount(account.id);
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
              ? 'Revoked & disconnected ${account.emailAddress}.'
              : (accounts.actionError ?? 'Disconnect failed.'),
        ),
      ),
    );
  }

  Future<void> _confirmLogout(AppSettingsProvider settings) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Text('Log Out of JobMail?'),
          content: const Text(
            'This signs out and revokes your current session on this device.',
          ),
          actions: <Widget>[
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              style: FilledButton.styleFrom(backgroundColor: AppColors.error),
              onPressed: () => Navigator.pop(dialogContext, true),
              child: const Text('Logout'),
            ),
          ],
        );
      },
    );

    if (confirmed != true || !mounted) return;
    await settings.logout();
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute<void>(builder: (_) => const AuthScreen()),
      (_) => false,
    );
  }

  @override
  Widget build(BuildContext context) {
    final settings = context.watch<AppSettingsProvider>();
    final accounts = context.watch<AccountsProvider>();
    final user = settings.currentUser;
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final surface = isDark ? AppColors.darkSurface : AppColors.lightSurface;
    final border = isDark ? AppColors.darkBorder : AppColors.lightBorder;
    final maxWidth = Responsive.contentMaxWidth(context);
    final retentionDays = user?.dataRetentionDays ?? 180;
    const allowedRetentions = <int>[30, 90, 180, 365];
    final selectedRetention =
        allowedRetentions.contains(retentionDays) ? retentionDays : 180;

    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: Align(
        alignment: Alignment.topCenter,
        child: ConstrainedBox(
          constraints: BoxConstraints(maxWidth: maxWidth),
          child: ListView(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
            children: <Widget>[
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: surface,
                  borderRadius: BorderRadius.circular(18),
                  border: Border.all(color: border),
                ),
                child: Row(
                  children: <Widget>[
                    CircleAvatar(
                      radius: 26,
                      backgroundColor: AppColors.primary.withAlpha(28),
                      child: Text(
                        settings.profileName.isNotEmpty
                            ? settings.profileName[0].toUpperCase()
                            : 'J',
                        style: const TextStyle(
                          color: AppColors.primary,
                          fontSize: 20,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          Text(
                            settings.profileName,
                            style: Theme.of(context).textTheme.titleMedium,
                          ),
                          const SizedBox(height: 2),
                          Text(
                            settings.profileEmail.isNotEmpty
                                ? settings.profileEmail
                                : 'Signed in user',
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                        ],
                      ),
                    ),
                    IconButton(
                      tooltip: 'Edit profile',
                      onPressed: () => _editProfile(settings),
                      icon: const Icon(Icons.edit_outlined),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 20),
              Text(
                'Account Security',
                style: Theme.of(context).textTheme.labelLarge,
              ),
              const SizedBox(height: 8),
              _SettingsSectionCard(
                children: <Widget>[
                  ListTile(
                    leading: const Icon(Icons.password_rounded),
                    title: const Text('Change Password'),
                    subtitle: const Text('Argon2id protected • revokes other sessions'),
                    trailing: const Icon(Icons.chevron_right_rounded),
                    onTap: () => showChangePasswordDialog(context, settings),
                  ),
                  const Divider(),
                  ListTile(
                    leading: const Icon(Icons.phonelink_lock_rounded),
                    title: const Text('Multi-Factor Authentication (MFA)'),
                    subtitle: Text(
                      user?.mfaEnabled == true
                          ? 'Enabled via authenticator app'
                          : 'Off — add TOTP 2FA protection',
                    ),
                    trailing: Chip(
                      label: Text(user?.mfaEnabled == true ? 'Enabled' : 'Enable'),
                    ),
                    onTap: () => showMfaManagementDialog(context, settings),
                  ),
                  const Divider(),
                  ListTile(
                    leading: const Icon(Icons.mark_email_read_outlined),
                    title: const Text('Email Verification Status'),
                    subtitle: Text(
                      user?.emailVerified == true
                          ? 'Email address verified'
                          : 'Unverified — tap to verify ownership',
                    ),
                    trailing: Icon(
                      user?.emailVerified == true
                          ? Icons.verified_rounded
                          : Icons.chevron_right_rounded,
                      color: user?.emailVerified == true ? AppColors.success : null,
                    ),
                    onTap: user?.emailVerified == true
                        ? null
                        : () => showEmailVerificationDialog(context, settings),
                  ),
                  const Divider(),
                  ListTile(
                    leading: const Icon(Icons.schedule_outlined),
                    title: const Text('Last Login Information'),
                    subtitle: Text(
                      user?.lastLoginAt != null
                          ? '${DateFormatter.formatShortDateTime(user!.lastLoginAt!)}'
                              '${user.lastLoginIp != null ? ' • IP ${user.lastLoginIp}' : ''}'
                          : 'Current session active',
                    ),
                  ),
                  const Divider(),
                  ListTile(
                    leading: const Icon(Icons.shield_outlined),
                    title: const Text('Security Activity Log'),
                    subtitle: const Text('Inspect sign-ins, MFA, and OAuth events'),
                    trailing: const Icon(Icons.chevron_right_rounded),
                    onTap: () => showSecurityActivitySheet(context, settings),
                  ),
                ],
              ),
              const SizedBox(height: 20),
              Text(
                'Active Sessions',
                style: Theme.of(context).textTheme.labelLarge,
              ),
              const SizedBox(height: 8),
              _SettingsSectionCard(
                children: <Widget>[
                  ListTile(
                    leading: const Icon(Icons.devices_rounded),
                    title: const Text('Manage Active Sessions'),
                    subtitle: const Text('Inspect devices, last active time, or revoke access'),
                    trailing: const Icon(Icons.chevron_right_rounded),
                    onTap: () => showActiveSessionsSheet(context, settings),
                  ),
                  const Divider(),
                  ListTile(
                    leading: const Icon(Icons.logout_rounded, color: AppColors.error),
                    title: const Text('Logout from All Devices'),
                    subtitle: const Text('Immediately invalidate every active session'),
                    onTap: () async {
                      await settings.logoutAllDevices();
                      if (!context.mounted) return;
                      Navigator.of(context).pushAndRemoveUntil(
                        MaterialPageRoute<void>(builder: (_) => const AuthScreen()),
                        (_) => false,
                      );
                    },
                  ),
                ],
              ),
              const SizedBox(height: 20),
              Text(
                'Connected Accounts',
                style: Theme.of(context).textTheme.labelLarge,
              ),
              const SizedBox(height: 8),
              _SettingsSectionCard(
                children: <Widget>[
                  ListTile(
                    leading: const Icon(Icons.alternate_email_rounded),
                    title: const Text('Manage Gmail Accounts'),
                    subtitle: Text(
                      '${accounts.accounts.length} Gmail account${accounts.accounts.length == 1 ? '' : 's'} linked (read-only OAuth)',
                    ),
                    trailing: const Icon(Icons.chevron_right_rounded),
                    onTap: widget.onOpenAccounts,
                  ),
                  for (final account in accounts.accounts) ...<Widget>[
                    const Divider(),
                    ListTile(
                      leading: Icon(
                        Icons.mail_outline_rounded,
                        color: account.syncStatus.color,
                      ),
                      title: Text(account.emailAddress),
                      subtitle: Text(
                        '${account.syncStatus.label} • '
                        '${account.lastSyncedAt != null ? 'Synced ${DateFormatter.formatRelative(account.lastSyncedAt!)}' : 'Not synced yet'}',
                      ),
                      trailing: TextButton(
                        onPressed: () => _disconnectAccountQuick(account, accounts),
                        child: const Text('Revoke'),
                      ),
                    ),
                  ],
                  const Divider(),
                  SwitchListTile(
                    secondary: const Icon(Icons.sync_rounded),
                    title: const Text('Automatic Synchronization'),
                    subtitle: const Text(
                      'Periodically fetch and classify new emails',
                    ),
                    value: settings.autoSyncEnabled,
                    onChanged: settings.setAutoSyncEnabled,
                  ),
                  if (settings.autoSyncEnabled) ...<Widget>[
                    const Divider(),
                    ListTile(
                      leading: const Icon(Icons.timer_outlined),
                      title: const Text('Sync Frequency'),
                      trailing: DropdownButton<int>(
                        value: settings.syncIntervalMinutes,
                        underline: const SizedBox.shrink(),
                        items: const <DropdownMenuItem<int>>[
                          DropdownMenuItem<int>(
                            value: 15,
                            child: Text('Every 15 min'),
                          ),
                          DropdownMenuItem<int>(
                            value: 30,
                            child: Text('Every 30 min'),
                          ),
                          DropdownMenuItem<int>(
                            value: 60,
                            child: Text('Every 1 hr'),
                          ),
                        ],
                        onChanged: (val) {
                          if (val != null) {
                            settings.setSyncIntervalMinutes(val);
                          }
                        },
                      ),
                    ),
                  ],
                ],
              ),
              const SizedBox(height: 20),
              Text(
                'Privacy',
                style: Theme.of(context).textTheme.labelLarge,
              ),
              const SizedBox(height: 8),
              _SettingsSectionCard(
                children: <Widget>[
                  ListTile(
                    leading: const Icon(Icons.auto_delete_outlined),
                    title: const Text('Data Retention Policy'),
                    subtitle: const Text('Auto-purge emails older than selected window'),
                    trailing: DropdownButton<int>(
                      value: selectedRetention,
                      underline: const SizedBox.shrink(),
                      items: const <DropdownMenuItem<int>>[
                        DropdownMenuItem<int>(value: 30, child: Text('30 days')),
                        DropdownMenuItem<int>(value: 90, child: Text('90 days')),
                        DropdownMenuItem<int>(value: 180, child: Text('180 days')),
                        DropdownMenuItem<int>(value: 365, child: Text('365 days')),
                      ],
                      onChanged: (val) async {
                        if (val != null) {
                          await settings.updateDataRetention(val);
                        }
                      },
                    ),
                  ),
                  const Divider(),
                  ListTile(
                    leading: const Icon(Icons.download_outlined),
                    title: const Text('Download My Data'),
                    subtitle: const Text('Export profile, accounts, and emails as JSON'),
                    trailing: const Icon(Icons.chevron_right_rounded),
                    onTap: () => showExportDataDialog(context, settings),
                  ),
                  const Divider(),
                  ListTile(
                    leading: const Icon(Icons.privacy_tip_outlined),
                    title: const Text('Privacy Policy & Encryption'),
                    subtitle: const Text('Read-only OAuth scope, MultiFernet, Limited Use'),
                    trailing: const Icon(Icons.chevron_right_rounded),
                    onTap: () => _showPrivacyDialog(settings),
                  ),
                  const Divider(),
                  ListTile(
                    leading: const Icon(Icons.delete_sweep_outlined, color: AppColors.error),
                    title: const Text('Delete Associated Gmail Data'),
                    subtitle: const Text('Erase synced emails and alerts from JobMail'),
                    onTap: () => showDeleteGmailDataDialog(context, settings),
                  ),
                  const Divider(),
                  ListTile(
                    leading: const Icon(Icons.person_remove_outlined, color: AppColors.error),
                    title: const Text('Delete My Account'),
                    subtitle: const Text('Permanently delete account and revoke OAuth'),
                    onTap: () => showDeleteAccountDialog(context, settings),
                  ),
                ],
              ),
              const SizedBox(height: 20),
              Text(
                'Preferences & Appearance',
                style: Theme.of(context).textTheme.labelLarge,
              ),
              const SizedBox(height: 8),
              _SettingsSectionCard(
                children: <Widget>[
                  ListTile(
                    leading: const Icon(Icons.notifications_outlined),
                    title: const Text('Notification Preferences'),
                    subtitle: const Text(
                      'Configure job, interview, and offer alerts',
                    ),
                    trailing: const Icon(Icons.chevron_right_rounded),
                    onTap: () => showNotificationPreferencesSheet(context),
                  ),
                  const Divider(),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 12, 16, 14),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Row(
                          children: <Widget>[
                            const Icon(Icons.palette_outlined, size: 22),
                            const SizedBox(width: 14),
                            Text(
                              'Theme Mode',
                              style: Theme.of(context).textTheme.titleMedium,
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        SizedBox(
                          width: double.infinity,
                          child: SegmentedButton<ThemeMode>(
                            segments: const <ButtonSegment<ThemeMode>>[
                              ButtonSegment<ThemeMode>(
                                value: ThemeMode.system,
                                label: Text('System'),
                                icon: Icon(Icons.brightness_auto_outlined),
                              ),
                              ButtonSegment<ThemeMode>(
                                value: ThemeMode.light,
                                label: Text('Light'),
                                icon: Icon(Icons.light_mode_outlined),
                              ),
                              ButtonSegment<ThemeMode>(
                                value: ThemeMode.dark,
                                label: Text('Dark'),
                                icon: Icon(Icons.dark_mode_outlined),
                              ),
                            ],
                            selected: <ThemeMode>{settings.themeMode},
                            onSelectionChanged: (selection) {
                              if (selection.isNotEmpty) {
                                settings.setThemeMode(selection.first);
                              }
                            },
                          ),
                        ),
                      ],
                    ),
                  ),
                  if (ApiConfig.canCustomizeApiUrl) ...<Widget>[
                    const Divider(),
                    ListTile(
                      leading: const Icon(Icons.dns_outlined),
                      title: const Text('Backend API Endpoint (Dev)'),
                      subtitle: Text(
                        settings.apiBaseUrl,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      trailing: const Icon(Icons.edit_outlined, size: 18),
                      onTap: () => _editBackendUrl(settings),
                    ),
                  ],
                ],
              ),
              const SizedBox(height: 24),
              OutlinedButton.icon(
                style: OutlinedButton.styleFrom(
                  foregroundColor: AppColors.error,
                  side: BorderSide(color: AppColors.error.withAlpha(110)),
                ),
                onPressed: () => _confirmLogout(settings),
                icon: const Icon(Icons.logout_rounded),
                label: const Text('Logout'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SettingsSectionCard extends StatelessWidget {
  const _SettingsSectionCard({required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return Material(
      color: isDark ? AppColors.darkSurface : AppColors.lightSurface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(18),
        side: BorderSide(
          color: isDark ? AppColors.darkBorder : AppColors.lightBorder,
        ),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(children: children),
    );
  }
}
