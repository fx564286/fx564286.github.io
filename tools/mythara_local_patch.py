from pathlib import Path

# Run from the cloned upstream Mythara repository root.

# Remove Meta DAT dependencies and give this build its own installable package id.
p = Path('app/build.gradle.kts')
s = p.read_text()
for line in (
    '    implementation(libs.mwdat.core)\n',
    '    implementation(libs.mwdat.camera)\n',
    '    implementation(libs.mwdat.display)\n',
):
    s = s.replace(line, '')
s = s.replace('applicationIdSuffix = ".debug"', 'applicationIdSuffix = ".local"')
s = s.replace('versionNameSuffix = "-debug"', 'versionNameSuffix = "-local-fold7"')
p.write_text(s)

# Remove the authenticated Meta GitHub Packages repository block.
p = Path('settings.gradle.kts')
s = p.read_text()
start = s.find('        maven {\n            name = "MetaWearablesDAT"')
if start >= 0:
    depth = 0
    seen = False
    i = start
    while i < len(s):
        if s[i] == '{':
            depth += 1
            seen = True
        elif s[i] == '}':
            depth -= 1
            if seen and depth == 0:
                s = s[:start] + s[i + 1:]
                break
        i += 1
p.write_text(s)

# No-op Meta glasses integration. Local AI / Shizuku / Accessibility / phone tools remain.
Path('app/src/main/kotlin/com/mythara/glasses/GlassesDatFacade.kt').write_text(r'''package com.mythara.glasses

import android.app.Activity
import android.content.Context
import android.graphics.Bitmap
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow

object GlassesDatFacade {
    const val DISPLAY_PATH_ENABLED = false

    enum class DatPermission { Unknown, Granted, Denied }

    data class GlassesDeviceInfo(
        val id: String,
        val name: String,
        val firmware: String,
        val linkState: String,
        val displayCapable: Boolean,
        val compatibility: String,
    )

    private val _connectionState = MutableStateFlow(GlassesConnectionState.NotInitialized)
    val connectionState: StateFlow<GlassesConnectionState> = _connectionState.asStateFlow()
    private val _lastRegistrationError = MutableStateFlow<String?>("Meta glasses disabled in Local Fold7 build")
    val lastRegistrationError: StateFlow<String?> = _lastRegistrationError.asStateFlow()
    private val _lastSessionError = MutableStateFlow<String?>(null)
    val lastSessionError: StateFlow<String?> = _lastSessionError.asStateFlow()
    private val _glassesAppUpdateRequired = MutableStateFlow(false)
    val glassesAppUpdateRequired: StateFlow<Boolean> = _glassesAppUpdateRequired.asStateFlow()
    private val _cameraPermission = MutableStateFlow(DatPermission.Unknown)
    val cameraPermission: StateFlow<DatPermission> = _cameraPermission.asStateFlow()
    private val _microphonePermission = MutableStateFlow(DatPermission.Unknown)
    val microphonePermission: StateFlow<DatPermission> = _microphonePermission.asStateFlow()
    private val _discoveredDevices = MutableStateFlow<List<GlassesDeviceInfo>>(emptyList())
    val discoveredDevices: StateFlow<List<GlassesDeviceInfo>> = _discoveredDevices.asStateFlow()
    private val _firmwareUpdateRequired = MutableStateFlow(false)
    val firmwareUpdateRequired: StateFlow<Boolean> = _firmwareUpdateRequired.asStateFlow()
    private val _events = MutableSharedFlow<GlassesEvent>(
        extraBufferCapacity = 8,
        onBufferOverflow = BufferOverflow.DROP_OLDEST,
    )
    val events: SharedFlow<GlassesEvent> = _events.asSharedFlow()

    fun isAvailable(): Boolean = false
    fun initializeIfAvailable(context: Context) { _connectionState.value = GlassesConnectionState.NotInitialized }
    fun reinitialize(context: Context) = initializeIfAvailable(context)
    fun startRegistration(activity: Activity) = Unit
    fun startUnregistration(activity: Activity) = Unit
    suspend fun openDATGlassesAppUpdate(activity: Activity) = Unit
    suspend fun openFirmwareUpdate(activity: Activity) = Unit
    suspend fun refreshDatPermissions() = Unit
    suspend fun refreshCameraPermission() = Unit
    suspend fun startSession(): Boolean = false
    fun stopSession() = Unit
    suspend fun render(screen: GlassesScreen): Boolean = false
    suspend fun capturePhoto(): Bitmap? = null
    fun publishEvent(event: GlassesEvent) { _events.tryEmit(event) }
}

enum class GlassesConnectionState {
    NotInitialized, Initialized, Paired, SessionActive, Disconnected, Error,
}
''')

