import re

with open('ui/primitives.jsx', 'r') as f:
    content = f.read()

replacement = """const NAV_ITEMS = [
  ['visual', 'Office'],
  ['tasks', 'Tasks'],
  ['vault', 'Library'],
  ['terminal', 'Terminal'],"""

content = re.sub(r'const NAV_ITEMS = \[\n  \[\'visual\', \'Office\'\],\n  \[\'tasks\', \'Tasks\'\],\n  \[\'memory\', \'Memory\'\],\n  \[\'vault\', \'Library\'\],\n  \[\'team\', \'Team\'\],\n  \[\'terminal\', \'Terminal\'\],', replacement, content)

with open('ui/primitives.jsx', 'w') as f:
    f.write(content)
