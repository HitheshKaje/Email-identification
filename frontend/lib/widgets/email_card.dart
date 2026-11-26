import 'package:flutter/material.dart';
import '../models/email_item.dart';
import '../theme/app_colors.dart';
import '../utils/date_formatter.dart';
import 'category_badge.dart';

/// Reusable recruitment email summary card used across Dashboard, Job Inbox, and Categories.
class EmailCard extends StatelessWidget {
  const EmailCard({
    super.key,
    required this.email,
    required this.onTap,
  });

  final EmailItem email;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final surface = isDark ? AppColors.darkSurface : AppColors.lightSurface;
    final border = email.isRead
        ? (isDark ? AppColors.darkBorder : AppColors.lightBorder)
        : email.category.color.withAlpha(110);
    final avatarBg = email.category.color.withAlpha(30);
    final initial = email.senderName.isNotEmpty
        ? email.senderName.trim()[0].toUpperCase()
        : '?';

    return Material(
      color: surface,
      borderRadius: BorderRadius.circular(18),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(18),
        child: Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(18),
            border: Border.all(color: border, width: email.isRead ? 1 : 1.3),
            boxShadow: isDark
                ? null
                : <BoxShadow>[
                    BoxShadow(
                      color: const Color(0xFF0F172A).withAlpha(10),
                      blurRadius: 14,
                      offset: const Offset(0, 4),
                    ),
                  ],
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: <Widget>[
                  CircleAvatar(
                    radius: 19,
                    backgroundColor: avatarBg,
                    child: Text(
                      initial,
                      style: TextStyle(
                        color: email.category.color,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Row(
                          children: <Widget>[
                            if (!email.isRead) ...<Widget>[
                              Container(
                                width: 8,
                                height: 8,
                                decoration: BoxDecoration(
                                  color: email.category.color,
                                  shape: BoxShape.circle,
                                ),
                              ),
                              const SizedBox(width: 6),
                            ],
                            Expanded(
                              child: Text(
                                email.senderName,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: Theme.of(context)
                                    .textTheme
                                    .titleMedium
                                    ?.copyWith(
                                      fontWeight: email.isRead
                                          ? FontWeight.w500
                                          : FontWeight.w700,
                                    ),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 2),
                        Text(
                          DateFormatter.formatShortDateTime(email.receivedAt),
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(width: 8),
                  CategoryBadge(category: email.category, compact: true),
                ],
              ),
              const SizedBox(height: 12),
              Text(
                email.subject,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      fontWeight:
                          email.isRead ? FontWeight.w600 : FontWeight.w700,
                    ),
              ),
              const SizedBox(height: 6),
              Text(
                email.bodyPreview,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.bodyMedium,
              ),
              if (email.companyName != null || email.jobRole != null) ...<Widget>[
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  runSpacing: 6,
                  children: <Widget>[
                    if (email.companyName != null)
                      _MetaPill(
                        icon: Icons.business_outlined,
                        label: email.companyName!,
                      ),
                    if (email.jobRole != null)
                      _MetaPill(
                        icon: Icons.badge_outlined,
                        label: email.jobRole!,
                      ),
                  ],
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _MetaPill extends StatelessWidget {
  const _MetaPill({required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final bg =
        isDark ? AppColors.darkSurfaceSubtle : AppColors.lightSurfaceSubtle;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(icon, size: 13, color: Theme.of(context).textTheme.bodySmall?.color),
          const SizedBox(width: 5),
          Flexible(
            child: Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(context).textTheme.labelSmall,
            ),
          ),
        ],
      ),
    );
  }
}
