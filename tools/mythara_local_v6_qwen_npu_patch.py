from pathlib import Path

# Mythara Local Fold7 KR FCC v6
# Main model: Qualcomm GenieX + Qwen3-VL-4B-Instruct, QAIRT w4a16 on SM8750.
# Existing Gemma/LiteRT-LM remains as an offline fallback and Observe extractor.

# -----------------------------------------------------------------------------
# Build config: stable package/signing line stays unchanged, versionCode -> 6,
# add Qualcomm GenieX Android binding and extract JNI libs for QAIRT discovery.
# -----------------------------------------------------------------------------
p = Path('app/build.gradle.kts')
s = p.read_text()
s = s.replace('versionNameSuffix = "-local-fold7-kr-v5"', 'versionNameSuffix = "-local-fold7-kr-v6"')
s = s.replace('versionCode = 5', 'versionCode = 6', 1)
if 'com.qualcomm.qti:geniex-android:0.3.5' not in s:
    anchor = 'dependencies {\n'
    s = s.replace(anchor, anchor + '    // v6: Qualcomm GenieX / QAIRT for Snapdragon 8 Elite Hexagon NPU.\n    implementation("com.qualcomm.qti:geniex-android:0.3.5")\n\n', 1)
if 'jniLibs {' not in s:
    anchor = '    packaging {\n'
    s = s.replace(anchor, anchor + '        jniLibs {\n            // QAIRT dispatch scans nativeLibraryDir; force extracted JNI libs.\n            useLegacyPackaging = true\n        }\n', 1)
p.write_text(s)

