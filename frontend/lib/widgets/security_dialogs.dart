import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../models/security_models.dart';
import '../providers/accounts_provider.dart';
import '../providers/app_settings_provider.dart';
import '../providers/dashboard_provider.dart';
import '../providers/emails_provider.dart';
import '../providers/notifications_provider.dart';
import '../screens/auth_screen.dart';
import '../services/api_exceptions.dart';
import '../theme/app_colors.dart';
import '../utils/date_formatter.dart';

String _formatError(Object err) =>
    err is ApiException ? err.message : 'Unable to complete security action.';

Future<void> showChangePasswordDialog(
  BuildContext context,
  AppSettingsProvider settings,
) async {
  final currentCtrl = TextEditingController();
  final nextCtrl = TextEditingController();
  String? errorText;
  bool saving = false;

  final updated = await showDialog<bool>(
    context: context,
    builder: (dialogContext) {
      return StatefulBuilder(
        builder: (context, setState) {
          return AlertDialog(
            title: const Text('Change Password'),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                const Text(
                  'Use at least 8 characters with uppercase, lowercase, a digit, and a symbol. Other sessions will be signed out.',
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: currentCtrl,
                  obscureText: true,
                  decoration: const InputDecoration(
                    labelText: 'Current Password',
                  ),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: nextCtrl,
                  obscureText: true,
                  decoration: const InputDecoration(
                    labelText: 'New Strong Password',
                  ),
                ),
                if (errorText != null) ...<Widget>[
                  const SizedBox(height: 10),
                  Text(
                    errorText!,
                    style: const TextStyle(color: AppColors.error, fontSize: 12),
                  ),
                ],
              ],
            ),
            actions: <Widget>[
              TextButton(
                onPressed: saving ? null : () => Navigator.pop(dialogContext, false),
                child: const Text('Cancel'),
              ),
              FilledButton(
                onPressed: saving
                    ? null
                    : () async {
                        setState(() {
                          saving = true;
                          errorText = null;
                        });
                        try {
                          await settings.changePassword(
                            currentPassword: currentCtrl.text,
                            newPassword: nextCtrl.text,
                          );
                          if (dialogContext.mounted) {
                            Navigator.pop(dialogContext, true);
                          }
                        } catch (e) {
                          setState(() {
                            saving = false;
                            errorText = _formatError(e);
                          });
                        }
                      },
                child: Text(saving ? 'Updating...' : 'Update Password'),
              ),
            ],
          );
        },
      );
    },
  );

  currentCtrl.dispose();
  nextCtrl.dispose();
  if (updated == true && context.mounted) {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Password changed and other active sessions signed out.'),
      ),
    );
  }
}

Future<void> showEmailVerificationDialog(
  BuildContext context,
  AppSettingsProvider settings,
) async {
  final tokenCtrl = TextEditingController();
  bool requested = false;
  bool busy = false;
  String? errorText;

  await showDialog<void>(
    context: context,
    builder: (dialogContext) {
      return StatefulBuilder(
        builder: (context, setState) {
          return AlertDialog(
            title: const Text('Verify Email Address'),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                Text(
                  'Account email: ${settings.profileEmail.isNotEmpty ? settings.profileEmail : 'Not set'}',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
                const SizedBox(height: 12),
                OutlinedButton.icon(
                  onPressed: busy
                      ? null
                      : () async {
                          setState(() {
                            busy = true;
                            errorText = null;
                          });
                          try {
                            await settings.requestEmailVerification();
                            setState(() {
                              requested = true;
                              busy = false;
                            });
                          } catch (e) {
                            setState(() {
                              busy = false;
                              errorText = _formatError(e);
                            });
                          }
                        },
                  icon: const Icon(Icons.mark_email_read_outlined, size: 18),
                  label: Text(
                    requested ? 'Verification Email Sent' : 'Send Verification Email',
                  ),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: tokenCtrl,
                  decoration: const InputDecoration(
                    labelText: 'Verification Token',
                    hintText: 'Paste token from verification email',
                  ),
                ),
                if (errorText != null) ...<Widget>[
                  const SizedBox(height: 10),
                  Text(
                    errorText!,
                    style: const TextStyle(color: AppColors.error, fontSize: 12),
                  ),
                ],
              ],
            ),
            actions: <Widget>[
              TextButton(
                onPressed: busy ? null : () => Navigator.pop(dialogContext),
                child: const Text('Close'),
              ),
              FilledButton(
                onPressed: busy
                    ? null
                    : () async {
                        if (tokenCtrl.text.trim().isEmpty) return;
                        setState(() {
                          busy = true;
                          errorText = null;
                        });
                        try {
                          await settings.confirmEmailVerification(tokenCtrl.text);
                          if (dialogContext.mounted) {
                            Navigator.pop(dialogContext);
                          }
                        } catch (e) {
                          setState(() {
                            busy = false;
                            errorText = _formatError(e);
                          });
                        }
                      },
                child: const Text('Verify'),
              ),
            ],
          );
        },
      );
    },
  );
  tokenCtrl.dispose();
}

