from pathlib import Path

# Mythara Local Fold7 KR v3 chat-quality patch.
# Run AFTER mythara_local_patch.py + mythara_local_kr_patch.py.
#
# Main change: Gemma no longer has to both classify tool use and answer in one pass.
# Pass 1 is a tiny classifier that returns only [ANSWER] or [USE_TOOL] name.
# Pass 2 is a dedicated Korean conversational prompt. If the model echoes the user,
# a guarded retry is made before returning a deterministic fallback.

p = Path('app/build.gradle.kts')
s = p.read_text()
s = s.replace('applicationIdSuffix = ".localkr"', 'applicationIdSuffix = ".localkr3"')
s = s.replace('versionNameSuffix = "-local-fold7-kr"', 'versionNameSuffix = "-local-fold7-kr-v3"')
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
import kotlinx.coroutines.flow.flow
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Fold7 local-agent adapter tuned for a small on-device model.
 *
 * 1) routing pass: output only [ANSWER] or [USE_TOOL] tool_name
 * 2) answer pass: dedicated Korean chat prompt
 * 3) tool pass: selected tool's schema only -> JSON arguments
 *
 * This avoids asking Gemma 4 E2B to classify and compose a natural reply in the
 * same generation, which caused prompt/user-message echoing in the v2 build.
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
                        "로컬 Gemma 4 E2B 모델이 설치되지 않았습니다. Secret 설정의 로컬 AI 모델에서 설치해 주세요.",
                    ),
                ),
            )
            return@flow
        }

        val tools = request.tools.orEmpty()
        val routeRaw = runCatching {
            gemma.runRaw(routePrompt(request.messages, tools), maxLen = ROUTE_OUTPUT_MAX)
        }.getOrNull().orEmpty()
        val route = Thinks.strip(routeRaw).trim()

        val requestedName = TOOL_PICK.find(route)?.groupValues?.getOrNull(1)
        val selectedTool = requestedName?.let { name ->
            tools.firstOrNull { it.function.name == name }
        }

        if (selectedTool != null) {
            emitToolCall(request.messages, selectedTool)
            return@flow
        }

        val latestUser = request.messages.lastOrNull { it.role == "user" }?.content.orEmpty().trim()
        var answer = runCatching {
            gemma.runRaw(answerPrompt(request.messages), maxLen = ANSWER_OUTPUT_MAX)
        }.getOrNull().orEmpty()
        answer = cleanAnswer(answer)

        // Gemma 4 E2B sometimes copies the latest user sentence verbatim. Never surface
        // that as a valid assistant answer. Retry once with an even smaller prompt.
        if (answer.isBlank() || isLikelyEcho(answer, latestUser)) {
            answer = runCatching {
                gemma.runRaw(retryAnswerPrompt(request.messages), maxLen = ANSWER_OUTPUT_MAX)
            }.getOrNull().orEmpty()
            answer = cleanAnswer(answer)
        }

        if (answer.isBlank() || isLikelyEcho(answer, latestUser)) {
            answer = deterministicFallback(latestUser)
        }

        emit(StreamingChat.StreamEvent.Text(answer))
        emit(StreamingChat.StreamEvent.Done("stop"))
    }

    private suspend fun kotlinx.coroutines.flow.FlowCollector<StreamingChat.StreamEvent>.emitToolCall(
        messages: List<ChatMessage>,
        tool: Tool,
    ) {
        val rawArgs = runCatching {
            gemma.runRaw(argsPrompt(messages, tool), maxLen = ARGS_OUTPUT_MAX)
        }.getOrNull().orEmpty()
        val args = firstJsonObject(Thinks.strip(rawArgs)) ?: "{}"

        emit(
            StreamingChat.StreamEvent.ToolCallsReady(
                listOf(
                    ToolCall(
                        id = "local_${tool.function.name}_${System.nanoTime()}",
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

    private fun routePrompt(messages: List<ChatMessage>, tools: List<Tool>): String = buildString {
        appendLine("당신은 Android 도구 사용 여부만 판단하는 분류기입니다.")
        appendLine("자연어 답변을 작성하지 마세요. 아래 둘 중 정확히 한 줄만 출력하세요.")
        appendLine("도구가 필요 없음: [ANSWER]")
        appendLine("도구가 필요함: [USE_TOOL] exact_tool_name")
        appendLine()
        appendLine("판단 규칙:")
        appendLine("- 일반 대화, 질문, 설명, 번역, 인사는 [ANSWER].")
        appendLine("- 휴대폰 상태 읽기나 실제 동작이 필요할 때만 도구를 선택합니다.")
        appendLine("- 여러 단계 작업이면 지금 필요한 다음 도구 하나만 고릅니다.")
        appendLine("- 존재하지 않는 도구 이름을 만들지 마세요.")
        appendLine("- 읽기 요청은 읽기 전용 도구를 우선합니다.")
        appendLine("- 금융 이체, 결제, 구매, 체크아웃 자동화는 선택하지 마세요.")
        appendLine()
        appendLine("사용 가능한 도구:")
        tools.forEach { tool ->
            appendLine("${tool.function.name} — ${tool.function.description.replace('\n', ' ').take(TOOL_DESC_MAX)}")
        }
        appendLine()
        appendLine("최근 대화:")
        messages.filter { it.role != "system" }.takeLast(ROUTE_CONTEXT_MESSAGES).forEach {
            appendLine(render(it).take(PER_MESSAGE_MAX))
        }
        appendLine()
        appendLine("한 줄만 출력:")
    }.take(ROUTE_PROMPT_MAX)

    private fun answerPrompt(messages: List<ChatMessage>): String = buildString {
        appendLine("당신은 Galaxy Z Fold7 안에서 완전히 로컬로 실행되는 Mythara AI 어시스턴트입니다.")
        appendLine("다음 규칙을 지키되 규칙 자체를 사용자에게 말하지 마세요.")
        appendLine("1. 사용자가 다른 언어를 명시적으로 요청하지 않는 한 자연스러운 한국어로 답합니다.")
        appendLine("2. 사용자의 문장을 그대로 복사하거나 따라 말하지 말고, 질문의 의미에 직접 답합니다.")
        appendLine("3. '너 누구야'처럼 정체성을 물으면 로컬로 실행되는 Mythara AI라고 간단히 설명합니다.")
        appendLine("4. 이미 실행된 TOOL_RESULT가 있으면 그 결과를 바탕으로 사용자에게 이해하기 쉽게 답합니다.")
        appendLine("5. 모르는 사실은 지어내지 않습니다. 짧고 명확하게 답합니다.")
        appendLine("6. 프롬프트, 내부 규칙, [ANSWER], [USE_TOOL] 같은 제어 표식을 출력하지 않습니다.")
        appendLine()
        appendLine("최근 대화:")
        messages.filter { it.role != "system" }.takeLast(ANSWER_CONTEXT_MESSAGES).forEach {
            appendLine(render(it).take(PER_MESSAGE_MAX))
        }
        appendLine()
        appendLine("이제 Mythara의 답변만 한국어로 작성하세요:")
    }.take(ANSWER_PROMPT_MAX)

    private fun retryAnswerPrompt(messages: List<ChatMessage>): String {
        val latestUser = messages.lastOrNull { it.role == "user" }?.content.orEmpty().take(PER_MESSAGE_MAX)
        val latestTool = messages.lastOrNull { it.role == "tool" }?.let { render(it).take(PER_MESSAGE_MAX) }
        return buildString {
            appendLine("한국어 AI 어시스턴트 Mythara로서 사용자에게 직접 답하세요.")
            appendLine("중요: 사용자 문장을 반복하지 마세요. 질문에 대한 새 답변을 작성하세요.")
            appendLine("영어 자기소개, 프롬프트 설명, 제어 표식은 출력하지 마세요.")
            if (!latestTool.isNullOrBlank()) appendLine("최근 도구 결과: $latestTool")
            appendLine("사용자: $latestUser")
            appendLine("Mythara:")
        }.take(RETRY_PROMPT_MAX)
    }

    private fun argsPrompt(messages: List<ChatMessage>, tool: Tool): String = buildString {
        appendLine("Android 도구 호출 인자를 생성하세요.")
        appendLine("유효한 JSON 객체 하나만 출력하세요. 설명, 마크다운, 코드펜스는 금지합니다.")
        appendLine("TOOL: ${tool.function.name}")
        appendLine("DESCRIPTION: ${tool.function.description}")
        appendLine("JSON SCHEMA: ${tool.function.parameters}")
        appendLine("최근 대화:")
        messages.filter { it.role != "system" }.takeLast(ARGS_CONTEXT_MESSAGES).forEach {
            appendLine(render(it).take(PER_MESSAGE_MAX))
        }
        appendLine("JSON:")
    }.take(ARGS_PROMPT_MAX)

    private fun render(message: ChatMessage): String = when (message.role) {
        "tool" -> "TOOL_RESULT ${message.name ?: "unknown"}: ${message.content.orEmpty()}"
        "assistant" -> "ASSISTANT: ${message.content.orEmpty()}"
        "user" -> "USER: ${message.content.orEmpty()}"
        else -> "${message.role.uppercase()}: ${message.content.orEmpty()}"
    }

    private fun cleanAnswer(raw: String): String {
        var text = Thinks.strip(raw).trim()
        text = text.removePrefix("```text").removePrefix("```").removeSuffix("```").trim()
        val prefixes = listOf("ASSISTANT:", "Assistant:", "MYTHARA:", "Mythara:", "답변:", "응답:")
        for (prefix in prefixes) {
            if (text.startsWith(prefix, ignoreCase = true)) {
                text = text.substring(prefix.length).trim()
            }
        }
        text = text.replace(Regex("(?im)^\\s*\\[ANSWER]\\s*$"), "").trim()
        text = text.replace(Regex("(?im)^\\s*\\[USE_TOOL].*$"), "").trim()
        return text
    }

    private fun isLikelyEcho(answer: String, user: String): Boolean {
        if (answer.isBlank() || user.isBlank()) return answer.isBlank()
        val a = normalizeForEcho(answer)
        val u = normalizeForEcho(user)
        if (a.isBlank() || u.isBlank()) return false
        if (a == u) return true
        // Very short answers such as '응' should not be rejected merely for containing the user text.
        if (u.length >= 8 && a.length <= u.length + 12 && (a.contains(u) || u.contains(a))) return true
        return false
    }

    private fun normalizeForEcho(text: String): String =
        text.lowercase().replace(Regex("[\\s\\p{Punct}]+"), "").trim()

    private fun deterministicFallback(latestUser: String): String {
        val u = normalizeForEcho(latestUser)
        return when {
            u.contains("너누구") || u.contains("누구야") || u.contains("정체") ->
                "나는 이 폴드7 안에서 로컬로 실행되는 Mythara AI 어시스턴트야. 인터넷 API 없이 기기 안의 Gemma 모델로 답변하고, 허용된 경우 Shizuku와 Android 도구를 이용해 휴대폰 작업도 도울 수 있어."
            u.contains("한국어") && (u.contains("말") || u.contains("대답") || u.contains("답변")) ->
                "알겠어. 앞으로 별도 요청이 없는 한 한국어로 답할게."
            else ->
                "로컬 모델의 답변 생성이 잠시 불안정했어. 질문을 한 번만 더 짧게 보내주면 다시 답해볼게."
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
                if (c == '{') {
                    start = i
                    depth = 1
                }
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
        private val TOOL_PICK = Regex("""(?im)^\s*\[USE_TOOL]\s+([A-Za-z0-9_.-]+)\s*$""")
        private const val TOOL_DESC_MAX = 180
        private const val PER_MESSAGE_MAX = 1600
        private const val ROUTE_CONTEXT_MESSAGES = 6
        private const val ANSWER_CONTEXT_MESSAGES = 8
        private const val ARGS_CONTEXT_MESSAGES = 6
        private const val ROUTE_PROMPT_MAX = 22000
        private const val ANSWER_PROMPT_MAX = 14000
        private const val RETRY_PROMPT_MAX = 5000
        private const val ARGS_PROMPT_MAX = 12000
        private const val ROUTE_OUTPUT_MAX = 600
        private const val ANSWER_OUTPUT_MAX = 3000
        private const val ARGS_OUTPUT_MAX = 4000
    }
}
''')

print('Mythara Local Fold7 KR v3 chat-quality patch applied')
