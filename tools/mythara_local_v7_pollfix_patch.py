from pathlib import Path

p = Path('app/src/main/kotlin/com/mythara/local/AceStepClient.kt')
s = p.read_text()
old = '        repeat(MAX_POLLS) {\n'
new = '        for (poll in 0 until MAX_POLLS) {\n'
if old not in s:
    raise SystemExit('ACE-Step poll loop anchor not found')
s = s.replace(old, new, 1)
s = s.replace('if (!audioRelative.isNullOrBlank()) return@repeat', 'if (!audioRelative.isNullOrBlank()) break')
p.write_text(s)
print('ACE-Step polling break fix applied')