Future<void> showMfaManagementDialog(
  BuildContext context,
  AppSettingsProvider settings,
) async {
  final isEnabled = settings.currentUser?.mfaEnabled == true;
  if (isEnabled) {
    await _showDisableMfaDialog(context, settings);
    return;
  }

  MfaSetupInfo? setup;
  try {
    setup = await settings.setupMfa();
  } catch (e) {
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(_formatError(e))),
      );
    }
    return;
  }
  if (setup == null || !context.mounted) return;

  final codeCtrl = TextEditingController();
  bool busy = false;
  String? errorText;

  final enabled = await showDialog<bool>(
    context: context,
    builder: (dialogContext) {
      return StatefulBuilder(
        builder: (context, setState) {
          return AlertDialog(
            title: const Text('Enable Two-Factor Authentication'),
            content: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: <Widget>[
                  const Text(
                    '1. Add this secret key to Google Authenticator, Authy, or 1Password:',
                  ),
                  const SizedBox(height: 8),
                  SelectableText(
                    setup!.secret,
                    style: const TextStyle(
                      fontWeight: FontWeight.w700,
                      letterSpacing: 1.1,
                    ),
                  ),
                  const SizedBox(height: 12),
                  const Text(
                    '2. Save these one-time recovery codes in a safe place:',
                  ),
                  const SizedBox(height: 6),
                  Container(
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(10),
                      color: AppColors.primary.withAlpha(14),
                    ),
                    child: SelectableText(
                      setup.recoveryCodes.join('   '),
                      style: const TextStyle(fontSize: 12),
                    ),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: codeCtrl,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(
                      labelText: '6-digit Authenticator Code',
                    ),
                  ),
                  if (errorText != null) ...<Widget>[
                    const SizedBox(height: 8),
                    Text(
                      errorText!,
                      style: const TextStyle(color: AppColors.error, fontSize: 12),
                    ),
                  ],
                ],
              ),
            ),
            actions: <Widget>[
              TextButton(
                onPressed: busy ? null : () => Navigator.pop(dialogContext, false),
                child: const Text('Cancel'),
              ),
              FilledButton(
                onPressed: busy
                    ? null
                    : () async {
                        setState(() {
                          busy = true;
                          errorText = null;
                        });
                        try {
                          await settings.enableMfa(codeCtrl.text);
                          if (dialogContext.mounted) {
                            Navigator.pop(dialogContext, true);
                          }
                        } catch (e) {
                          setState(() {
                            busy = false;
                            errorText = _formatError(e);
                          });
                        }
                      },
                child: Text(busy ? 'Enabling...' : 'Confirm & Enable'),
              ),
            ],
          );
        },
      );
    },
  );

  codeCtrl.dispose();
  if (enabled == true && context.mounted) {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Two-factor authentication enabled.')),
    );
  }
}