# -----------------------------------------------------------------------------
# Qualcomm NPU runtime singleton.
# - downloads the official AI Hub model for SM8750
# - loads QAIRT / HTP0
# - one resident VLM shared by FCC roles and vision
# - serializes all native inference
# -----------------------------------------------------------------------------
qdir = Path('app/src/main/kotlin/com/mythara/local')
qdir.mkdir(parents=True, exist_ok=True)
(qdir / 'QwenNpuRuntime.kt').write_text(r'''package com.mythara.local

import android.content.Context
import android.util.Log
import com.geniex.sdk.GenieXSdk
import com.geniex.sdk.ModelManagerWrapper
import com.geniex.sdk.VlmWrapper
import com.geniex.sdk.bean.GenerationConfig
import com.geniex.sdk.bean.HubSource
import com.geniex.sdk.bean.LlmStreamResult
import com.geniex.sdk.bean.ModelConfig
import com.geniex.sdk.bean.ModelPullInput
import com.geniex.sdk.bean.VlmChatMessage
import com.geniex.sdk.bean.VlmContent
import com.geniex.sdk.bean.VlmCreateInput
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton
import kotlin.coroutines.resume

@Singleton
class QwenNpuRuntime @Inject constructor(
    @ApplicationContext private val ctx: Context,
) {
    sealed interface State {
        data object Missing : State
        data object Initializing : State
        data class Downloading(val percent: Int) : State
        data object Downloaded : State
        data object Loading : State
        data class Loaded(val backend: String = "Hexagon NPU · QAIRT / HTP0") : State
        data class Failed(val message: String) : State
    }

    private val _state = MutableStateFlow<State>(State.Missing)
    val state: StateFlow<State> = _state.asStateFlow()

    @Volatile private var wrapper: VlmWrapper? = null
    @Volatile private var sdkReady = false
    private val sdkLock = Mutex()
    private val loadLock = Mutex()
    private val inferenceLock = Mutex()

    fun isReady(): Boolean = wrapper != null

    suspend fun refreshState() {
        if (isReady()) {
            _state.value = State.Loaded()
            return
        }
        runCatching {
            ensureSdk()
            val paths = ModelManagerWrapper.getPaths(MODEL_NAME)
            _state.value = if (paths != null) State.Downloaded else State.Missing
        }.onFailure { _state.value = State.Failed(it.message ?: it.javaClass.simpleName) }
    }

    suspend fun downloadAndLoad(): Boolean = withContext(Dispatchers.IO) {
        runCatching {
            ensureSdk()
            val existing = ModelManagerWrapper.getPaths(MODEL_NAME)
            if (existing == null) {
                _state.value = State.Downloading(0)
                val input = ModelPullInput(
                    model_name = MODEL_NAME,
                    precision = PRECISION,
                    hub = HubSource.AUTO,
                    chipset = CHIPSET,
                    display_name = null,
                )
                ModelManagerWrapper.pullFlow(input).collect { event ->
                    when (event) {
                        is ModelManagerWrapper.PullEvent.Progress -> {
                            val total = event.files.sumOf { if (it.total_bytes > 0) it.total_bytes else 0L }
                            val done = event.files.sumOf { it.downloaded_bytes }
                            val pct = if (total > 0) ((done * 100) / total).toInt().coerceIn(0, 100) else 0
                            _state.update { State.Downloading(pct) }
                        }
                        is ModelManagerWrapper.PullEvent.Completed -> _state.value = State.Downloaded
                        is ModelManagerWrapper.PullEvent.Error -> error("모델 다운로드 실패 (${event.code}): ${event.message}")
                    }
                }
            }
            loadModel()
        }.getOrElse { e ->
            Log.e(TAG, "download/load failed", e)
            _state.value = State.Failed(e.message ?: e.javaClass.simpleName)
            false
        }
    }

    suspend fun ensureLoadedIfPresent(): Boolean = withContext(Dispatchers.IO) {
        if (isReady()) return@withContext true
        runCatching {
            ensureSdk()
            if (ModelManagerWrapper.getPaths(MODEL_NAME) == null) {
                _state.value = State.Missing
                return@runCatching false
            }
            loadModel()
        }.getOrElse { e ->
            Log.w(TAG, "cached-model load failed: ${e.message}")
            _state.value = State.Failed(e.message ?: e.javaClass.simpleName)
            false
        }
    }

    suspend fun unload() = withContext(Dispatchers.IO) {
        loadLock.withLock {
            runCatching { wrapper?.stopStream() }
            runCatching { wrapper?.destroy() }
            wrapper = null
            refreshState()
        }
    }

    suspend fun runRaw(prompt: String, maxLen: Int = 6000): String? = withContext(Dispatchers.IO) {
        if (prompt.isBlank()) return@withContext null
        if (!ensureLoadedIfPresent()) return@withContext null
        inferenceLock.withLock {
            val vlm = wrapper ?: return@withLock null
            runCatching {
                val msg = VlmChatMessage(
                    role = "user",
                    contents = listOf(VlmContent("text", prompt)),
                )
                val templated = vlm.applyChatTemplate(arrayOf(msg), null, false).getOrThrow()
                val out = StringBuilder()
                vlm.generateStreamFlow(
                    templated.formattedText,
                    GenerationConfig(maxTokens = charsToTokens(maxLen)),
                ).collect { ev ->
                    when (ev) {
                        is LlmStreamResult.Token -> out.append(ev.text)
                        is LlmStreamResult.Completed -> Unit
                        else -> Unit
                    }
                }
                out.toString().trim().take(maxLen).ifBlank { null }
            }.getOrElse { e ->
                Log.w(TAG, "Qwen NPU inference failed: ${e.message}")
                null
            }
        }
    }

    suspend fun describeImage(imageFile: File, prompt: String): String? = withContext(Dispatchers.IO) {
        if (!imageFile.exists() || imageFile.length() <= 0L || prompt.isBlank()) return@withContext null
        if (!ensureLoadedIfPresent()) return@withContext null
        inferenceLock.withLock {
            val vlm = wrapper ?: return@withLock null
            runCatching {
                val msg = VlmChatMessage(
                    role = "user",
                    contents = listOf(
                        VlmContent("image", imageFile.absolutePath),
                        VlmContent("text", prompt),
                    ),
                )
                val templated = vlm.applyChatTemplate(arrayOf(msg), null, false).getOrThrow()
                val base = GenerationConfig(maxTokens = 1024)
                val mediaConfig = vlm.injectMediaPathsToConfig(arrayOf(msg), base)
                val out = StringBuilder()
                vlm.generateStreamFlow(templated.formattedText, mediaConfig).collect { ev ->
                    when (ev) {
                        is LlmStreamResult.Token -> out.append(ev.text)
                        is LlmStreamResult.Completed -> Unit
                        else -> Unit
                    }
                }
                out.toString().trim().ifBlank { null }
            }.getOrElse { e ->
                Log.w(TAG, "Qwen NPU vision failed: ${e.message}")
                null
            }
        }
    }

    private suspend fun loadModel(): Boolean = loadLock.withLock {
        if (wrapper != null) return@withLock true
        ensureSdk()
        _state.value = State.Loading
        val paths = ModelManagerWrapper.getPaths(MODEL_NAME) ?: run {
            _state.value = State.Missing
            return@withLock false
        }
        val runtimeId = paths.runtime_id.ifEmpty { "qairt" }
        val config = ModelConfig(
            nCtx = 0,
            nGpuLayers = 0,
            nThreads = 8,
            enable_thinking = false,
        )
        val result = VlmWrapper.builder()
            .vlmCreateInput(
                VlmCreateInput(
                    model_name = paths.model_name,
                    model_path = paths.model_path,
                    mmproj_path = paths.mmproj_path,
                    config = config,
                    runtime_id = runtimeId,
                    compute_unit = "HTP0",
                ),
            )
            .build()
        val built = result.getOrElse { throw it }
        wrapper = built
        _state.value = State.Loaded()
        Log.i(TAG, "Qwen3-VL-4B loaded on QAIRT/HTP0 ($runtimeId)")
        true
    }

    private suspend fun ensureSdk() {
        if (sdkReady) return
        sdkLock.withLock {
            if (sdkReady) return@withLock
            _state.value = State.Initializing
            val ok = suspendCancellableCoroutine<Boolean> { cont ->
                GenieXSdk.getInstance().init(
                    ctx,
                    object : GenieXSdk.InitCallback {
                        override fun onSuccess() {
                            if (cont.isActive) cont.resume(true)
                        }
                        override fun onFailure(reason: String) {
                            Log.e(TAG, "GenieX init failed: $reason")
                            if (cont.isActive) cont.resume(false)
                        }
                    },
                )
            }
            if (!ok) error("Qualcomm GenieX 초기화 실패")
            sdkReady = true
        }
    }

    private fun charsToTokens(maxLen: Int): Int = (maxLen / 3).coerceIn(128, 2048)

    companion object {
        private const val TAG = "Mythara/QwenNPU"
        const val MODEL_NAME = "ai-hub-models/Qwen3-VL-4B-Instruct"
        const val PRECISION = "w4a16"
        const val CHIPSET = "SM8750"
    }
}
''')

