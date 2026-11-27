import 'package:flutter/material.dart';
import '../models/connected_account.dart';
import '../theme/app_colors.dart';
import '../utils/date_formatter.dart';

/// Card representing a connected Gmail account with sync and disconnect controls.
class AccountCard extends StatelessWidget {
  const AccountCard({
    super.key,
    required this.account,
    required this.isSyncing,
    required this.onSync,
    required this.onDisconnect,
    this.isVerifying = false,
    this.onVerify,
    this.onReconnect,
  });

  final ConnectedAccount account;
  final bool isSyncing;
  final bool isVerifying;
  final VoidCallback onSync;
  final VoidCallback onDisconnect;
  final VoidCallback? onVerify;
  final VoidCallback? onReconnect;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final surface = isDark ? AppColors.darkSurface : AppColors.lightSurface;
    final border = isDark ? AppColors.darkBorder : AppColors.lightBorder;
    final statusColor = account.syncStatus.color;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: border),
        boxShadow: isDark
            ? null
            : <BoxShadow>[
                BoxShadow(
                  color: const Color(0xFF0F172A).withAlpha(10),
                  blurRadius: 12,
                  offset: const Offset(0, 4),
                ),
              ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  color: AppColors.primary.withAlpha(24),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: const Icon(
                  Icons.alternate_email_rounded,
                  color: AppColors.primary,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      account.emailAddress,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(height: 3),
                    Text(
                      'Google OAuth 2.0 (Read-only)',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                decoration: BoxDecoration(
                  color: statusColor.withAlpha(26),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    Container(
                      width: 7,
                      height: 7,
                      decoration: BoxDecoration(
                        color: statusColor,
                        shape: BoxShape.circle,
                      ),
                    ),
                    const SizedBox(width: 6),
                    Text(
                      account.syncStatus.label,
                      style: TextStyle(
                        color: statusColor,
                        fontSize: 12,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          Row(
            children: <Widget>[
              Icon(
                Icons.sync_rounded,
                size: 15,
                color: Theme.of(context).textTheme.bodySmall?.color,
              ),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  account.lastSyncedAt != null
                      ? 'Last synced ${DateFormatter.formatRelative(account.lastSyncedAt!)}'
                      : 'Not synchronized yet',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ),
            ],
          ),
          if (account.statusMessage != null &&
              account.statusMessage!.trim().isNotEmpty) ...<Widget>[
            const SizedBox(height: 8),
            Text(
              account.statusMessage!,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: statusColor,
                  ),
            ),
          ],
          const SizedBox(height: 14),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: <Widget>[
              if (account.syncStatus == AccountSyncStatus.revoked &&
                  onReconnect != null)
                FilledButton.icon(
                  onPressed: isSyncing ? null : onReconnect,
                  icon: const Icon(Icons.link_rounded, size: 18),
                  label: const Text('Reconnect'),
                )
              else
                OutlinedButton.icon(
                  onPressed: (isSyncing || isVerifying) ? null : onSync,
                  icon: isSyncing
                      ? const SizedBox(
                          width: 15,
                          height: 15,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.refresh_rounded, size: 18),
                  label: Text(isSyncing ? 'Syncing...' : 'Sync Now'),
                ),
              if (onVerify != null &&
                  account.syncStatus != AccountSyncStatus.revoked)
                IconButton.outlined(
                  tooltip: 'Refresh connection status',
                  onPressed: (isSyncing || isVerifying) ? null : onVerify,
                  icon: isVerifying
                      ? const SizedBox(
                          width: 15,
                          height: 15,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.verified_user_outlined, size: 18),
                ),
              OutlinedButton.icon(
                onPressed: isSyncing ? null : onDisconnect,
                style: OutlinedButton.styleFrom(
                  foregroundColor: AppColors.error,
                  side: BorderSide(color: AppColors.error.withAlpha(90)),
                ),
                icon: const Icon(Icons.link_off_rounded, size: 18),
                label: const Text('Disconnect'),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
