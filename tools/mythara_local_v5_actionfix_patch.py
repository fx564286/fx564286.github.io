from pathlib import Path

# Mythara Local Fold7 KR FCC v5
# - keep the v4 package id stable for future in-place updates
# - fix human colour names for apply_cosmetic
# - route image generation deterministically to generate_image
# - display generated images automatically through render_canvas
# - answer capability questions from the actual registered tool set

# ---------------------------------------------------------------------
# Stable package/version.
# ---------------------------------------------------------------------
p = Path('app/build.gradle.kts')
s = p.read_text()
s = s.replace('applicationIdSuffix = ".localkr4"', 'applicationIdSuffix = ".localkr4"')
s = s.replace('versionNameSuffix = "-local-fold7-kr-v4"', 'versionNameSuffix = "-local-fold7-kr-v5"')
s = s.replace('versionCode = 1', 'versionCode = 5', 1)
p.write_text(s)

# ---------------------------------------------------------------------
# CosmeticTool: map common Korean/English colour names to valid ARGB.
# ---------------------------------------------------------------------
p = Path('app/src/main/kotlin/com/mythara/agent/tools/CosmeticTool.kt')
s = p.read_text()
old = '''        val key = args["key"]?.jsonPrimitive?.contentOrNull()?.trim().orEmpty()\n        val value = args["value"]?.jsonPrimitive?.contentOrNull()?.trim().orEmpty()\n        if (key.isBlank() || value.isBlank()) return ToolResult.fail("key + value required")\n'''
new = '''        val key = args["key"]?.jsonPrimitive?.contentOrNull()?.trim().orEmpty()\n        val rawValue = args["value"]?.jsonPrimitive?.contentOrNull()?.trim().orEmpty()\n        val value = normalizeCosmeticValue(key, rawValue)\n        if (key.isBlank() || value.isBlank()) return ToolResult.fail("key + value required")\n'''
if old not in s:
    raise SystemExit('CosmeticTool execute anchor not found')
s = s.replace(old, new, 1)
anchor = '    private fun setupCard(reason: String): String = when (reason) {\n'
helper = r'''    /** Human colour names -> valid ARGB accepted by accent_color. */
    private fun normalizeCosmeticValue(key: String, raw: String): String {
        if (key != "accent_color") return raw
        if (raw.matches(Regex("^#?[0-9a-fA-F]{6,8}$"))) return raw
        val n = raw.lowercase()
            .replace(" ", "")
            .replace("-", "")
            .replace("_", "")
            .replace("계열", "")
            .replace("색", "")
        return when (n) {
            "pink", "핑크", "분홍" -> "#FFFF69B4"
            "hotpink", "진한핑크", "핫핑크" -> "#FFFF1493"
            "rose", "로즈", "장미" -> "#FFFF4F81"
            "red", "빨강", "빨간" -> "#FFF44336"
            "orange", "주황" -> "#FFFF9800"
            "yellow", "노랑", "노란" -> "#FFFFEB3B"
            "green", "초록", "녹색" -> "#FF4CAF50"
            "mint", "민트" -> "#FF00BFA5"
            "blue", "파랑", "파란" -> "#FF2196F3"
            "navy", "남색" -> "#FF3F51B5"
            "purple", "보라" -> "#FF9C27B0"
            "lavender", "라벤더" -> "#FFB187FF"
            "black", "검정", "검은" -> "#FF000000"
            "white", "흰", "하양", "하얀" -> "#FFFFFFFF"
            else -> raw
        }
    }

'''
if anchor not in s:
    raise SystemExit('CosmeticTool helper anchor not found')
s = s.replace(anchor, helper + anchor, 1)
p.write_text(s)