Future<void> _showDisableMfaDialog(
  BuildContext context,
  AppSettingsProvider settings,
) async {
  final passwordCtrl = TextEditingController();
  final codeCtrl = TextEditingController();
  bool busy = false;
  String? errorText;

  final disabled = await showDialog<bool>(
    context: context,
    builder: (dialogContext) {
      return StatefulBuilder(
        builder: (context, setState) {
          return AlertDialog(
            title: const Text('Disable Multi-Factor Auth'),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                TextField(
                  controller: passwordCtrl,
                  obscureText: true,
                  decoration: const InputDecoration(labelText: 'Account Password'),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: codeCtrl,
                  decoration: const InputDecoration(
                    labelText: 'Authenticator or Recovery Code',
                  ),
                ),
                if (errorText != null) ...<Widget>[
                  const SizedBox(height: 8),
                  Text(
                    errorText!,
                    style: const TextStyle(color: AppColors.error, fontSize: 12),
                  ),
                ],
              ],
            ),
            actions: <Widget>[
              TextButton(
                onPressed: busy ? null : () => Navigator.pop(dialogContext, false),
                child: const Text('Cancel'),
              ),
              FilledButton(
                style: FilledButton.styleFrom(backgroundColor: AppColors.error),
                onPressed: busy
                    ? null
                    : () async {
                        setState(() {
                          busy = true;
                          errorText = null;
                        });
                        try {
                          await settings.disableMfa(
                            password: passwordCtrl.text,
                            code: codeCtrl.text,
                          );
                          if (dialogContext.mounted) {
                            Navigator.pop(dialogContext, true);
                          }
                        } catch (e) {
                          setState(() {
                            busy = false;
                            errorText = _formatError(e);
                          });
                        }
                      },
                child: Text(busy ? 'Disabling...' : 'Disable MFA'),
              ),
            ],
          );
        },
      );
    },
  );
  passwordCtrl.dispose();
  codeCtrl.dispose();
  if (disabled == true && context.mounted) {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Multi-factor authentication disabled.')),
    );
  }
}

Future<void> showActiveSessionsSheet(
  BuildContext context,
  AppSettingsProvider settings,
) async {
  await showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (sheetContext) {
      List<SessionInfo>? sessions;
      String? errorText;
      bool loading = true;

      return StatefulBuilder(
        builder: (context, setState) {
          Future<void> load() async {
            setState(() {
              loading = true;
              errorText = null;
            });
            try {
              final list = await settings.getActiveSessions();
              setState(() {
                sessions = list;
                loading = false;
              });
            } catch (e) {
              setState(() {
                errorText = _formatError(e);
                loading = false;
              });
            }
          }

          if (loading && sessions == null && errorText == null) {
            load();
          }

          return SafeArea(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 4, 16, 20),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: <Widget>[
                  Text(
                    'Active Sessions',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  const SizedBox(height: 6),
                  const Text(
                    'Review devices currently signed into your JobMail account.',
                  ),
                  const SizedBox(height: 12),
                  if (loading)
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 24),
                      child: Center(child: CircularProgressIndicator()),
                    )
                  else if (errorText != null)
                    Text(errorText!, style: const TextStyle(color: AppColors.error))
                  else if ((sessions ?? const <SessionInfo>[]).isEmpty)
                    const Text('No active sessions found.')
                  else
                    ConstrainedBox(
                      constraints: const BoxConstraints(maxHeight: 300),
                      child: ListView.separated(
                        shrinkWrap: true,
                        itemCount: sessions!.length,
                        separatorBuilder: (_, __) => const Divider(),
                        itemBuilder: (context, index) {
                          final item = sessions![index];
                          return ListTile(
                            contentPadding: EdgeInsets.zero,
                            leading: Icon(
                              item.isCurrent
                                  ? Icons.devices_rounded
                                  : Icons.laptop_mac_outlined,
                              color: item.isCurrent ? AppColors.primary : null,
                            ),
                            title: Row(
                              children: <Widget>[
                                Expanded(
                                  child: Text(
                                    item.deviceInfo,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                ),
                                if (item.isCurrent)
                                  Container(
                                    padding: const EdgeInsets.symmetric(
                                      horizontal: 8,
                                      vertical: 2,
                                    ),
                                    decoration: BoxDecoration(
                                      color: AppColors.success.withAlpha(24),
                                      borderRadius: BorderRadius.circular(12),
                                    ),
                                    child: const Text(
                                      'Current',
                                      style: TextStyle(
                                        fontSize: 11,
                                        color: AppColors.success,
                                        fontWeight: FontWeight.w700,
                                      ),
                                    ),
                                  ),
                              ],
                            ),
                            subtitle: Text(
                              'Last active ${DateFormatter.formatRelative(item.lastActiveAt)}'
                              '${item.ipAddress != null ? ' • ${item.ipAddress}' : ''}',
                            ),
                            trailing: item.isCurrent
                                ? null
                                : TextButton(
                                    onPressed: () async {
                                      await settings.revokeSession(item.id);
                                      await load();
                                    },
                                    child: const Text('Revoke'),
                                  ),
                          );
                        },
                      ),
                    ),
                  const SizedBox(height: 12),
                  OutlinedButton.icon(
                    style: OutlinedButton.styleFrom(
                      foregroundColor: AppColors.error,
                    ),
                    onPressed: () async {
                      Navigator.pop(sheetContext);
                      await settings.logoutAllDevices();
                      if (context.mounted) {
                        Navigator.of(context).pushAndRemoveUntil(
                          MaterialPageRoute<void>(
                            builder: (_) => const AuthScreen(),
                          ),
                          (_) => false,
                        );
                      }
                    },
                    icon: const Icon(Icons.logout_rounded),
                    label: const Text('Logout from All Devices'),
                  ),
                ],
              ),
            ),
          );
        },
      );
    },
  );
}

