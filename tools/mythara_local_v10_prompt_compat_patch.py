from pathlib import Path

# Mythara Local Fold7 KR FCC v10
# Fixes confirmed from Fold7 screenshots:
# 1) generate_image argument generation could copy an older [auto-triage] SMS instead of
#    the latest explicit user image request. Image prompts now deterministically use the
#    latest user message, bypassing the second LLM argument pass for generate_image.
# 2) Android 17 showed the 16KB developer compatibility dialog because the APK variant
#    was debuggable. Keep the same debug-variant dependency behavior but ship it as
#    non-debuggable; android:pageSizeCompat=enabled from v8 remains in the manifest.

# -----------------------------------------------------------------------------
# Version + non-debuggable install build.
# -----------------------------------------------------------------------------
p = Path('app/build.gradle.kts')
s = p.read_text()
s = s.replace('versionNameSuffix = "-local-fold7-kr-v9"', 'versionNameSuffix = "-local-fold7-kr-v10"')
s = s.replace('versionCode = 9', 'versionCode = 10', 1)

# The workflow intentionally assembles the debug variant because that path has been
# stable with all local AI native dependencies. Android's page-size diagnostic popup is
# specifically surfaced for debuggable apps, so make this install artifact non-debuggable.
debug_anchor = '''        debug {\n            isMinifyEnabled = false'''
if debug_anchor in s and 'isDebuggable = false' not in s:
    s = s.replace(
        debug_anchor,
        '''        debug {\n            isMinifyEnabled = false\n            isDebuggable = false''',
        1,
    )
p.write_text(s)

# -----------------------------------------------------------------------------
# Deterministic latest-user prompt for local image generation.
# -----------------------------------------------------------------------------
p = Path('app/src/main/kotlin/com/mythara/local/LocalGemmaChat.kt')
s = p.read_text()

if 'import org.json.JSONObject' not in s:
    s = s.replace('import javax.inject.Inject\n', 'import org.json.JSONObject\nimport javax.inject.Inject\n', 1)

old = '''        val rawArgs = runCatching {\n            gemma.runRaw(argsPrompt(request.messages, selectedTool), maxLen = 4000)\n        }.getOrNull().orEmpty()\n        val args = firstJsonObject(rawArgs) ?: "{}"'''
new = '''        // Image generation is especially sensitive to stale conversation context.\n        // The tool already accepts a natural-language prompt, so do not ask the small\n        // local model to reconstruct it from recent history. Use the latest explicit\n        // user turn verbatim. This also removes one inference pass for image requests.\n        val latestUser = request.messages\n            .lastOrNull { it.role == "user" }\n            ?.content\n            .orEmpty()\n            .trim()\n        val args = if (selectedTool.function.name == "generate_image" && latestUser.isNotBlank()) {\n            "{\\\"prompt\\\":" + JSONObject.quote(latestUser) + "}"\n        } else {\n            val rawArgs = runCatching {\n                gemma.runRaw(argsPrompt(request.messages, selectedTool), maxLen = 4000)\n            }.getOrNull().orEmpty()\n            firstJsonObject(rawArgs) ?: "{}"\n        }'''
if old not in s:
    raise SystemExit('v10 LocalGemmaChat tool-args anchor not found')
s = s.replace(old, new, 1)

# Make all remaining tool argument prompts privilege the current user turn rather than
# older notification/auto-triage content.
old = '''    private fun argsPrompt(messages: List<ChatMessage>, tool: Tool): String = buildString {\n        appendLine("Return ONLY one valid JSON object with arguments for this Android tool.")\n        appendLine("No markdown and no explanation.")\n        appendLine("TOOL: ${tool.function.name}")\n        appendLine("DESCRIPTION: ${tool.function.description}")\n        appendLine("JSON SCHEMA: ${tool.function.parameters}")\n        appendLine("RECENT CONVERSATION:")'''
new = '''    private fun argsPrompt(messages: List<ChatMessage>, tool: Tool): String = buildString {\n        val latestUser = messages.lastOrNull { it.role == "user" }?.content.orEmpty().trim()\n        appendLine("Return ONLY one valid JSON object with arguments for this Android tool.")\n        appendLine("No markdown and no explanation.")\n        appendLine("The LATEST USER REQUEST below is authoritative. Never copy an older notification, [auto-triage] message, SMS, or unrelated prior turn into arguments unless the latest user explicitly refers to it.")\n        appendLine("TOOL: ${tool.function.name}")\n        appendLine("DESCRIPTION: ${tool.function.description}")\n        appendLine("JSON SCHEMA: ${tool.function.parameters}")\n        appendLine("LATEST USER REQUEST:")\n        appendLine(latestUser.take(3000))\n        appendLine("RECENT CONVERSATION (secondary context only):")'''
if old not in s:
    raise SystemExit('v10 argsPrompt anchor not found')
s = s.replace(old, new, 1)

p.write_text(s)
print('Mythara Fold7 KR FCC v10 prompt + compatibility patch applied')