# ---------------------------------------------------------------------
# FCC local chat: deterministic capability + image routing.
# ---------------------------------------------------------------------
p = Path('app/src/main/kotlin/com/mythara/local/LocalGemmaChat.kt')
s = p.read_text()
needle = '''        val latestUser = messages.lastOrNull { it.role == "user" }?.content.orEmpty().trim()\n\n        // MAIN: only decide whether this is ordinary conversation or a real\n'''
insert = '''        val latestUser = messages.lastOrNull { it.role == "user" }?.content.orEmpty().trim()\n\n        // Deterministic capability answers prevent the small local model from\n        // claiming that registered tools do not exist.\n        if (isCapabilityQuestion(latestUser)) {\n            emit(StreamingChat.StreamEvent.Text(capabilitySummary(tools)))\n            emit(StreamingChat.StreamEvent.Done("stop"))\n            return@flow\n        }\n\n        // Image generation already exists in upstream Mythara. Do not ask a\n        // 2B local model to discover this among dozens of tools: route it\n        // directly. GenerateImageTool itself will explain if the Gemini key is\n        // missing or quota is unavailable.\n        if (isImageGenerationRequest(latestUser)) {\n            val imageTool = tools.firstOrNull { it.function.name == "generate_image" }\n            if (imageTool != null) {\n                val promptJson = kotlinx.serialization.json.JsonPrimitive(latestUser).toString()\n                emitDirectToolCall(imageTool, "{\\\"prompt\\\":" + promptJson + "}", "WORKER")\n                return@flow\n            }\n        }\n\n        // MAIN: only decide whether this is ordinary conversation or a real\n'''
if needle not in s:
    raise SystemExit('LocalGemmaChat stream anchor not found')
s = s.replace(needle, insert, 1)

needle = '''        val toolResult = messages.lastOrNull { it.role == "tool" }?.content.orEmpty()\n\n        // REVIEWER: must explicitly PASS or RETRY based on the actual tool output.\n'''
insert = '''        val toolResult = messages.lastOrNull { it.role == "tool" }?.content.orEmpty()\n\n        // generate_image returns a private local file path. Automatically send\n        // that path to render_canvas so the user sees the image instead of a\n        // text-only success message.\n        if (lastExecutedToolName(messages) == "generate_image") {\n            val path = Regex("\\\"path\\\"\\s*:\\s*\\\"([^\\\"]+)\\\"")\n                .find(toolResult)?.groupValues?.getOrNull(1)\n            val canvasTool = tools.firstOrNull { it.function.name == "render_canvas" }\n            if (!path.isNullOrBlank() && canvasTool != null) {\n                val html = \"<div style='margin:0;background:#111;min-height:100vh;display:flex;align-items:center;justify-content:center'><img src='file://\" + path + \"' style='max-width:100%;height:auto;display:block'/></div>\"\n                val htmlJson = kotlinx.serialization.json.JsonPrimitive(html).toString()\n                val args = \"{\\\"html\\\":\" + htmlJson + \",\\\"template\\\":\\\"blank\\\",\\\"mode\\\":\\\"inline\\\",\\\"retain\\\":true,\\\"auto_navigate\\\":true}\"\n                emitDirectToolCall(canvasTool, args, "WORKER")\n                return\n            }\n        }\n\n        // REVIEWER: must explicitly PASS or RETRY based on the actual tool output.\n'''
if needle not in s:
    raise SystemExit('LocalGemmaChat tool-result anchor not found')
s = s.replace(needle, insert, 1)