# -----------------------------------------------------------------------------
# Settings panel + ViewModel for explicit large-model download and status.
# -----------------------------------------------------------------------------
(qdir / 'QwenSetupViewModel.kt').write_text(r'''package com.mythara.local

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class QwenSetupViewModel @Inject constructor(
    private val runtime: QwenNpuRuntime,
) : ViewModel() {
    val state: StateFlow<QwenNpuRuntime.State> = runtime.state

    init {
        viewModelScope.launch {
            runtime.refreshState()
            runtime.ensureLoadedIfPresent()
        }
    }

    fun downloadAndLoad() {
        viewModelScope.launch { runtime.downloadAndLoad() }
    }

    fun retryLoad() {
        viewModelScope.launch { runtime.ensureLoadedIfPresent() }
    }

    fun unload() {
        viewModelScope.launch { runtime.unload() }
    }
}
''')

Path('app/src/main/kotlin/com/mythara/ui/settings/QwenAccelerationPanel.kt').write_text(r'''package com.mythara.ui.settings

import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.mythara.local.QwenNpuRuntime
import com.mythara.local.QwenSetupViewModel
import com.mythara.ui.theme.MytharaColors

@Composable
fun QwenAccelerationPanel(vm: QwenSetupViewModel = hiltViewModel()) {
    val state by vm.state.collectAsState()
    Column(
        Modifier
            .fillMaxWidth()
            .border(1.dp, MytharaColors.SurfaceHigh, RoundedCornerShape(14.dp))
            .padding(14.dp),
    ) {
        Text("Snapdragon AI 가속", style = MaterialTheme.typography.titleMedium, color = MytharaColors.Fg)
        Spacer(Modifier.height(6.dp))
        Text("Qwen3-VL-4B-Instruct · Qualcomm QAIRT w4a16", color = MytharaColors.Fg)
        Text("Galaxy Z Fold7 / SM8750 · Hexagon NPU(HTP0) 우선", style = MaterialTheme.typography.bodySmall, color = MytharaColors.FgDim)
        Spacer(Modifier.height(8.dp))
        Text(
            when (val s = state) {
                QwenNpuRuntime.State.Missing -> "상태: 모델 미설치"
                QwenNpuRuntime.State.Initializing -> "상태: Qualcomm 런타임 초기화 중…"
                is QwenNpuRuntime.State.Downloading -> "상태: 모델 다운로드 ${s.percent}%"
                QwenNpuRuntime.State.Downloaded -> "상태: 다운로드 완료 · 로드 대기"
                QwenNpuRuntime.State.Loading -> "상태: Hexagon NPU에 모델 로드 중…"
                is QwenNpuRuntime.State.Loaded -> "상태: ${s.backend} 사용 중"
                is QwenNpuRuntime.State.Failed -> "상태: 실패 · ${s.message}"
            },
            style = MaterialTheme.typography.bodyMedium,
            color = MytharaColors.Fg,
        )
        Spacer(Modifier.height(10.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            when (state) {
                QwenNpuRuntime.State.Missing,
                is QwenNpuRuntime.State.Failed -> Button(
                    onClick = vm::downloadAndLoad,
                    colors = ButtonDefaults.buttonColors(containerColor = MytharaColors.Charple, contentColor = MytharaColors.Fg),
                ) { Text("Qwen NPU 모델 다운로드 및 활성화") }
                QwenNpuRuntime.State.Downloaded -> Button(onClick = vm::retryLoad) { Text("NPU 모델 로드") }
                is QwenNpuRuntime.State.Loaded -> Button(onClick = vm::unload) { Text("NPU 모델 언로드") }
                else -> Unit
            }
        }
        Spacer(Modifier.height(8.dp))
        Text(
            "기본 대화·FCC·화면/사진 이해는 Qwen NPU를 우선 사용하고, 초기화 실패나 모델 미설치 시 기존 Gemma 4 E2B로 자동 폴백합니다. 모델은 APK에 포함되지 않으며 Qualcomm AI Hub에서 기기용 자산을 내려받습니다.",
            style = MaterialTheme.typography.bodySmall,
            color = MytharaColors.FgDim,
        )
        Spacer(Modifier.height(6.dp))
        Text(
            "자유 대화 모드는 현재 공식 Instruct 모델의 프롬프트 완화만 지원합니다. 별도 검열해제 체크포인트는 NPU용 QAIRT 변환본을 검증하기 전까지 기본 에이전트에 사용하지 않습니다.",
            style = MaterialTheme.typography.bodySmall,
            color = MytharaColors.FgDim,
        )
    }
}
''')

