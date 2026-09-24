import re

with open('scripts/gen_pixel_hq.py', 'r') as f:
    content = f.read()

# Update HUMANS dictionary
humans_replacement = """HUMANS = {
    'cafresohq': {'tmpl': 'suit', 'h': '4b2e1f', 'H': '2a1510', 'c': '362d42', 'C': '231c2c', 'w': 'ffffff', 't': 'f0c674', 'p': '2b2436', 'P': '1a1622', 'z': '18121e'},
    'boss': {'tmpl': 'suit', 'h': '2c2c34', 'H': '181820', 'c': '222228', 'C': '141418', 'w': 'ffffff', 't': 'e74c3c', 'p': '222228', 'P': '141418', 'z': '0e0e12'},
    'rose': {'tmpl': 'creative', 'h': '5a2c20', 'H': '3a1810', 'c': 'd97c7c', 'C': 'a85656', 't': 'f5c490', 'p': '3d2d44', 'P': '24192b'},
    'teal': {'tmpl': 'hoodie', 'h': '241e2c', 'H': '120e18', 'c': '2c7873', 'C': '1c524e', 'w': 'd0f0ed', 'g': 'ffd166', 'p': '232938', 'P': '151924'},
    'sun': {'tmpl': 'suit', 'h': '8b5a2b', 'H': '543414', 'c': 'c68642', 'C': '8f5c25', 'w': 'ffffff', 't': '2b1f22', 'p': '3b2e2a', 'P': '241b18'},
    'leaf': {'tmpl': 'researcher', 'h': '28201a', 'H': '140e0a', 'c': '557a55', 'C': '385238', 'w': 'f4f4ee', 'g': 'c48a3e', 'p': '38302c', 'P': '221c18'},
    'sky': {'tmpl': 'researcher', 'h': '4a3022', 'H': '281810', 'c': '4a7c96', 'C': '2e5366', 'w': 'ffffff', 'g': '7db5b5', 'p': '283244', 'P': '181f2c'},
    'mint': {'tmpl': 'hoodie', 'h': '342216', 'H': '1c1008', 'c': '4fa382', 'C': '326d56', 'w': 'd2f4e8', 'g': '58c8d8', 'p': '362c44', 'P': '20182c'},
    'blush': {'tmpl': 'creative', 'h': '6a3222', 'H': '3c180e', 'c': 'e07a5f', 'C': 'b3543d', 't': 'f2cc8f', 'p': '3d405b', 'P': '242638'},
    'lavender': {'tmpl': 'classic', 'h': '3a2c20', 'H': '1e140c', 'c': 'b6a8e0', 'C': '7d6bb0'},
    'marketplace': {'tmpl': 'market', 'h': '1e1e1e', 'H': '000000', 'c': '1a1a1a', 'C': '0a0a0a', 't': '39ff14'},
}"""

content = re.sub(r'HUMANS = \{.*?\n\}', humans_replacement, content, flags=re.DOTALL)

# Add template arrays logic in gen_chars
gen_chars_replacement = """def gen_chars():
    def apply_template(pose, tmpl):
        p = list(pose)
        if tmpl == 'suit':
            if p == FRONT_A or p == FRONT_B:
                p[13] = '....KKwwwwKK....'
                p[14] = '...KccCttCccK...'
                p[15] = '..KcCccwtwccCcK.'
                p[16] = '.KsKcccwtwcccKsK'
                p[17] = '.KKKcCccwccCcKKK'
                p[18] = '...KccccwccccK..'
            elif p == BACK:
                p[13] = '....KKwwwwKK....'
            elif p == SIDE_A or p == SIDE_B:
                p[13] = '....KcccctcK....'
            elif p == STRETCH:
                p[12] = '....KKwwwwKK....'
                p[13] = '...KccCttCccK...'
                p[14] = '..KcCccwtwccCcK.'
                p[15] = '..KccccwtwcccK..'
                p[16] = '..KcCccwtwccCcK.'
        elif tmpl == 'hoodie':
            if p == FRONT_A or p == FRONT_B:
                p[14] = '...KccccccccK...'
                p[15] = '..KcCccwwccCcK..'
                p[16] = '.KsKccccwwccccKs'
                p[17] = '.KKKccCCCCccKKK.'
            elif p == SIDE_A or p == SIDE_B:
                p[14] = '...KcCccwwcK....'
        elif tmpl == 'researcher':
            if p == FRONT_A or p == FRONT_B:
                p[8] =  '.KhHggSSggSHhK..'
                p[9] =  '.KhgkkgSgkkgShK.'
                p[13] = '....KKwwwwKK....'
                p[14] = '...KccCwwCccK...'
                p[15] = '..KcCccwwccCcK..'
                p[16] = '.KsKccccwwccccKs'
                p[17] = '.KKKccccccccCKKK'
        elif tmpl == 'creative':
            if p == FRONT_A or p == FRONT_B:
                p[13] = '....KKttttKK....'
                p[14] = '...KcttttttccK..'
        elif tmpl == 'market':
            if p == FRONT_A or p == FRONT_B:
                p[14] = '...KcccttcccK...'
                p[15] = '..KcCcttctccCcK.'
                p[16] = '.KsKcccttctccKsK'
        return art(p, CHAR_W)

    for name, data in HUMANS.items():
        pal = dict(CHAR_BASE)
        tmpl = data.get('tmpl', 'classic')
        for k, v in data.items():
            if k != 'tmpl':
                pal[k] = hx(v)
        
        sheet = Canvas(CHAR_W * len(POSES), CHAR_H)
        for i, pose in enumerate(POSES):
            sheet.blit_ascii(apply_template(pose, tmpl), pal, ox=i * CHAR_W)
        sheet.save('char_%s.png' % name)"""

content = re.sub(r'def gen_chars\(\):.*?(?=\n\n# ──)', gen_chars_replacement, content, flags=re.DOTALL)

with open('scripts/gen_pixel_hq.py', 'w') as f:
    f.write(content)
