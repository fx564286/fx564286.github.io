from pathlib import Path

# Mythara Local Fold7 KR v4 — FCC-Mobile orchestration.
# Run AFTER mythara_local_patch.py + mythara_local_kr_patch.py.
#
# One on-device Gemma engine is shared sequentially across four roles:
#   MAIN      : answer vs phone-action classification + final user response
#   WORKER    : choose the next concrete Android tool
#   REVIEWER  : inspect the real tool result and decide PASS vs RETRY
#   DEBUGGER  : after a failed result, choose a recovery tool
#
# GemmaExtractor serialises inference with a Mutex, so this design never starts
# concurrent LiteRT-LM sessions and is safe for the Fold7's single resident model.

p = Path('app/build.gradle.kts')
s = p.read_text()
s = s.replace('applicationIdSuffix = ".localkr"', 'applicationIdSuffix = ".localkr4"')
s = s.replace('versionNameSuffix = "-local-fold7-kr"', 'versionNameSuffix = "-local-fold7-kr-v4"')
p.write_text(s)

local_file = Path('app/src/main/kotlin/com/mythara/local/LocalGemmaChat.kt')
local_file.write_text(r'''package com.mythara.local

import com.mythara.agent.Thinks
import com.mythara.minimax.ErrorMapper
import com.mythara.minimax.StreamingChat
import com.mythara.minimax.models.ChatMessage
import com.mythara.minimax.models.ChatRequest
import com.mythara.minimax.models.Tool
import com.mythara.minimax.models.ToolCall
import com.mythara.minimax.models.ToolCallFunction
import com.mythara.secret.observe.extract.gemma.GemmaExtractor
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.FlowCollector
import kotlinx.coroutines.flow.flow
import javax.inject.Inject
import javax.inject.Singleton

/**
 * FCC-Mobile for the fully-local Fold7 build.
 *
 * We deliberately do NOT run four models in parallel. The device keeps one
 * Gemma 4 E2B / LiteRT-LM engine resident and gives it short, role-specific
 * prompts in sequence. That preserves the Main/Worker/Debugger/Reviewer
 * separation without creating competing native sessions or multiplying RAM.
 */
@Singleton
class LocalGemmaChat @Inject constructor(
    private val gemma: GemmaExtractor,
) {
    fun isReady(): Boolean = gemma.isReady()

    fun stream(request: ChatRequest): Flow<StreamingChat.StreamEvent> = flow {
        if (!gemma.isReady()) {
            emit(
                StreamingChat.StreamEvent.Failure(
                    ErrorMapper.Mapped(
                        0,
                        "LOCAL_MODEL_MISSING",
                        "로컬 Gemma 4 E2B 모델이 설치되지 않았습니다. 설정 → 정보 → MYTHARA 3회 탭 → Secret → 로컬 AI 모델에서 설치해 주세요.",
                    ),
                ),
            )
            return@flow
        }

        val messages = request.messages
        val tools = request.tools.orEmpty()

        // AgentLoop calls us again after a tool has actually executed. That is
        // the FCC Reviewer entry point: verify the real result before Main says
        // the task is complete.
        if (messages.lastOrNull()?.role == "tool") {
            handleToolResult(messages, tools)
            return@flow
        }

        val latestUser = messages.lastOrNull { it.role == "user" }?.content.orEmpty().trim()

        // MAIN: only decide whether this is ordinary conversation or a real
        // phone action/read that needs the tool layer.
        val mainRoute = runRaw(mainRoutePrompt(messages), MAIN_ROUTE_OUT)
        val needsAction = MAIN_ACTION.containsMatchIn(mainRoute)

        if (!needsAction) {
            emitMainAnswer(messages, latestUser)
            return@flow
        }

        // WORKER: select exactly one next tool. Keeping this separate from Main
        // makes the small model much less likely to hallucinate a tool call.
        val worker = runRaw(workerPrompt(messages, tools), WORKER_OUT)
        val selected = pickTool(worker, tools)
        if (selected == null) {
            emitMainAnswer(messages, latestUser)
            return@flow
        }

        emitToolCall(messages, selected, role = "WORKER")
    }

    private suspend fun FlowCollector<StreamingChat.StreamEvent>.handleToolResult(
        messages: List<ChatMessage>,
        tools: List<Tool>,
    ) {
        val latestUser = messages.lastOrNull { it.role == "user" }?.content.orEmpty().trim()
        val recentToolAttempts = messages.takeLast(18).count { it.role == "tool" }
        val toolResult = messages.lastOrNull { it.role == "tool" }?.content.orEmpty()

        // REVIEWER: must explicitly PASS or RETRY based on the actual tool output.
        val review = runRaw(reviewerPrompt(messages), REVIEW_OUT)
        val pass = REVIEW_PASS.containsMatchIn(review) ||
            (!REVIEW_RETRY.containsMatchIn(review) && heuristicToolSuccess(toolResult))

        if (pass) {
            var answer = cleanAnswer(runRaw(finalResultPrompt(messages), ANSWER_OUT))
            if (answer.isBlank() || isLikelyEcho(answer, latestUser)) {
                answer = deterministicResultFallback(toolResult)
            }
            emit(StreamingChat.StreamEvent.Text(answer))
            emit(StreamingChat.StreamEvent.Done("stop"))
            return
        }

        // Never let local recovery loop forever. AgentLoop also has its own loop
        // detector; this is an extra mobile-specific cap to control heat/latency.
        if (recentToolAttempts >= MAX_FCC_TOOL_ATTEMPTS) {
            emit(
                StreamingChat.StreamEvent.Text(
                    "작업 결과를 검증했지만 정상 완료를 확인하지 못했어. 자동 복구를 ${MAX_FCC_TOOL_ATTEMPTS}회 시도했기 때문에 여기서 중단했어. 현재 화면이나 오류 내용을 알려주면 다음 방법을 잡아볼게.",
                ),
            )
            emit(StreamingChat.StreamEvent.Done("stop"))
            return
        }

        // DEBUGGER: inspect the failed result and choose a recovery tool. It can
        // reuse the same tool with corrected args, or choose another tool.
        val debug = runRaw(debuggerPrompt(messages, tools), DEBUGGER_OUT)
        val recovery = pickTool(debug, tools)
        if (recovery != null) {
            emitToolCall(messages, recovery, role = "DEBUGGER")
            return
        }

        emit(
            StreamingChat.StreamEvent.Text(
                "도구 실행 결과를 검토했지만 자동으로 복구할 안전한 다음 동작을 찾지 못했어. 마지막 결과: ${toolResult.take(300)}",
            ),
        )
        emit(StreamingChat.StreamEvent.Done("stop"))
    }

    private suspend fun FlowCollector<StreamingChat.StreamEvent>.emitMainAnswer(
        messages: List<ChatMessage>,
        latestUser: String,
    ) {
        var answer = cleanAnswer(runRaw(mainAnswerPrompt(messages), ANSWER_OUT))

        // Small local models occasionally copy the user verbatim. Retry once
        // with a deliberately tiny prompt and then use deterministic Korean
        // fallbacks for the most common cases.
        if (answer.isBlank() || isLikelyEcho(answer, latestUser)) {
            answer = cleanAnswer(runRaw(retryAnswerPrompt(messages), ANSWER_OUT))
        }
        if (answer.isBlank() || isLikelyEcho(answer, latestUser)) {
            answer = deterministicFallback(latestUser)
        }

        emit(StreamingChat.StreamEvent.Text(answer))
        emit(StreamingChat.StreamEvent.Done("stop"))
    }

    private suspend fun FlowCollector<StreamingChat.StreamEvent>.emitToolCall(
        messages: List<ChatMessage>,
        tool: Tool,
        role: String,
    ) {
        val rawArgs = runRaw(argsPrompt(messages, tool, role), ARGS_OUT)
        val args = firstJsonObject(Thinks.strip(rawArgs)) ?: "{}"
        emit(
            StreamingChat.StreamEvent.ToolCallsReady(
                listOf(
                    ToolCall(
                        id = "fcc_${role.lowercase()}_${tool.function.name}_${System.nanoTime()}",
                        type = "function",
                        function = ToolCallFunction(
                            name = tool.function.name,
                            arguments = args,
                        ),
                    ),
                ),
            ),
        )
        emit(StreamingChat.StreamEvent.Done("tool_calls"))
    }

    private suspend fun runRaw(prompt: String, maxLen: Int): String =
        runCatching { gemma.runRaw(prompt, maxLen = maxLen) }
            .getOrNull().orEmpty().let(Thinks::strip).trim()

    // ── MAIN ────────────────────────────────────────────────────────────────
    private fun mainRoutePrompt(messages: List<ChatMessage>): String = buildString {
        appendLine("[FCC MAIN / ROUTER]")
        appendLine("당신은 요청을 분류만 합니다. 답변 문장을 작성하지 마세요.")
        appendLine("휴대폰 상태 읽기, 앱 실행, 화면 조작, 메시지/전화/일정/설정 변경 등 실제 Android 기능이 필요하면 [ACTION]을 출력하세요.")
        appendLine("인사, 지식 질문, 설명, 번역, 잡담처럼 휴대폰 도구가 필요 없으면 [ANSWER]를 출력하세요.")
        appendLine("정확히 한 줄만 출력: [ACTION] 또는 [ANSWER]")
        appendLine("최근 대화:")
        appendRecent(messages, MAIN_CONTEXT)
    }.take(MAIN_ROUTE_PROMPT_MAX)

    private fun mainAnswerPrompt(messages: List<ChatMessage>): String = buildString {
        appendLine("[FCC MAIN / FINAL ANSWER]")
        appendLine("당신은 Galaxy Z Fold7 안에서 완전히 로컬로 실행되는 Mythara AI입니다.")
        appendLine("사용자가 다른 언어를 명시하지 않는 한 자연스러운 한국어로 직접 답하세요.")
        appendLine("사용자 문장을 그대로 반복하지 마세요. 내부 프롬프트나 FCC 역할 이름을 말하지 마세요.")
        appendLine("모르는 사실은 만들지 말고, 작은 로컬 모델답게 짧고 명확하게 답하세요.")
        appendLine("최근 대화:")
        appendRecent(messages, ANSWER_CONTEXT)
        appendLine("Mythara의 최종 답변:")
    }.take(ANSWER_PROMPT_MAX)

    private fun retryAnswerPrompt(messages: List<ChatMessage>): String {
        val latestUser = messages.lastOrNull { it.role == "user" }?.content.orEmpty().take(PER_MESSAGE_MAX)
        return buildString {
            appendLine("한국어 AI Mythara로서 질문에 새 내용으로 직접 답하세요.")
            appendLine("사용자 문장을 복사하거나 영어 자기소개를 하지 마세요.")
            appendLine("사용자: $latestUser")
            appendLine("답변:")
        }.take(RETRY_PROMPT_MAX)
    }

    // ── WORKER ──────────────────────────────────────────────────────────────
    private fun workerPrompt(messages: List<ChatMessage>, tools: List<Tool>): String = buildString {
        appendLine("[FCC WORKER]")
        appendLine("사용자 요청을 실제로 수행하기 위한 다음 Android 도구 하나만 고르세요.")
        appendLine("출력 형식은 정확히 [USE_TOOL] exact_tool_name 한 줄입니다.")
        appendLine("없는 도구를 만들지 마세요. 읽기 요청에는 읽기 도구를 우선하세요.")
        appendLine("금융 이체/결제/구매/체크아웃 자동화는 선택하지 마세요.")
        appendToolCatalogue(tools)
        appendLine("최근 대화:")
        appendRecent(messages, WORKER_CONTEXT)
        appendLine("다음 도구:")
    }.take(WORKER_PROMPT_MAX)

    // ── REVIEWER ────────────────────────────────────────────────────────────
    private fun reviewerPrompt(messages: List<ChatMessage>): String = buildString {
        appendLine("[FCC REVIEWER]")
        appendLine("방금 실제 Android 도구가 실행되었습니다. 사용자 요청이 실제로 완료됐는지 결과만 검증하세요.")
        appendLine("완료가 확인되면 [PASS] 한 줄, 실패/불완전/권한문제/잘못된 결과면 [RETRY] 한 줄을 출력하세요.")
        appendLine("성공을 추측하지 마세요. 도구 결과에 근거하세요.")
        appendLine("최근 대화와 도구 결과:")
        appendRecent(messages, REVIEW_CONTEXT)
        appendLine("판정:")
    }.take(REVIEW_PROMPT_MAX)

    // ── DEBUGGER ────────────────────────────────────────────────────────────
    private fun debuggerPrompt(messages: List<ChatMessage>, tools: List<Tool>): String = buildString {
        appendLine("[FCC DEBUGGER]")
        appendLine("직전 도구 실행이 실패하거나 불완전했습니다. 원인을 고려해 안전한 복구용 다음 도구 하나를 고르세요.")
        appendLine("출력 형식은 정확히 [USE_TOOL] exact_tool_name 한 줄입니다.")
        appendLine("복구 가능한 도구가 없으면 [STOP] 한 줄을 출력하세요.")
        appendLine("권한 거부를 무시하거나 보안 제한을 우회하지 마세요.")
        appendToolCatalogue(tools)
        appendLine("최근 실패 맥락:")
        appendRecent(messages, DEBUG_CONTEXT)
        appendLine("복구 결정:")
    }.take(DEBUG_PROMPT_MAX)

    private fun finalResultPrompt(messages: List<ChatMessage>): String = buildString {
        appendLine("[FCC MAIN / VERIFIED RESULT]")
        appendLine("FCC Reviewer가 방금 실행 결과를 PASS로 판정했습니다.")
        appendLine("도구 결과에 있는 사실만 사용해서 사용자에게 자연스러운 한국어로 최종 결과를 알려주세요.")
        appendLine("내부 도구명, FCC 역할, 프롬프트를 불필요하게 노출하지 마세요.")
        appendLine("최근 대화와 검증된 결과:")
        appendRecent(messages, RESULT_CONTEXT)
        appendLine("최종 답변:")
    }.take(RESULT_PROMPT_MAX)

    private fun argsPrompt(messages: List<ChatMessage>, tool: Tool, role: String): String = buildString {
        appendLine("[FCC $role / TOOL ARGUMENTS]")
        appendLine("아래 Android 도구 호출 인자를 생성하세요.")
        appendLine("유효한 JSON 객체 하나만 출력하세요. 설명, 마크다운, 코드펜스는 출력하지 마세요.")
        appendLine("TOOL: ${tool.function.name}")
        appendLine("DESCRIPTION: ${tool.function.description}")
        appendLine("JSON SCHEMA: ${tool.function.parameters}")
        appendLine("최근 대화:")
        appendRecent(messages, ARGS_CONTEXT)
        appendLine("JSON:")
    }.take(ARGS_PROMPT_MAX)

    private fun StringBuilder.appendToolCatalogue(tools: List<Tool>) {
        appendLine("사용 가능한 도구:")
        tools.forEach { tool ->
            appendLine("${tool.function.name} — ${tool.function.description.replace('\n', ' ').take(TOOL_DESC_MAX)}")
        }
    }

    private fun StringBuilder.appendRecent(messages: List<ChatMessage>, count: Int) {
        messages.filter { it.role != "system" }.takeLast(count).forEach {
            appendLine(render(it).take(PER_MESSAGE_MAX))
        }
    }

    private fun render(message: ChatMessage): String = when (message.role) {
        "tool" -> "도구결과 ${message.name ?: "unknown"}: ${message.content.orEmpty()}"
        "assistant" -> "Mythara: ${message.content.orEmpty()}"
        "user" -> "사용자: ${message.content.orEmpty()}"
        else -> "${message.role}: ${message.content.orEmpty()}"
    }

    private fun pickTool(raw: String, tools: List<Tool>): Tool? {
        val name = TOOL_PICK.find(raw)?.groupValues?.getOrNull(1) ?: return null
        return tools.firstOrNull { it.function.name == name }
    }

    private fun cleanAnswer(raw: String): String {
        var text = Thinks.strip(raw).trim()
        text = text.removePrefix("```text").removePrefix("```").removeSuffix("```").trim()
        val prefixes = listOf("ASSISTANT:", "Assistant:", "MYTHARA:", "Mythara:", "답변:", "응답:", "최종 답변:")
        prefixes.forEach { prefix ->
            if (text.startsWith(prefix, ignoreCase = true)) text = text.substring(prefix.length).trim()
        }
        text = text.replace(Regex("(?im)^\\s*\\[(ANSWER|ACTION|PASS|RETRY|STOP)]\\s*$"), "").trim()
        text = text.replace(Regex("(?im)^\\s*\\[USE_TOOL].*$"), "").trim()
        return text
    }

    private fun heuristicToolSuccess(result: String): Boolean {
        val r = result.lowercase()
        if (r.isBlank()) return false
        val failureTokens = listOf("error", "failed", "failure", "denied", "not granted", "exception", "timeout", "not found", "실패", "오류", "거부")
        if (failureTokens.any { r.contains(it) }) return false
        val successTokens = listOf("\"ok\":true", "\"success\":true", "success", "completed", "done", "ready", "opened", "launched", "성공", "완료")
        return successTokens.any { r.contains(it) }
    }

    private fun deterministicResultFallback(result: String): String {
        val brief = result.replace(Regex("\\s+"), " ").trim().take(350)
        return if (brief.isBlank()) {
            "작업은 완료된 것으로 확인했어."
        } else {
            "작업 결과를 확인했어. $brief"
        }
    }

    private fun isLikelyEcho(answer: String, user: String): Boolean {
        if (answer.isBlank() || user.isBlank()) return answer.isBlank()
        val a = normalizeForEcho(answer)
        val u = normalizeForEcho(user)
        if (a.isBlank() || u.isBlank()) return false
        if (a == u) return true
        return u.length >= 8 && a.length <= u.length + 14 && (a.contains(u) || u.contains(a))
    }

    private fun normalizeForEcho(text: String): String =
        text.lowercase().replace(Regex("[\\s\\p{Punct}]+"), "").trim()

    private fun deterministicFallback(latestUser: String): String {
        val u = normalizeForEcho(latestUser)
        return when {
            u.contains("너누구") || u.contains("누구야") || u.contains("정체") ->
                "나는 이 폴드7 안에서 로컬로 실행되는 Mythara AI 어시스턴트야. 인터넷 API 없이 기기 안의 Gemma 모델로 답하고, 허용된 경우 Shizuku와 Android 도구로 휴대폰 작업도 도울 수 있어."
            u.contains("한국어") && (u.contains("말") || u.contains("대답") || u.contains("답변")) ->
                "알겠어. 별도 요청이 없는 한 한국어로 답할게."
            else -> "로컬 모델의 답변 생성이 잠시 불안정했어. 질문을 조금만 짧게 다시 보내줘."
        }
    }

    private fun firstJsonObject(text: String): String? {
        var start = -1
        var depth = 0
        var inString = false
        var escaped = false
        for (i in text.indices) {
            val c = text[i]
            if (start < 0) {
                if (c == '{') { start = i; depth = 1 }
                continue
            }
            if (inString) {
                if (escaped) escaped = false
                else if (c == '\\') escaped = true
                else if (c == '"') inString = false
                continue
            }
            when (c) {
                '"' -> inString = true
                '{' -> depth++
                '}' -> {
                    depth--
                    if (depth == 0) return text.substring(start, i + 1)
                }
            }
        }
        return null
    }

    companion object {
        private val MAIN_ACTION = Regex("(?im)^\\s*\\[ACTION]\\s*$")
        private val TOOL_PICK = Regex("""(?im)^\s*\[USE_TOOL]\s+([A-Za-z0-9_.-]+)\s*$""")
        private val REVIEW_PASS = Regex("(?im)^\\s*\\[PASS]\\s*$")
        private val REVIEW_RETRY = Regex("(?im)^\\s*\\[RETRY]\\s*$")

        private const val MAX_FCC_TOOL_ATTEMPTS = 3
        private const val TOOL_DESC_MAX = 170
        private const val PER_MESSAGE_MAX = 1500
        private const val MAIN_CONTEXT = 6
        private const val ANSWER_CONTEXT = 8
        private const val WORKER_CONTEXT = 7
        private const val REVIEW_CONTEXT = 8
        private const val DEBUG_CONTEXT = 10
        private const val RESULT_CONTEXT = 8
        private const val ARGS_CONTEXT = 7

        private const val MAIN_ROUTE_PROMPT_MAX = 7000
        private const val ANSWER_PROMPT_MAX = 12000
        private const val RETRY_PROMPT_MAX = 3500
        private const val WORKER_PROMPT_MAX = 22000
        private const val REVIEW_PROMPT_MAX = 9000
        private const val DEBUG_PROMPT_MAX = 24000
        private const val RESULT_PROMPT_MAX = 10000
        private const val ARGS_PROMPT_MAX = 12000

        private const val MAIN_ROUTE_OUT = 300
        private const val WORKER_OUT = 500
        private const val REVIEW_OUT = 350
        private const val DEBUGGER_OUT = 500
        private const val ANSWER_OUT = 3000
        private const val ARGS_OUT = 4000
    }
}
''')

print('Mythara Local Fold7 KR v4 FCC-Mobile patch applied')