Future<void> showSecurityActivitySheet(
  BuildContext context,
  AppSettingsProvider settings,
) async {
  List<SecurityEventItem> events = const <SecurityEventItem>[];
  String? error;
  try {
    events = await settings.getSecurityEvents();
  } catch (e) {
    error = _formatError(e);
  }
  if (!context.mounted) return;

  await showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (sheetContext) {
      return SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              Text(
                'Security Activity',
                style: Theme.of(sheetContext).textTheme.titleLarge,
              ),
              const SizedBox(height: 10),
              if (error != null)
                Text(error, style: const TextStyle(color: AppColors.error))
              else if (events.isEmpty)
                const Text('No security events recorded yet.')
              else
                ConstrainedBox(
                  constraints: const BoxConstraints(maxHeight: 340),
                  child: ListView.separated(
                    shrinkWrap: true,
                    itemCount: events.length,
                    separatorBuilder: (_, __) => const Divider(),
                    itemBuilder: (context, idx) {
                      final ev = events[idx];
                      return ListTile(
                        contentPadding: EdgeInsets.zero,
                        leading: Icon(
                          ev.alert
                              ? Icons.warning_amber_rounded
                              : Icons.verified_user_outlined,
                          color: ev.alert ? AppColors.error : AppColors.primary,
                        ),
                        title: Text(ev.eventType),
                        subtitle: Text(
                          '${ev.summary}\n${DateFormatter.formatShortDateTime(ev.createdAt)}'
                          '${ev.ipAddress != null ? ' • ${ev.ipAddress}' : ''}',
                        ),
                      );
                    },
                  ),
                ),
            ],
          ),
        ),
      );
    },
  );
}

Future<void> showExportDataDialog(
  BuildContext context,
  AppSettingsProvider settings,
) async {
  Map<String, dynamic>? payload;
  try {
    payload = await settings.exportMyData();
  } catch (e) {
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(_formatError(e))),
      );
    }
    return;
  }
  if (!context.mounted) return;
  final prettyJson = const JsonEncoder.withIndent('  ').convert(payload);

  await showDialog<void>(
    context: context,
    builder: (dialogContext) {
      return AlertDialog(
        title: const Text('Download My Data (JSON)'),
        content: SizedBox(
          width: 480,
          height: 300,
          child: SingleChildScrollView(
            child: SelectableText(
              prettyJson,
              style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
            ),
          ),
        ),
        actions: <Widget>[
          TextButton.icon(
            onPressed: () {
              Clipboard.setData(ClipboardData(text: prettyJson));
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Exported data copied to clipboard.')),
              );
            },
            icon: const Icon(Icons.copy_rounded, size: 18),
            label: const Text('Copy JSON'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: const Text('Close'),
          ),
        ],
      );
    },
  );
}

