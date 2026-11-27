import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';
import '../models/email_category.dart';
import '../models/email_item.dart';
import '../providers/dashboard_provider.dart';
import '../providers/emails_provider.dart';
import '../services/api_exceptions.dart';
import '../theme/app_colors.dart';
import '../utils/date_formatter.dart';
import '../utils/responsive.dart';
import '../widgets/category_badge.dart';
import '../widgets/state_views.dart';

/// Screen 6: Full classified email details, extracted entities, and Gmail launch.
class EmailDetailScreen extends StatefulWidget {
  const EmailDetailScreen({
    super.key,
    this.initialEmail,
    this.emailId,
  }) : assert(initialEmail != null || emailId != null);

  final EmailItem? initialEmail;
  final String? emailId;

  @override
  State<EmailDetailScreen> createState() => _EmailDetailScreenState();
}

class _EmailDetailScreenState extends State<EmailDetailScreen> {
  EmailItem? _email;
  bool _isLoading = false;
  bool _isUpdating = false;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _email = widget.initialEmail;
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadDetails());
  }

  Future<void> _loadDetails() async {
    final targetId = _email?.id ?? widget.emailId;
    if (targetId == null || targetId.isEmpty) return;

    if (_email == null) {
      setState(() {
        _isLoading = true;
        _errorMessage = null;
      });
    }

    final emailsProvider = context.read<EmailsProvider>();
    final dashboardProvider = context.read<DashboardProvider>();

    try {
      final fetched = await emailsProvider.fetchEmailDetail(targetId);
      if (!mounted) return;
      setState(() {
        _email = fetched;
      });
      if (!fetched.isRead) {
        final marked = await emailsProvider.toggleReadStatus(
          fetched,
          isRead: true,
        );
        if (!mounted) return;
        setState(() {
          _email = marked;
        });
        dashboardProvider.applyLocalEmailUpdate(marked);
      }
    } on ApiException catch (e) {
      if (!mounted) return;
      if (_email == null) {
        setState(() {
          _errorMessage = e.message;
        });
      }
    } catch (_) {
      if (!mounted) return;
      if (_email == null) {
        setState(() {
          _errorMessage = 'Unable to load email details.';
        });
      }
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  Future<void> _openInGmail(EmailItem email) async {
    final launched = await launchUrl(
      email.gmailUri,
      mode: LaunchMode.externalApplication,
    );
    if (!launched && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Could not open Gmail on this device.'),
        ),
      );
    }
  }

  Future<void> _toggleRead(EmailItem email) async {
    setState(() => _isUpdating = true);
    try {
      final updated = await context.read<EmailsProvider>().toggleReadStatus(
            email,
            isRead: !email.isRead,
          );
      if (!mounted) return;
      context.read<DashboardProvider>().applyLocalEmailUpdate(updated);
      setState(() {
        _email = updated;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.message)),
      );
    } finally {
      if (mounted) setState(() => _isUpdating = false);
    }
  }

  Future<void> _correctCategory(EmailItem email) async {
    final selected = await showModalBottomSheet<EmailCategory>(
      context: context,
      showDragHandle: true,
      builder: (sheetContext) {
        return SafeArea(
          child: ListView(
            shrinkWrap: true,
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 16),
            children: <Widget>[
              Text(
                'Correct Email Category',
                style: Theme.of(sheetContext).textTheme.titleLarge,
              ),
              const SizedBox(height: 4),
              Text(
                'Your feedback improves JobMail\'s classification model.',
                style: Theme.of(sheetContext).textTheme.bodySmall,
              ),
              const SizedBox(height: 12),
              ...EmailCategory.values.map((category) {
                final isCurrent = category == email.category;
                return ListTile(
                  leading: Icon(category.icon, color: category.color),
                  title: Text(category.displayName),
                  trailing: isCurrent
                      ? Icon(Icons.check_rounded, color: category.color)
                      : null,
                  onTap: () => Navigator.pop(sheetContext, category),
                );
              }),
            ],
          ),
        );
      },
    );

    if (selected == null || selected == email.category || !mounted) return;

    setState(() => _isUpdating = true);
    try {
      final updated =
          await context.read<EmailsProvider>().correctCategory(email, selected);
      if (!mounted) return;
      context.read<DashboardProvider>().applyLocalEmailUpdate(updated);
      setState(() {
        _email = updated;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Updated category to ${selected.displayName}.'),
        ),
      );
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.message)),
      );
    } finally {
      if (mounted) setState(() => _isUpdating = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final email = _email;
    final maxWidth = Responsive.contentMaxWidth(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Email Details'),
        actions: <Widget>[
          if (email != null) ...<Widget>[
            IconButton(
              tooltip: email.isRead ? 'Mark as unread' : 'Mark as read',
              onPressed: _isUpdating ? null : () => _toggleRead(email),
              icon: Icon(
                email.isRead
                    ? Icons.mark_email_unread_outlined
                    : Icons.mark_email_read_outlined,
              ),
            ),
            IconButton(
              tooltip: 'Correct category',
              onPressed: _isUpdating ? null : () => _correctCategory(email),
              icon: const Icon(Icons.edit_attributes_outlined),
            ),
          ],
        ],
      ),
      body: Align(
        alignment: Alignment.topCenter,
        child: ConstrainedBox(
          constraints: BoxConstraints(maxWidth: maxWidth),
          child: _buildBody(context),
        ),
      ),
      bottomNavigationBar: email == null
          ? null
          : SafeArea(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 14),
                child: FilledButton.icon(
                  onPressed: () => _openInGmail(email),
                  icon: const Icon(Icons.open_in_new_rounded),
                  label: const Text('Open in Gmail'),
                ),
              ),
            ),
    );
  }

  Widget _buildBody(BuildContext context) {
    if (_isLoading && _email == null) {
      return const LoadingStateView(message: 'Loading email details...');
    }

    if (_errorMessage != null && _email == null) {
      return ErrorStateView(
        message: _errorMessage!,
        onRetry: _loadDetails,
      );
    }

    final email = _email;
    if (email == null) {
      return const EmptyStateView(
        icon: Icons.mail_outline_rounded,
        title: 'Email unavailable',
        subtitle: 'The requested email details could not be found.',
      );
    }

    final isDark = Theme.of(context).brightness == Brightness.dark;
    final surface = isDark ? AppColors.darkSurface : AppColors.lightSurface;
    final border = isDark ? AppColors.darkBorder : AppColors.lightBorder;
    final confidencePct = (email.confidence * 100).clamp(0, 100).round();

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 28),
      children: <Widget>[
        Wrap(
          spacing: 10,
          runSpacing: 8,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: <Widget>[
            CategoryBadge(category: email.category),
            if (email.confidence > 0)
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 10,
                  vertical: 5,
                ),
                decoration: BoxDecoration(
                  color: isDark
                      ? AppColors.darkSurfaceSubtle
                      : AppColors.lightSurfaceSubtle,
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(
                  'Confidence: $confidencePct%',
                  style: Theme.of(context).textTheme.labelSmall,
                ),
              ),
          ],
        ),
        const SizedBox(height: 14),
        Text(
          email.subject,
          style: Theme.of(context).textTheme.headlineMedium,
        ),
        const SizedBox(height: 16),
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: surface,
            borderRadius: BorderRadius.circular(18),
            border: Border.all(color: border),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Row(
                children: <Widget>[
                  CircleAvatar(
                    radius: 22,
                    backgroundColor: email.category.color.withAlpha(30),
                    child: Text(
                      email.senderName.isNotEmpty
                          ? email.senderName.trim()[0].toUpperCase()
                          : '?',
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
                        Text(
                          email.senderName,
                          style: Theme.of(context).textTheme.titleMedium,
                        ),
                        const SizedBox(height: 2),
                        SelectableText(
                          email.senderEmail,
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 14),
              const Divider(),
              const SizedBox(height: 12),
              _DetailRow(
                icon: Icons.schedule_outlined,
                label: 'Received',
                value: DateFormatter.formatFullDateTime(email.receivedAt),
              ),
              const SizedBox(height: 8),
              _DetailRow(
                icon: Icons.business_outlined,
                label: 'Identified Company',
                value: email.companyName ?? 'Not identified',
              ),
              const SizedBox(height: 8),
              _DetailRow(
                icon: Icons.badge_outlined,
                label: 'Identified Job Role',
                value: email.jobRole ?? 'Not identified',
              ),
              const SizedBox(height: 8),
              _DetailRow(
                icon: Icons.category_outlined,
                label: 'Category',
                value: email.category.displayName,
              ),
              const SizedBox(height: 8),
              Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: <Widget>[
                  Icon(
                    Icons.fingerprint_rounded,
                    size: 16,
                    color: Theme.of(context).textTheme.bodySmall?.color,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      'Gmail Ref: ${email.gmailMessageId}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ),
                  IconButton(
                    tooltip: 'Copy Gmail message ID',
                    iconSize: 16,
                    visualDensity: VisualDensity.compact,
                    onPressed: () {
                      Clipboard.setData(
                        ClipboardData(text: email.gmailMessageId),
                      );
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(
                          content: Text('Gmail reference copied.'),
                        ),
                      );
                    },
                    icon: const Icon(Icons.copy_rounded),
                  ),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),
        Container(
          padding: const EdgeInsets.all(18),
          decoration: BoxDecoration(
            color: surface,
            borderRadius: BorderRadius.circular(18),
            border: Border.all(color: border),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Row(
                children: <Widget>[
                  Expanded(
                    child: Text(
                      'Email Content',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                  ),
                  const Tooltip(
                    message:
                        'Active HTML, scripts, and remote images are stripped safely.',
                    child: Chip(
                      visualDensity: VisualDensity.compact,
                      avatar: Icon(Icons.security_rounded, size: 14),
                      label: Text(
                        'Sanitized Text',
                        style: TextStyle(fontSize: 11),
                      ),
                    ),
                  ),
                ],
              ),
              if (email.hasAttachments) ...<Widget>[
                const SizedBox(height: 10),
                Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: AppColors.accentAmber.withAlpha(24),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Row(
                    children: <Widget>[
                      const Icon(
                        Icons.attachment_rounded,
                        size: 16,
                        color: AppColors.accentAmber,
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          email.attachmentNames.isNotEmpty
                              ? 'Attachments not downloaded for security: ${email.attachmentNames.join(', ')}'
                              : 'Email includes attachments (never downloaded or executed by JobMail).',
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
              const SizedBox(height: 10),
              SelectableText(
                email.displayContent,
                style: Theme.of(context).textTheme.bodyLarge,
              ),
            ],
          ),
        ),
        const SizedBox(height: 14),
        OutlinedButton.icon(
          onPressed: _isUpdating ? null : () => _correctCategory(email),
          icon: const Icon(Icons.label_outline_rounded, size: 18),
          label: const Text('Wrong category? Correct classification'),
        ),
      ],
    );
  }
}

class _DetailRow extends StatelessWidget {
  const _DetailRow({
    required this.icon,
    required this.label,
    required this.value,
  });

  final IconData icon;
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Icon(
          icon,
          size: 16,
          color: Theme.of(context).textTheme.bodySmall?.color,
        ),
        const SizedBox(width: 8),
        SizedBox(
          width: 132,
          child: Text(
            label,
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  fontWeight: FontWeight.w600,
                ),
          ),
        ),
        Expanded(
          child: Text(
            value,
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  fontWeight: FontWeight.w600,
                ),
          ),
        ),
      ],
    );
  }
}
