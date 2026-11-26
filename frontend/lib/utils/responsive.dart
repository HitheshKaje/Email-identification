import 'package:flutter/material.dart';

/// Responsive layout breakpoints for mobile, tablet, and desktop views.
class Responsive {
  Responsive._();

  static const double tabletBreakpoint = 640;
  static const double desktopBreakpoint = 1024;

  static bool isCompact(BuildContext context) =>
      MediaQuery.sizeOf(context).width < tabletBreakpoint;

  static bool isMedium(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    return width >= tabletBreakpoint && width < desktopBreakpoint;
  }

  static bool isExpanded(BuildContext context) =>
      MediaQuery.sizeOf(context).width >= desktopBreakpoint;

  static int gridColumnCount(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    if (width >= desktopBreakpoint) return 4;
    if (width >= tabletBreakpoint) return 2;
    return 2;
  }

  static double contentMaxWidth(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    if (width >= desktopBreakpoint) return 1120;
    return double.infinity;
  }
}