Future<void> showDeleteGmailDataDialog(
  BuildContext context,
  AppSettingsProvider settings,
) async {
  bool disconnectAccounts = false;
  final confirmed = await showDialog<bool>(
    context: context,
    builder: (dialogContext) {
      return StatefulBuilder(
        builder: (context, setState) {
          return AlertDialog(
            title: const Text('Delete Associated Gmail Data?'),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                const Text(
                  'This permanently removes all synced emails, alerts, sync history, and classification feedback stored in JobMail (your Gmail mailbox on Google is never modified).',
                ),
                const SizedBox(height: 12),
                CheckboxListTile(
                  contentPadding: EdgeInsets.zero,
                  value: disconnectAccounts,
                  onChanged: (val) =>
                      setState(() => disconnectAccounts = val ?? false),
                  title: const Text('Also revoke & disconnect Gmail accounts'),
                ),
              ],
            ),
            actions: <Widget>[
              TextButton(
                onPressed: () => Navigator.pop(dialogContext, false),
                child: const Text('Cancel'),
              ),
              FilledButton(
                style: FilledButton.styleFrom(backgroundColor: AppColors.error),
                onPressed: () => Navigator.pop(dialogContext, true),
                child: const Text('Delete Gmail Data'),
              ),
            ],
          );
        },
      );
    },
  );

  if (confirmed != true || !context.mounted) return;
  try {
    final msg = await settings.deleteGmailData(
      disconnectAccounts: disconnectAccounts,
    );
    if (!context.mounted) return;
    await Future.wait(<Future<void>>[
      context.read<AccountsProvider>().loadAccounts(),
      context.read<DashboardProvider>().loadDashboard(),
      context.read<EmailsProvider>().loadEmails(),
      context.read<NotificationsProvider>().loadNotifications(),
    ]);
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
    }
  } catch (e) {
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(_formatError(e))),
      );
    }
  }
}

Future<void> showDeleteAccountDialog(
  BuildContext context,
  AppSettingsProvider settings,
) async {
  final passwordCtrl = TextEditingController();
  final confirmCtrl = TextEditingController();
  bool busy = false;
  String? errorText;

  final deleted = await showDialog<bool>(
    context: context,
    builder: (dialogContext) {
      return StatefulBuilder(
        builder: (context, setState) {
          return AlertDialog(
            title: const Text('Permanently Delete Account?'),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                const Text(
                  'This revokes all Gmail OAuth connections and permanently erases your account, sessions, emails, and notifications.',
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: passwordCtrl,
                  obscureText: true,
                  decoration: const InputDecoration(labelText: 'Password'),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: confirmCtrl,
                  decoration: const InputDecoration(
                    labelText: 'Type DELETE to confirm',
                  ),
                ),
                if (errorText != null) ...<Widget>[
                  const SizedBox(height: 8),
                  Text(
                    errorText!,
                    style: const TextStyle(color: AppColors.error, fontSize: 12),
                  ),
                ],
              ],
            ),
            actions: <Widget>[
              TextButton(
                onPressed: busy ? null : () => Navigator.pop(dialogContext, false),
                child: const Text('Cancel'),
              ),
              FilledButton(
                style: FilledButton.styleFrom(backgroundColor: AppColors.error),
                onPressed: busy
                    ? null
                    : () async {
                        if (confirmCtrl.text.trim().toUpperCase() != 'DELETE') {
                          setState(() => errorText = 'Type DELETE to confirm.');
                          return;
                        }
                        setState(() {
                          busy = true;
                          errorText = null;
                        });
                        try {
                          await settings.deleteAccount(
                            password: passwordCtrl.text,
                          );
                          if (dialogContext.mounted) {
                            Navigator.pop(dialogContext, true);
                          }
                        } catch (e) {
                          setState(() {
                            busy = false;
                            errorText = _formatError(e);
                          });
                        }
                      },
                child: Text(busy ? 'Deleting...' : 'Delete My Account'),
              ),
            ],
          );
        },
      );
    },
  );
  passwordCtrl.dispose();
  confirmCtrl.dispose();

  if (deleted == true && context.mounted) {
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute<void>(builder: (_) => const AuthScreen()),
      (_) => false,
    );
  }
}
