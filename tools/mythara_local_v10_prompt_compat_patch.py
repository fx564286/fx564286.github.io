from pathlib import Path
import re

# Mythara Local Fold7 KR FCC v10
# Fixes observed on the user's Fold7 screenshots:
# - manual chat and auto-triage were allowed to run concurrently, so notification text
#   could leak into a manual image request / tool arguments
# - generate_image fallback argument generation could therefore use stale SMS content
# - Android 17 showed the developer 16KB compatibility popup because the shipped
#   assembleDebug artifact was still debuggable
#
# v10 serializes AgentRunner turns, makes the current request authoritative for FCC
# routing/arguments, hard-wires generate_image fallback arguments to the current user
# text, and emits a non-debuggable install artifact while keeping pageSizeCompat.

# -----------------------------------------------------------------------------
# Version + non-debuggable install artifact.
# -----------------------------------------------------------------------------
p = Path('app/build.gradle.kts')
s = p.read_text()
s = s.replace('versionNameSuffix = "-local-fold7-kr-v9"', 'versionNameSuffix = "-local-fold7-kr-v10"')
s = s.replace('versionCode = 9', 'versionCode = 10', 1)

if 'isDebuggable = false' not in s:
    pat = r'(\n\s*debug\s*\{\s*\n\s*isMinifyEnabled\s*=\s*false)'
    s, n = re.subn(pat, r'\1\n            isDebuggable = false', s, count=1)
    if n != 1:
        raise SystemExit('v10 debug buildType anchor not found')
p.write_text(s)

# -----------------------------------------------------------------------------
# FCC current-request routing + deterministic image arguments.
# -----------------------------------------------------------------------------
p = Path('app/src/main/kotlin/com/mythara/local/LocalGemmaChat.kt')
s = p.read_text()

# If deterministic v5 image routing ever falls through to generic WORKER selection,
# never let the small model reconstruct the image prompt from old conversation.
old = '''        val rawArgs = runRaw(argsPrompt(messages, tool, role), ARGS_OUT)\n        val args = firstJsonObject(Thinks.strip(rawArgs)) ?: "{}"'''
new = '''        val latestUser = messages.lastOrNull { it.role == "user" }?.content.orEmpty().trim()\n        val args = if (tool.function.name == "generate_image" && latestUser.isNotBlank()) {\n            val promptJson = kotlinx.serialization.json.JsonPrimitive(latestUser).toString()\n            "{\\\"prompt\\\":" + promptJson + "}"\n        } else {\n            val rawArgs = runRaw(argsPrompt(messages, tool, role), ARGS_OUT)\n            firstJsonObject(Thinks.strip(rawArgs)) ?: "{}"\n        }'''
if old not in s:
    raise SystemExit('v10 FCC emitToolCall args anchor not found')
s = s.replace(old, new, 1)

# Tell WORKER that the current user turn wins over all older notification history.
old = '''    private fun workerPrompt(messages: List<ChatMessage>, tools: List<Tool>): String = buildString {\n        appendLine("[FCC WORKER]")\n        appendLine("사용자 요청을 실제로 수행하기 위한 다음 Android 도구 하나만 고르세요.")'''
new = '''    private fun workerPrompt(messages: List<ChatMessage>, tools: List<Tool>): String = buildString {\n        val latestUser = messages.lastOrNull { it.role == "user" }?.content.orEmpty().trim()\n        appendLine("[FCC WORKER]")\n        appendLine("현재 요청이 최우선입니다. 과거 알림, [auto-triage], SMS, 이전 사용자 요청을 현재 요청으로 착각하지 마세요.")\n        appendLine("CURRENT REQUEST: $latestUser")\n        appendLine("사용자 요청을 실제로 수행하기 위한 다음 Android 도구 하나만 고르세요.")'''
if old not in s:
    raise SystemExit('v10 FCC workerPrompt anchor not found')
s = s.replace(old, new, 1)