# Insert panel near top of Settings.
p = Path('app/src/main/kotlin/com/mythara/ui/settings/SettingsScreen.kt')
s = p.read_text()
anchor = '        AppearancePanel()\n\n        Spacer(Modifier.height(16.dp))\n        AutopilotPanel()'
if anchor not in s:
    raise SystemExit('SettingsScreen insertion anchor not found')
s = s.replace(anchor, '        AppearancePanel()\n\n        Spacer(Modifier.height(16.dp))\n        QwenAccelerationPanel()\n\n        Spacer(Modifier.height(16.dp))\n        AutopilotPanel()', 1)
p.write_text(s)

# -----------------------------------------------------------------------------
# FCC adapter: Qwen NPU first, Gemma fallback. Remove AgentLoop's synchronous
# readiness gate so cached Qwen can be auto-loaded at the start of a turn.
# -----------------------------------------------------------------------------
p = Path('app/src/main/kotlin/com/mythara/local/LocalGemmaChat.kt')
s = p.read_text()
s = s.replace(
    'class LocalGemmaChat @Inject constructor(\n    private val gemma: GemmaExtractor,\n) {\n    fun isReady(): Boolean = gemma.isReady()',
    'class LocalGemmaChat @Inject constructor(\n    private val gemma: GemmaExtractor,\n    private val qwen: QwenNpuRuntime,\n) {\n    fun isReady(): Boolean = qwen.isReady() || gemma.isReady()',
    1,
)
old = '''        if (!gemma.isReady()) {\n            emit(\n                StreamingChat.StreamEvent.Failure(\n                    ErrorMapper.Mapped(\n                        0,\n                        "LOCAL_MODEL_MISSING",\n                        "로컬 Gemma 4 E2B 모델이 설치되지 않았습니다. 설정 → 정보 → MYTHARA 3회 탭 → Secret → 로컬 AI 모델에서 설치해 주세요.",\n                    ),\n                ),\n            )\n            return@flow\n        }'''
new = '''        qwen.ensureLoadedIfPresent()\n        if (!qwen.isReady() && !gemma.isReady()) {\n            emit(\n                StreamingChat.StreamEvent.Failure(\n                    ErrorMapper.Mapped(\n                        0,\n                        "LOCAL_MODEL_MISSING",\n                        "로컬 AI 모델이 준비되지 않았습니다. 설정 → Snapdragon AI 가속에서 Qwen3-VL-4B NPU 모델을 다운로드하거나 Secret 설정에서 Gemma 폴백 모델을 설치해 주세요.",\n                    ),\n                ),\n            )\n            return@flow\n        }'''
if old not in s:
    raise SystemExit('LocalGemmaChat missing-model anchor not found')