anchor = '''    // ── MAIN ────────────────────────────────────────────────────────────────\n'''
helpers = r'''    private suspend fun FlowCollector<StreamingChat.StreamEvent>.emitDirectToolCall(
        tool: Tool,
        argsJson: String,
        role: String,
    ) {
        emit(
            StreamingChat.StreamEvent.ToolCallsReady(
                listOf(
                    ToolCall(
                        id = "fcc_${role.lowercase()}_${tool.function.name}_${System.nanoTime()}",
                        type = "function",
                        function = ToolCallFunction(
                            name = tool.function.name,
                            arguments = argsJson,
                        ),
                    ),
                ),
            ),
        )
        emit(StreamingChat.StreamEvent.Done("tool_calls"))
    }

    private fun lastExecutedToolName(messages: List<ChatMessage>): String? {
        messages.lastOrNull { it.role == "tool" }?.name?.let { if (it.isNotBlank()) return it }
        return messages.asReversed()
            .firstOrNull { it.role == "assistant" && !it.toolCalls.isNullOrEmpty() }
            ?.toolCalls?.lastOrNull()?.function?.name
    }

    private fun isImageGenerationRequest(text: String): Boolean {
        val t = text.replace(" ", "").lowercase()
        val hasImageWord = listOf("이미지", "그림", "사진", "일러스트", "포스터").any { t.contains(it) }
        val asksCreate = listOf("만들어줘", "만들어", "생성해줘", "생성해", "그려줘", "그려").any { t.contains(it) }
        val asksCamera = listOf("찍어줘", "촬영해", "카메라").any { t.contains(it) }
        val isCapabilityList = (t.contains("영상") || t.contains("음악") || t.contains("노래")) &&
            (t.endsWith("?") || t.contains("가능") || t.contains("할수"))
        return hasImageWord && asksCreate && !asksCamera && !isCapabilityList
    }

    private fun isCapabilityQuestion(text: String): Boolean {
        val t = text.replace(" ", "").lowercase()
        if (listOf("뭘할수", "뭐할수", "무엇을할수", "어떤작업", "지원할수", "지원해", "기능이뭐", "가능한작업").any { t.contains(it) }) return true
        val mediaWords = listOf("사진", "이미지", "그림", "영상", "음악", "노래").count { t.contains(it) }
        return mediaWords >= 2 && (t.endsWith("?") || t.contains("만들기는") || t.contains("가능"))
    }

    private fun capabilitySummary(tools: List<Tool>): String {
        val names = tools.map { it.function.name }.toSet()
        val parts = mutableListOf<String>()
        if ("read_screen" in names || "tap" in names || "open_app" in names) {
            parts += "화면 읽기, 앱 실행, 탭·스와이프·텍스트 입력 같은 휴대폰 조작"
        }
        if ("send_sms_direct" in names || "place_call_direct" in names) {
            parts += "문자·전화 같은 통신 작업(필요 시 확인 절차 포함)"
        }
        if ("apply_cosmetic" in names) {
            parts += "Shizuku를 이용한 글자 크기·다크 모드·일부 시스템 꾸미기"
        }
        if ("take_photo" in names || "search_photos" in names) {
            parts += "카메라 촬영과 사진 검색"
        }
        if ("generate_image" in names) {
            parts += "이미지 생성(Gemini API 키가 설정되어 있을 때)"
        }
        if ("render_canvas" in names) {
            parts += "Canvas에 카드·HTML·간단한 2D/3D 화면 표시"
        }
        if ("run_shell" in names || "termux_exec" in names) {
            parts += "허용 범위의 셸·Termux 작업"
        }
        val body = if (parts.isEmpty()) "현재 등록된 휴대폰 도구를 확인하지 못했어." else parts.joinToString("\n• ", prefix = "• ")
        return "현재 이 폰에서 가능한 주요 작업은 다음과 같아.\n$body\n\n현재 기본 도구에는 영상 생성이나 완성된 음악/노래 생성 엔진은 연결되어 있지 않아. 이미지 생성은 로컬 Gemma가 아니라 Gemini 이미지 API를 사용하므로 해당 기능만 인터넷과 Gemini API 키가 필요해."
    }

'''
if anchor not in s:
    raise SystemExit('LocalGemmaChat helper insertion anchor not found')
s = s.replace(anchor, helpers + anchor, 1)

# Improve the generic router wording too, for non-deterministic visual tools.
s = s.replace(
    '휴대폰 상태 읽기, 앱 실행, 화면 조작, 메시지/전화/일정/설정 변경 등 실제 Android 기능이 필요하면 [ACTION]을 출력하세요.',
    '휴대폰 상태 읽기, 앱 실행, 화면 조작, 메시지/전화/일정/설정 변경, 이미지 생성, Canvas 표시 등 실제 도구가 필요하면 [ACTION]을 출력하세요.',
)
p.write_text(s)

print('Mythara Local Fold7 KR FCC v5 action fixes applied')