Path('app/src/main/kotlin/com/mythara/glasses/GlassesScreenRenderer.kt').write_text(
    'package com.mythara.glasses\n\ninternal object GlassesScreenRenderer\n'
)

Path('app/src/main/kotlin/com/mythara/ui/settings/GlassesPanel.kt').write_text(r'''package com.mythara.ui.settings

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

@Composable
fun GlassesPanel() {
    Column(Modifier.fillMaxWidth().padding(16.dp)) {
        Text("Meta glasses integration is disabled in Mythara Local Fold7.")
        Text("Shizuku, phone control and local AI remain enabled.")
    }
}
''')

# Main local agent adapter. Gemma first chooses one tool, then receives only that tool's
# full schema to generate arguments. This keeps the prompt manageable for a mobile model.
local_dir = Path('app/src/main/kotlin/com/mythara/local')
local_dir.mkdir(parents=True, exist_ok=True)
(local_dir / 'LocalGemmaChat.kt').write_text(r'''package com.mythara.local

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
                        "Local Gemma model is not installed. Download Gemma 4 E2B in onboarding or Secret settings.",
                    ),
                ),
            )
            return@flow
        }

        val tools = request.tools.orEmpty()
        val routed = runCatching {
            gemma.runRaw(routePrompt(request.messages, tools), maxLen = 6000)
        }.getOrNull()

        if (routed.isNullOrBlank()) {
            emit(
                StreamingChat.StreamEvent.Failure(
                    ErrorMapper.Mapped(0, "LOCAL_INFERENCE_FAILED", "Local Gemma inference failed."),
                ),
            )
            return@flow
        }

        val text = Thinks.strip(routed).trim()
        val requestedName = TOOL_PICK.find(text)?.groupValues?.getOrNull(1)
        val selectedTool = requestedName?.let { name ->
            tools.firstOrNull { it.function.name == name }
        }

        if (selectedTool == null) {
            val answer = text.replace(TOOL_PICK, "").trim().ifBlank {
                "Local model returned an empty answer."
            }
            emit(StreamingChat.StreamEvent.Text(answer))
            emit(StreamingChat.StreamEvent.Done("stop"))
            return@flow
        }

        val rawArgs = runCatching {
            gemma.runRaw(argsPrompt(request.messages, selectedTool), maxLen = 4000)
        }.getOrNull().orEmpty()
        val args = firstJsonObject(rawArgs) ?: "{}"

        emit(
            StreamingChat.StreamEvent.ToolCallsReady(
                listOf(
                    ToolCall(
                        id = "local_${selectedTool.function.name}_${System.nanoTime()}",
                        type = "function",
                        function = ToolCallFunction(
                            name = selectedTool.function.name,
                            arguments = args,
                        ),
                    ),
                ),
            ),
        )
        emit(StreamingChat.StreamEvent.Done("tool_calls"))
    }

    private fun routePrompt(messages: List<ChatMessage>, tools: List<Tool>): String = buildString {
        appendLine("You are Mythara, a private Android assistant running entirely on this phone.")
        appendLine("If the latest user request needs ONE phone tool, output exactly: [USE_TOOL] exact_tool_name")
        appendLine("Otherwise answer directly. For multi-step work choose only the NEXT tool.")
        appendLine("Never invent tool names. Read-only requests must not cause side effects.")
        appendLine("Never automate banking, payments, purchases, checkout, or financial transfers.")
        appendLine("TOOLS:")
        tools.forEach { tool ->
            appendLine("${tool.function.name} — ${tool.function.description.replace('\n', ' ').take(220)}")
        }
        appendLine("RECENT CONVERSATION:")
        messages.filter { it.role != "system" }.takeLast(12).forEach {
            appendLine(render(it).take(2000))
        }
        appendLine("Answer now, or output one [USE_TOOL] marker.")
    }.take(28000)

    private fun argsPrompt(messages: List<ChatMessage>, tool: Tool): String = buildString {
        appendLine("Return ONLY one valid JSON object with arguments for this Android tool.")
        appendLine("No markdown and no explanation.")
        appendLine("TOOL: ${tool.function.name}")
        appendLine("DESCRIPTION: ${tool.function.description}")
        appendLine("JSON SCHEMA: ${tool.function.parameters}")
        appendLine("RECENT CONVERSATION:")
        messages.filter { it.role != "system" }.takeLast(6).forEach {
            appendLine(render(it).take(2000))
        }
    }.take(12000)

    private fun render(message: ChatMessage): String = when (message.role) {
        "tool" -> "TOOL_RESULT ${message.name ?: "unknown"}: ${message.content.orEmpty()}"
        "assistant" -> "ASSISTANT: ${message.content.orEmpty()}"
        else -> "${message.role.uppercase()}: ${message.content.orEmpty()}"
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
    }
}
''')

