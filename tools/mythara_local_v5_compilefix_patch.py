from pathlib import Path

p = Path('app/src/main/kotlin/com/mythara/local/LocalGemmaChat.kt')
lines = p.read_text().splitlines()
changed = False
for i, line in enumerate(lines):
    if 'val path = Regex(' in line:
        indent = line[:len(line) - len(line.lstrip())]
        lines[i] = indent + 'val path = Regex("""["]path["]\\s*:\\s*["]([^"]+)["]""")'
        changed = True
        break
if not changed:
    raise SystemExit('v5 path regex line not found')
p.write_text('\n'.join(lines) + '\n')
print('v5 Kotlin regex compile fix applied')
