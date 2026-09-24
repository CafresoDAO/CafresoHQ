import re

with open('ui/office.jsx', 'r') as f:
    content = f.read()

replacement = """  const toolItems = [
    { icon: '📬', label: 'Inbox',    badge: inboxCount || 0,   action: onOpenInbox },
    { icon: '🔬', label: 'Research', badge: missionCount || 0,  action: onOpenResearch },
    { icon: night ? '☀' : '☾', label: night ? 'Day' : 'Night', badge: 0, action: onToggleNight },
    { icon: '⚙️', label: 'Settings', badge: 0,                  action: onOpenSettings },
  ];"""

content = re.sub(r'  const toolItems = \[\n.*?  \];', replacement, content, flags=re.DOTALL)

with open('ui/office.jsx', 'w') as f:
    f.write(content)
