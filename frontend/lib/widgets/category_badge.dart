import 'package:flutter/material.dart';
import '../models/email_category.dart';

/// Color-coded category badge pill for classified recruitment emails.
class CategoryBadge extends StatelessWidget {
  const CategoryBadge({
    super.key,
    required this.category,
    this.compact = false,
  });

  final EmailCategory category;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final color = category.color;
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: compact ? 8 : 10,
        vertical: compact ? 4 : 5,
      ),
      decoration: BoxDecoration(
        color: color.withAlpha(26),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color.withAlpha(70)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(
            category.icon,
            size: compact ? 13 : 14,
            color: color,
          ),
          const SizedBox(width: 5),
          Text(
            compact ? category.shortLabel : category.displayName,
            style: TextStyle(
              color: color,
              fontSize: compact ? 11.5 : 12,
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ),
    );
  }
}