s = s.replace(old, new, 1)
old = '''    private suspend fun runRaw(prompt: String, maxLen: Int): String =\n        runCatching { gemma.runRaw(prompt, maxLen = maxLen) }\n            .getOrNull().orEmpty().let(Thinks::strip).trim()'''
new = '''    private suspend fun runRaw(prompt: String, maxLen: Int): String {\n        val qwenOut = runCatching { qwen.runRaw(prompt, maxLen = maxLen) }.getOrNull()\n        val raw = if (!qwenOut.isNullOrBlank()) qwenOut else runCatching { gemma.runRaw(prompt, maxLen = maxLen) }.getOrNull()\n        return raw.orEmpty().let(Thinks::strip).trim()\n    }'''
if old not in s:
    raise SystemExit('LocalGemmaChat runRaw anchor not found')
s = s.replace(old, new, 1)
s = s.replace(
    '당신은 Galaxy Z Fold7 안에서 완전히 로컬로 실행되는 Mythara AI입니다.',
    '당신은 Galaxy Z Fold7 안에서 완전히 로컬로 실행되는 Mythara AI입니다. 기본 추론은 Qwen3-VL-4B-Instruct를 Snapdragon Hexagon NPU에서 실행합니다.',
)
p.write_text(s)

p = Path('app/src/main/kotlin/com/mythara/agent/AgentLoop.kt')
s = p.read_text()
start = '''        if (!localGemmaChat.isReady()) {\n            emit(\n                Turn.Error(\n                    "Local Gemma 4 E2B is not installed yet. Download it in onboarding or Secret settings, then retry.",\n                    retryable = false,\n                ),\n            )\n            return@flow\n        }'''
if start in s:
    s = s.replace(start, '        // v6: LocalQwen can lazy-load a cached QAIRT model inside the stream; do not pre-gate here.', 1)
p.write_text(s)

# -----------------------------------------------------------------------------
# Vision path: Qwen VLM/NPU first, Gemma fallback.
# Keep the existing class name so all callers remain source-compatible.
# -----------------------------------------------------------------------------
p = Path('app/src/main/kotlin/com/mythara/minimax/GemmaVisionService.kt')
s = p.read_text()
s = s.replace(
    'class GemmaVisionService @Inject constructor(\n    private val gemma: GemmaExtractor,\n) {',
    'class GemmaVisionService @Inject constructor(\n    private val gemma: GemmaExtractor,\n    private val qwen: com.mythara.local.QwenNpuRuntime,\n) {',
    1,
)
s = s.replace('fun isAvailable(): Boolean = gemma.isReady()', 'fun isAvailable(): Boolean = qwen.isReady() || gemma.isReady()', 1)
needle = '''        if (!gemma.isReady()) {\n            return@withContext Outcome(false, "Gemma model not installed", code = "not_ready")\n        }'''
replacement = '''        // v6: use the Snapdragon-NPU Qwen VLM first. It consumes the image\n        // path directly through GenieX/QAIRT and avoids a cloud round-trip.\n        val qwenReply = runCatching { qwen.describeImage(imageFile, prompt) }.getOrNull()\n        if (!qwenReply.isNullOrBlank()) {\n            return@withContext Outcome(ok = true, text = qwenReply.trim())\n        }\n        if (!gemma.isReady()) {\n            return@withContext Outcome(false, "Qwen NPU / Gemma local vision model not ready", code = "not_ready")\n        }'''
if needle not in s:
    raise SystemExit('GemmaVisionService readiness anchor not found')
s = s.replace(needle, replacement, 1)
p.write_text(s)

print('Mythara Local Fold7 KR FCC v6 Qwen3-VL NPU patch applied')
