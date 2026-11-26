import 'package:flutter/material.dart';

/// Brand and semantic color tokens for JobMail light and dark themes.
class AppColors {
  AppColors._();

  // Brand primary palette (Deep Indigo + Electric Blue + Teal accents)
  static const Color primary = Color(0xFF1D4ED8);
  static const Color primaryDark = Color(0xFF60A5FA);
  static const Color primaryContainerLight = Color(0xFFDBEAFE);
  static const Color primaryContainerDark = Color(0xFF1E3A8A);

  static const Color secondary = Color(0xFF0D9488);
  static const Color secondaryDark = Color(0xFF2DD4BF);

  static const Color accentPurple = Color(0xFF6D28D9);
  static const Color accentAmber = Color(0xFFD97706);
  static const Color accentEmerald = Color(0xFF059669);
  static const Color accentRose = Color(0xFFE11D48);
  static const Color accentCyan = Color(0xFF0284C7);

  // Light surfaces
  static const Color lightBackground = Color(0xFFF6F8FC);
  static const Color lightSurface = Color(0xFFFFFFFF);
  static const Color lightSurfaceSubtle = Color(0xFFF1F5F9);
  static const Color lightBorder = Color(0xFFE2E8F0);
  static const Color lightTextPrimary = Color(0xFF0F172A);
  static const Color lightTextSecondary = Color(0xFF475569);
  static const Color lightTextMuted = Color(0xFF64748B);

  // Dark surfaces
  static const Color darkBackground = Color(0xFF0B1120);
  static const Color darkSurface = Color(0xFF111827);
  static const Color darkSurfaceSubtle = Color(0xFF1E293B);
  static const Color darkBorder = Color(0xFF293548);
  static const Color darkTextPrimary = Color(0xFFF8FAFC);
  static const Color darkTextSecondary = Color(0xFFCBD5E1);
  static const Color darkTextMuted = Color(0xFF94A3B8);

  // Semantic feedback
  static const Color success = Color(0xFF16A34A);
  static const Color warning = Color(0xFFEA580C);
  static const Color error = Color(0xFFDC2626);
  static const Color info = Color(0xFF2563EB);
}
