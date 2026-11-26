/// Formatting utilities for email and sync timestamps without external locale dependencies.
class DateFormatter {
  DateFormatter._();

  static const List<String> _months = <String>[
    'Jan',
    'Feb',
    'Mar',
    'Apr',
    'May',
    'Jun',
    'Jul',
    'Aug',
    'Sep',
    'Oct',
    'Nov',
    'Dec',
  ];

  static String formatShortDateTime(DateTime dt) {
    final local = dt.toLocal();
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final dateOnly = DateTime(local.year, local.month, local.day);
    final diffDays = today.difference(dateOnly).inDays;

    final timePart = _formatTime(local);
    if (diffDays == 0) {
      return 'Today, $timePart';
    }
    if (diffDays == 1) {
      return 'Yesterday, $timePart';
    }
    if (local.year == now.year) {
      return '${_months[local.month - 1]} ${local.day}, $timePart';
    }
    return '${_months[local.month - 1]} ${local.day}, ${local.year}';
  }

  static String formatFullDateTime(DateTime dt) {
    final local = dt.toLocal();
    return '${_months[local.month - 1]} ${local.day}, ${local.year} at ${_formatTime(local)}';
  }

  static String formatRelative(DateTime dt) {
    final diff = DateTime.now().difference(dt.toLocal());
    if (diff.inSeconds < 60) {
      return 'Just now';
    }
    if (diff.inMinutes < 60) {
      final mins = diff.inMinutes;
      return '$mins min${mins == 1 ? '' : 's'} ago';
    }
    if (diff.inHours < 24) {
      final hrs = diff.inHours;
      return '$hrs hr${hrs == 1 ? '' : 's'} ago';
    }
    if (diff.inDays < 7) {
      final days = diff.inDays;
      return '$days day${days == 1 ? '' : 's'} ago';
    }
    return formatShortDateTime(dt);
  }

  static String _formatTime(DateTime dt) {
    final hour12 = dt.hour % 12 == 0 ? 12 : dt.hour % 12;
    final minute = dt.minute.toString().padLeft(2, '0');
    final period = dt.hour >= 12 ? 'PM' : 'AM';
    return '$hour12:$minute $period';
  }
}
