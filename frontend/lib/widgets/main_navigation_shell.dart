import 'package:flutter/material.dart';
import '../screens/categories_screen.dart';
import '../screens/connected_accounts_screen.dart';
import '../screens/dashboard_screen.dart';
import '../screens/job_inbox_screen.dart';
import '../screens/settings_screen.dart';
import '../utils/responsive.dart';
import 'jobmail_logo.dart';

/// Adaptive root shell providing bottom navigation on mobile and NavigationRail on wide screens.
class MainNavigationShell extends StatefulWidget {
  const MainNavigationShell({super.key, this.initialIndex = 0});

  final int initialIndex;

  @override
  State<MainNavigationShell> createState() => _MainNavigationShellState();
}

class _MainNavigationShellState extends State<MainNavigationShell> {
  late int _selectedIndex;

  @override
  void initState() {
    super.initState();
    _selectedIndex = widget.initialIndex;
  }

  void _selectTab(int index) {
    setState(() {
      _selectedIndex = index;
    });
  }

  static const List<NavigationDestination> _destinations =
      <NavigationDestination>[
    NavigationDestination(
      icon: Icon(Icons.dashboard_outlined),
      selectedIcon: Icon(Icons.dashboard_rounded),
      label: 'Home',
    ),
    NavigationDestination(
      icon: Icon(Icons.inbox_outlined),
      selectedIcon: Icon(Icons.inbox_rounded),
      label: 'Inbox',
    ),
    NavigationDestination(
      icon: Icon(Icons.category_outlined),
      selectedIcon: Icon(Icons.category_rounded),
      label: 'Categories',
    ),
    NavigationDestination(
      icon: Icon(Icons.alternate_email_outlined),
      selectedIcon: Icon(Icons.alternate_email_rounded),
      label: 'Accounts',
    ),
    NavigationDestination(
      icon: Icon(Icons.settings_outlined),
      selectedIcon: Icon(Icons.settings_rounded),
      label: 'Settings',
    ),
  ];

  @override
  Widget build(BuildContext context) {
    final isCompact = Responsive.isCompact(context);

    final pages = <Widget>[
      DashboardScreen(
        onOpenInbox: () => _selectTab(1),
        onOpenAccounts: () => _selectTab(3),
        onOpenSettings: () => _selectTab(4),
      ),
      const JobInboxScreen(),
      const CategoriesScreen(),
      const ConnectedAccountsScreen(),
      SettingsScreen(
        onOpenAccounts: () => _selectTab(3),
      ),
    ];

    if (isCompact) {
      return Scaffold(
        body: IndexedStack(
          index: _selectedIndex,
          children: pages,
        ),
        bottomNavigationBar: NavigationBar(
          selectedIndex: _selectedIndex,
          onDestinationSelected: _selectTab,
          destinations: _destinations,
        ),
      );
    }

    return Scaffold(
      body: Row(
        children: <Widget>[
          NavigationRail(
            selectedIndex: _selectedIndex,
            onDestinationSelected: _selectTab,
            extended: Responsive.isExpanded(context),
            leading: Padding(
              padding: const EdgeInsets.symmetric(vertical: 16),
              child: JobMailLogo(
                size: 36,
                showWordmark: Responsive.isExpanded(context),
              ),
            ),
            destinations: const <NavigationRailDestination>[
              NavigationRailDestination(
                icon: Icon(Icons.dashboard_outlined),
                selectedIcon: Icon(Icons.dashboard_rounded),
                label: Text('Home'),
              ),
              NavigationRailDestination(
                icon: Icon(Icons.inbox_outlined),
                selectedIcon: Icon(Icons.inbox_rounded),
                label: Text('Inbox'),
              ),
              NavigationRailDestination(
                icon: Icon(Icons.category_outlined),
                selectedIcon: Icon(Icons.category_rounded),
                label: Text('Categories'),
              ),
              NavigationRailDestination(
                icon: Icon(Icons.alternate_email_outlined),
                selectedIcon: Icon(Icons.alternate_email_rounded),
                label: Text('Accounts'),
              ),
              NavigationRailDestination(
                icon: Icon(Icons.settings_outlined),
                selectedIcon: Icon(Icons.settings_rounded),
                label: Text('Settings'),
              ),
            ],
          ),
          const VerticalDivider(width: 1),
          Expanded(
            child: IndexedStack(
              index: _selectedIndex,
              children: pages,
            ),
          ),
        ],
      ),
    );
  }
}
