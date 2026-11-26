import 'email_category.dart';

/// Represents a classified career-related email item returned by the backend.
class EmailItem {
  const EmailItem({
    required this.id,
    required this.accountId,
    required this.gmailMessageId,
    required this.senderName,
    required this.senderEmail,
    required this.subject,
    required this.bodyPreview,
    required this.receivedAt,
    required this.category,
    required this.confidence,
    this.fullContent,
    this.companyName,
    this.jobRole,
    this.isRead = false,
  });

  final String id;
  final String accountId;
  final String gmailMessageId;
  final String senderName;
  final String senderEmail;
  final String subject;
  final String bodyPreview;
  final String? fullContent;
  final DateTime receivedAt;
  final EmailCategory category;
  final double confidence;
  final String? companyName;
  final String? jobRole;
  final bool isRead;

  String get displayContent {
    final content = fullContent?.trim();
    if (content != null && content.isNotEmpty) {
      return content;
    }
    return bodyPreview;
  }

  Uri get gmailUri =>
      Uri.parse('https://mail.google.com/mail/u/0/#all/$gmailMessageId');

  EmailItem copyWith({
    String? id,
    String? accountId,
    String? gmailMessageId,
    String? senderName,
    String? senderEmail,
    String? subject,
    String? bodyPreview,
    String? fullContent,
    DateTime? receivedAt,
    EmailCategory? category,
    double? confidence,
    String? companyName,
    String? jobRole,
    bool? isRead,
  }) {
    return EmailItem(
      id: id ?? this.id,
      accountId: accountId ?? this.accountId,
      gmailMessageId: gmailMessageId ?? this.gmailMessageId,
      senderName: senderName ?? this.senderName,
      senderEmail: senderEmail ?? this.senderEmail,
      subject: subject ?? this.subject,
      bodyPreview: bodyPreview ?? this.bodyPreview,
      fullContent: fullContent ?? this.fullContent,
      receivedAt: receivedAt ?? this.receivedAt,
      category: category ?? this.category,
      confidence: confidence ?? this.confidence,
      companyName: companyName ?? this.companyName,
      jobRole: jobRole ?? this.jobRole,
      isRead: isRead ?? this.isRead,
    );
  }

  factory EmailItem.fromJson(Map<String, dynamic> json) {
    final rawSender = (json['sender'] ?? '').toString();
    final parsed = _parseSender(
      rawSender,
      explicitName: json['sender_name']?.toString(),
      explicitEmail: json['sender_email']?.toString(),
    );

    return EmailItem(
      id: (json['id'] ?? json['_id'] ?? '').toString(),
      accountId: (json['account_id'] ?? '').toString(),
      gmailMessageId: (json['gmail_message_id'] ?? '').toString(),
      senderName: parsed.$1,
      senderEmail: parsed.$2,
      subject: (json['subject'] ?? '(No Subject)').toString(),
      bodyPreview: (json['body_preview'] ?? '').toString(),
      fullContent: json['full_content']?.toString(),
      receivedAt: DateTime.tryParse((json['received_at'] ?? '').toString()) ??
          DateTime.now(),
      category: EmailCategory.fromApi(json['category']?.toString()),
      confidence: (json['confidence'] is num)
          ? (json['confidence'] as num).toDouble()
          : 0.0,
      companyName: _cleanOptional(json['company_name']),
      jobRole: _cleanOptional(json['job_role']),
      isRead: json['is_read'] == true,
    );
  }

  static String? _cleanOptional(dynamic value) {
    if (value == null) return null;
    final trimmed = value.toString().trim();
    return trimmed.isEmpty ? null : trimmed;
  }

  static (String, String) _parseSender(
    String raw, {
    String? explicitName,
    String? explicitEmail,
  }) {
    if (explicitName != null &&
        explicitName.trim().isNotEmpty &&
        explicitEmail != null &&
        explicitEmail.trim().isNotEmpty) {
      return (explicitName.trim(), explicitEmail.trim());
    }
    final match = RegExp(r'^(.*)<([^>]+)>$').firstMatch(raw.trim());
    if (match != null) {
      final name = match.group(1)?.replaceAll('"', '').trim() ?? '';
      final email = match.group(2)?.trim() ?? '';
      return (name.isEmpty ? email : name, email);
    }
    final fallback = raw.trim().isEmpty ? 'Unknown Sender' : raw.trim();
    return (explicitName?.trim().isNotEmpty == true ? explicitName!.trim() : fallback,
        explicitEmail?.trim().isNotEmpty == true ? explicitEmail!.trim() : fallback);
  }
}