# Route AgentLoop entirely through LocalGemmaChat and remove the API-key requirement.
p = Path('app/src/main/kotlin/com/mythara/agent/AgentLoop.kt')
s = p.read_text()

old = '''    private val termuxAvailability: com.mythara.services.TermuxAvailability,\n) {'''
new = '''    private val termuxAvailability: com.mythara.services.TermuxAvailability,\n    private val localGemmaChat: com.mythara.local.LocalGemmaChat,\n) {'''
if old not in s:
    raise SystemExit('AgentLoop constructor anchor missing')
s = s.replace(old, new, 1)

old = '''        val snap = settings.snapshot()\n        val apiKey = snap.apiKey\n        if (apiKey.isNullOrBlank()) {\n            emit(Turn.MissingApiKey); return@flow\n        }'''
new = '''        val snap = settings.snapshot()\n        if (!localGemmaChat.isReady()) {\n            emit(\n                Turn.Error(\n                    "Local Gemma 4 E2B is not installed yet. Download it in onboarding or Secret settings, then retry.",\n                    retryable = false,\n                ),\n            )\n            return@flow\n        }'''
if old not in s:
    raise SystemExit('AgentLoop API-key anchor missing')
s = s.replace(old, new, 1)

old = '''        val client = MiniMaxClient(apiKey = apiKey, region = snap.region)\n        val streaming = StreamingChat(client)'''
if old not in s:
    raise SystemExit('AgentLoop cloud streaming anchor missing')
s = s.replace(old, '        // Local Fold7 build: no cloud client is instantiated for the main agent.', 1)

old = '''            streaming.stream(snap.region, req).collect { ev ->'''
if old not in s:
    raise SystemExit('AgentLoop stream collect anchor missing')
s = s.replace(old, '''            localGemmaChat.stream(req).collect { ev ->''', 1)
p.write_text(s)

# Change visible app name when the conventional string exists.
strings = Path('app/src/main/res/values/strings.xml')
if strings.exists():
    t = strings.read_text()
    t = t.replace('<string name="app_name">Mythara</string>', '<string name="app_name">Mythara Local</string>')
    strings.write_text(t)

print('Mythara Local Fold7 patch applied')
