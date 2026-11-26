import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/accounts_provider.dart';
import '../providers/app_settings_provider.dart';
import '../theme/app_colors.dart';
import '../utils/responsive.dart';
import 'notifications_screen.dart';
import 'onboarding_screen.dart';

/// Screen 9: Application settings, theme, sync, privacy, profile, and logout.
class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key, required this.onOpenAccounts});

  final VoidCallback onOpenAccounts;

  Future<void> _editProfile(
    BuildContext context,
    AppSettingsProvider settings,
  ) async {
    final nameCtrl = TextEditingController(text: settings.profileName);
    final emailCtrl = TextEditingController(text: settings.profileEmail);

    final saved = await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Text('Edit Profile'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              TextField(
                controller: nameCtrl,
                decoration: const InputDecoration(
                  labelText: 'Display Name',
                  prefixIcon: Icon(Icons.person_outline_rounded),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: emailCtrl,
                keyboardType: TextInputType.emailAddress,
                decoration: const InputDecoration(
                  labelText: 'Primary Email',
                  prefixIcon: Icon(Icons.email_outlined),
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
              child: const Text('Save'),
            ),
          ],
        );
      },
    );

    if (saved == true && context.mounted) {
      await settings.updateProfile(
        name: nameCtrl.text,
        email: emailCtrl.text,
      );
    }
    nameCtrl.dispose();
    emailCtrl.dispose();
  }

  Future<void> _editBackendUrl(
    BuildContext context,
    AppSettingsProvider settings,
  ) async {
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
                'Point JobMail to your FastAPI backend URL.',
                style: Theme.of(dialogContext).textTheme.bodySmall,
              ),
              const SizedBox(height: 12),
              TextField(
                controller: urlCtrl,
                keyboardType: TextInputType.url,
                decoration: const InputDecoration(
                  labelText: 'API Base URL',
                  hintText: 'http://10.0.2.2:8000',
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

    if (saved == true && context.mounted) {
      await settings.updateApiBaseUrl(urlCtrl.text);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Backend API URL updated.')),
        );
      }
    }
    urlCtrl.dispose();
  }

  Future<void> _showPrivacyDialog(BuildContext context) async {
    await showDialog<void>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Text('Privacy & Security'),
          content: const Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text('• Read-only Gmail scope via Google OAuth 2.0.'),
              SizedBox(height: 8),
              Text('• Gmail passwords are never requested or stored.'),
              SizedBox(height: 8),
              Text(
                '• OAuth refresh tokens are encrypted at rest on the backend.',
              ),
              SizedBox(height: 8),
              Text(
                '• Minimal email metadata retention; disconnect any account anytime to permanently delete its credentials.',
              ),
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

  Future<void> _confirmLogout(
    BuildContext context,
    AppSettingsProvider settings,
  ) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Text('Log Out of JobMail?'),
          content: const Text(
            'This clears your current app session on this device.',
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

    if (confirmed != true || !context.mounted) return;
    await settings.logout();
    if (!context.mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute<void>(builder: (_) => const OnboardingScreen()),
      (_) => false,
    );
  }

  @override
  Widget build(BuildContext context) {
    final settings = context.watch<AppSettingsProvider>();
    final accounts = context.watch<AccountsProvider>();
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final surface = isDark ? AppColors.darkSurface : AppColors.lightSurface;
    final border = isDark ? AppColors.darkBorder : AppColors.lightBorder;
    final maxWidth = Responsive.contentMaxWidth(context);

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
                                : 'Tap edit to add your primary email',
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                        ],
                      ),
                    ),
                    IconButton(
                      tooltip: 'Edit profile',
                      onPressed: () => _editProfile(context, settings),
                      icon: const Icon(Icons.edit_outlined),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 20),
              Text(
                'Accounts & Sync',
                style: Theme.of(context).textTheme.labelLarge,
              ),
              const SizedBox(height: 8),
              _SettingsSectionCard(
                children: <Widget>[
                  ListTile(
                    leading: const Icon(Icons.alternate_email_rounded),
                    title: const Text('Connected Accounts'),
                    subtitle: Text(
                      '${accounts.accounts.length} Gmail account${accounts.accounts.length == 1 ? '' : 's'} linked',
                    ),
                    trailing: const Icon(Icons.chevron_right_rounded),
                    onTap: onOpenAccounts,
                  ),
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
                ],
              ),
              const SizedBox(height: 20),
              Text(
                'Privacy & Connection',
                style: Theme.of(context).textTheme.labelLarge,
              ),
              const SizedBox(height: 8),
              _SettingsSectionCard(
                children: <Widget>[
                  ListTile(
                    leading: const Icon(Icons.privacy_tip_outlined),
                    title: const Text('Privacy Settings'),
                    subtitle: const Text(
                      'OAuth scope, token encryption, and retention policy',
                    ),
                    trailing: const Icon(Icons.chevron_right_rounded),
                    onTap: () => _showPrivacyDialog(context),
                  ),
                  const Divider(),
                  ListTile(
                    leading: const Icon(Icons.dns_outlined),
                    title: const Text('Backend API Endpoint'),
                    subtitle: Text(
                      settings.apiBaseUrl,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    trailing: const Icon(Icons.edit_outlined, size: 18),
                    onTap: () => _editBackendUrl(context, settings),
                  ),
                ],
              ),
              const SizedBox(height: 24),
              OutlinedButton.icon(
                style: OutlinedButton.styleFrom(
                  foregroundColor: AppColors.error,
                  side: BorderSide(color: AppColors.error.withAlpha(110)),
                ),
                onPressed: () => _confirmLogout(context, settings),
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
    return Container(
      decoration: BoxDecoration(
        color: isDark ? AppColors.darkSurface : AppColors.lightSurface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(
          color: isDark ? AppColors.darkBorder : AppColors.lightBorder,
        ),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(children: children),
    );
  }
}