# Same rule for tool arguments.
old = '''    private fun argsPrompt(messages: List<ChatMessage>, tool: Tool, role: String): String = buildString {\n        appendLine("[FCC $role / TOOL ARGUMENTS]")\n        appendLine("아래 Android 도구 호출 인자를 생성하세요.")'''
new = '''    private fun argsPrompt(messages: List<ChatMessage>, tool: Tool, role: String): String = buildString {\n        val latestUser = messages.lastOrNull { it.role == "user" }?.content.orEmpty().trim()\n        appendLine("[FCC $role / TOOL ARGUMENTS]")\n        appendLine("CURRENT REQUEST가 도구 인자의 최우선 출처입니다. 이전 알림/[auto-triage]/SMS를 복사하지 마세요.")\n        appendLine("CURRENT REQUEST: $latestUser")\n        appendLine("아래 Android 도구 호출 인자를 생성하세요.")'''
if old not in s:
    raise SystemExit('v10 FCC argsPrompt anchor not found')
s = s.replace(old, new, 1)

# Main router also gets an explicit current-turn line so old auto-triage content cannot
# dominate a short manual request.
old = '''    private fun mainRoutePrompt(messages: List<ChatMessage>): String = buildString {\n        appendLine("[FCC MAIN / ROUTER]")\n        appendLine("당신은 요청을 분류만 합니다. 답변 문장을 작성하지 마세요.")'''
new = '''    private fun mainRoutePrompt(messages: List<ChatMessage>): String = buildString {\n        val latestUser = messages.lastOrNull { it.role == "user" }?.content.orEmpty().trim()\n        appendLine("[FCC MAIN / ROUTER]")\n        appendLine("CURRENT REQUEST만 우선 분류하세요. 과거 알림과 이전 요청은 보조 맥락입니다.")\n        appendLine("CURRENT REQUEST: $latestUser")\n        appendLine("당신은 요청을 분류만 합니다. 답변 문장을 작성하지 마세요.")'''
if old not in s:
    raise SystemExit('v10 FCC mainRoutePrompt anchor not found')
s = s.replace(old, new, 1)
p.write_text(s)

# -----------------------------------------------------------------------------
# AgentRunner: serialize complete turns.
# Upstream explicitly allows concurrent submit() calls. That is useful for cloud LLMs,
# but unsafe for this single-resident local FCC stack because manual chat + notification
# auto-triage can append/read shared history at the same time. One turn at a time fixes
# the exact interleaving seen in the screenshot without disabling autopilot.
# -----------------------------------------------------------------------------
p = Path('app/src/main/kotlin/com/mythara/agent/AgentRunner.kt')
s = p.read_text()
if 'import kotlinx.coroutines.sync.Mutex' not in s:
    s = s.replace(
        'import kotlinx.coroutines.launch\n',
        'import kotlinx.coroutines.launch\nimport kotlinx.coroutines.sync.Mutex\nimport kotlinx.coroutines.sync.withLock\n',
        1,
    )

scope_anchor = '''    private val scope: CoroutineScope =\n        CoroutineScope(SupervisorJob() + Dispatchers.IO)\n'''
if 'private val turnExecutionMutex = Mutex()' not in s:
    if scope_anchor not in s:
        raise SystemExit('v10 AgentRunner scope anchor not found')
    s = s.replace(
        scope_anchor,
        scope_anchor + '\n    /** Local FCC owns one resident model/history writer: serialize full turns. */\n    private val turnExecutionMutex = Mutex()\n',
        1,
    )

# Wrap both agent.submit(...).collect blocks (submit + submitAndAwait) without relying
# on the internals of the collection body.
def wrap_collect_once(text: str, start_at: int = 0):
    marker = '                agent.submit(text, fromVoice = fromVoice).collect { turn ->'
    start = text.find(marker, start_at)
    if start < 0:
        raise SystemExit('v10 AgentRunner collect anchor not found')
    end_marker = '            } catch (t: Throwable) {'
    end = text.find(end_marker, start)
    if end < 0:
        raise SystemExit('v10 AgentRunner collect end anchor not found')
    block = text[start:end]
    # If already wrapped, leave it alone.
    prefix = text[max(0, start - 80):start]
    if 'turnExecutionMutex.withLock' in prefix:
        return text, end
    indented = ''.join(('    ' + line if line.strip() else line) for line in block.splitlines(True))
    wrapped = '                turnExecutionMutex.withLock {\n' + indented + '                }\n'
    text = text[:start] + wrapped + text[end:]
    return text, start + len(wrapped)

s, pos = wrap_collect_once(s, 0)
s, pos = wrap_collect_once(s, pos)
p.write_text(s)

print('Mythara Fold7 KR FCC v10 serialization + prompt + compatibility patch applied')
