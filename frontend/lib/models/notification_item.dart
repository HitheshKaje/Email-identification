import 'email_category.dart';

/// Push/in-app notification linked to a classified career email.
class NotificationItem {
  const NotificationItem({
    required this.id,
    required this.emailId,
    required this.title,
    required this.message,
    required this.createdAt,
    this.category = EmailCategory.job,
    this.isRead = false,
  });

  final String id;
  final String emailId;
  final String title;
  final String message;
  final EmailCategory category;
  final DateTime createdAt;
  final bool isRead;

  NotificationItem copyWith({bool? isRead}) {
    return NotificationItem(
      id: id,
      emailId: emailId,
      title: title,
      message: message,
      category: category,
      createdAt: createdAt,
      isRead: isRead ?? this.isRead,
    );
  }

  factory NotificationItem.fromJson(Map<String, dynamic> json) {
    return NotificationItem(
      id: (json['id'] ?? json['_id'] ?? '').toString(),
      emailId: (json['email_id'] ?? '').toString(),
      title: (json['title'] ?? 'New Job Notification').toString(),
      message: (json['message'] ?? '').toString(),
      category: EmailCategory.fromApi(json['category']?.toString()),
      createdAt: DateTime.tryParse((json['created_at'] ?? '').toString()) ??
          DateTime.now(),
      isRead: json['is_read'] == true,
    );
  }
}
