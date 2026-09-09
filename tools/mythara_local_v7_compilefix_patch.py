from pathlib import Path

# Compile fixes found by the first v7 Hybrid CI run.

# 1) ACE-Step nullable row access.
p = Path('app/src/main/kotlin/com/mythara/local/AceStepClient.kt')
s = p.read_text()
s = s.replace(
    'val resultText = row["result"]?.jsonPrimitive?.contentOrNull.orEmpty()',
    'val resultText = row?.get("result")?.jsonPrimitive?.contentOrNull.orEmpty()',
)
p.write_text(s)

# 2) Qualcomm GenieX APIs used below are suspend functions.
p = Path('app/src/main/kotlin/com/mythara/local/QwenNpuRuntime.kt')
s = p.read_text()
s = s.replace('    private fun applyTemplate(', '    private suspend fun applyTemplate(', 1)
s = s.replace('    private fun buildVlm(', '    private suspend fun buildVlm(', 1)
s = s.replace('    private fun tryBuildVlm(', '    private suspend fun tryBuildVlm(', 1)
s = s.replace('    private fun switchOutLocked() {', '    private suspend fun switchOutLocked() {', 1)
p.write_text(s)

# 3) v7 music planner output budget constant. The original insertion guard
# matched usages of MUSIC_PLAN_OUT, so the declaration itself was skipped.
p = Path('app/src/main/kotlin/com/mythara/local/LocalGemmaChat.kt')
s = p.read_text()
if 'private const val MUSIC_PLAN_OUT' not in s:
    anchors = [
        '        private const val ARGS_OUT = 4000\n',
        '        private const val MAX_FCC_TOOL_ATTEMPTS = 3\n',
    ]
    for anchor in anchors:
        if anchor in s:
            s = s.replace(anchor, anchor + '        private const val MUSIC_PLAN_OUT = 12000\n', 1)
            break
    else:
        raise SystemExit('LocalGemmaChat companion constant anchor not found')
p.write_text(s)

print('Mythara v7 Hybrid Kotlin compile fixes applied')
