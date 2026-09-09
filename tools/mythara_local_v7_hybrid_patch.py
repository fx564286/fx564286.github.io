from pathlib import Path

# Mythara Local Fold7 KR FCC v7 Hybrid
# - stable package/signing retained from v5
# - official Qwen3-VL-4B-Instruct QAIRT/w4a16 for phone-agent/FCC reliability
# - optional uncensored/abliterated Qwen3-VL-4B Q4_K_M GGUF for freer chat/lyrics
# - ACE-Step 1.5 remote/local-LAN music server integration for actual vocal songs
# - one Qwen model resident at a time to control RAM/heat on Galaxy Z Fold7

# -----------------------------------------------------------------------------
# Version + allow LAN HTTP for a user-owned ACE-Step server.
# -----------------------------------------------------------------------------
p = Path('app/build.gradle.kts')
s = p.read_text()
s = s.replace('versionNameSuffix = "-local-fold7-kr-v6"', 'versionNameSuffix = "-local-fold7-kr-v7"')
s = s.replace('versionCode = 6', 'versionCode = 7', 1)
p.write_text(s)

p = Path('app/src/main/AndroidManifest.xml')
s = p.read_text()
if 'android:usesCleartextTraffic=' not in s:
    s = s.replace('<application', '<application\n        android:usesCleartextTraffic="true"', 1)
p.write_text(s)

# -----------------------------------------------------------------------------
# Unified Qualcomm runtime: official QAIRT agent + optional uncensored GGUF.
# Uses only API methods exercised by Qualcomm's public GenieX Android sample.
# -----------------------------------------------------------------------------
qdir = Path('app/src/main/kotlin/com/mythara/local')
qdir.mkdir(parents=True, exist_ok=True)
(qdir / 'QwenNpuRuntime.kt').write_text(r'''package com.mythara.local

import android.content.Context
import android.util.Log
import com.geniex.sdk.GenieXSdk
import com.geniex.sdk.ModelManagerWrapper
import com.geniex.sdk.VlmWrapper
import com.geniex.sdk.bean.ComputeUnitValue
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
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
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
        data class Loaded(val backend: String) : State
        data class Failed(val message: String) : State
    }

    enum class Mode { AGENT, CREATIVE }
    private enum class Active { NONE, AGENT, CREATIVE }

    private val prefs = ctx.getSharedPreferences("mythara_hybrid_ai", Context.MODE_PRIVATE)

    private val _agentState = MutableStateFlow<State>(State.Missing)
    val agentState: StateFlow<State> = _agentState.asStateFlow()
    // v6 compatibility for existing settings VM.
    val state: StateFlow<State> get() = agentState

    private val _creativeState = MutableStateFlow<State>(State.Missing)
    val creativeState: StateFlow<State> = _creativeState.asStateFlow()

    private val _mode = MutableStateFlow(
        if (prefs.getBoolean(KEY_CREATIVE_MODE, false)) Mode.CREATIVE else Mode.AGENT,
    )
    val mode: StateFlow<Mode> = _mode.asStateFlow()

    @Volatile private var sdkReady = false
    @Volatile private var active = Active.NONE
    @Volatile private var wrapper: VlmWrapper? = null
    @Volatile private var activeBackend = ""

    private val sdkLock = Mutex()
    private val modelLock = Mutex()
    private val inferenceLock = Mutex()

    fun isReady(): Boolean = wrapper != null || agentState.value is State.Downloaded || creativeState.value is State.Downloaded
    fun isCreativeMode(): Boolean = _mode.value == Mode.CREATIVE

    fun setCreativeMode(enabled: Boolean) {
        prefs.edit().putBoolean(KEY_CREATIVE_MODE, enabled).apply()
        _mode.value = if (enabled) Mode.CREATIVE else Mode.AGENT
    }

    suspend fun refreshState() = withContext(Dispatchers.IO) {
        runCatching {
            ensureSdk()
            _agentState.value = when {
                active == Active.AGENT && wrapper != null -> State.Loaded(activeBackend)
                ModelManagerWrapper.getPaths(AGENT_MODEL) != null -> State.Downloaded
                else -> State.Missing
            }
            _creativeState.value = when {
                active == Active.CREATIVE && wrapper != null -> State.Loaded(activeBackend)
                ModelManagerWrapper.getPaths(CREATIVE_MODEL) != null -> State.Downloaded
                else -> State.Missing
            }
        }.onFailure { e ->
            if (_agentState.value !is State.Loaded) _agentState.value = State.Failed(e.message ?: e.javaClass.simpleName)
        }
    }

    suspend fun downloadAndLoad(): Boolean = downloadAgentAndLoad()

    suspend fun downloadAgentAndLoad(): Boolean = withContext(Dispatchers.IO) {
        downloadModel(
            modelName = AGENT_MODEL,
            precision = AGENT_PRECISION,
            hub = HubSource.AUTO,
            chipset = CHIPSET,
            stateFlow = _agentState,
        ) && ensureAgentLoadedIfPresent()
    }

    suspend fun downloadCreativeAndLoad(): Boolean = withContext(Dispatchers.IO) {
        downloadModel(
            modelName = CREATIVE_MODEL,
            precision = CREATIVE_PRECISION,
            hub = HubSource.HUGGINGFACE,
            chipset = null,
            stateFlow = _creativeState,
        ) && ensureCreativeLoadedIfPresent()
    }

    suspend fun ensureLoadedIfPresent(): Boolean = ensureAgentLoadedIfPresent()

    suspend fun ensureAgentLoadedIfPresent(): Boolean = withContext(Dispatchers.IO) {
        modelLock.withLock {
            if (active == Active.AGENT && wrapper != null) return@withLock true
            runCatching {
                ensureSdk()
                val paths = ModelManagerWrapper.getPaths(AGENT_MODEL) ?: run {
                    _agentState.value = State.Missing
                    return@runCatching false
                }
                switchOutLocked()
                _agentState.value = State.Loading
                val conf = ModelConfig(nCtx = 0, nGpuLayers = 0, nThreads = 8, enable_thinking = false)
                val built = buildVlm(
                    VlmCreateInput(
                        model_name = paths.model_name,
                        model_path = paths.model_path,
                        mmproj_path = paths.mmproj_path,
                        config = conf,
                        runtime_id = paths.runtime_id.ifEmpty { "qairt" },
                        compute_unit = "HTP0",
                    ),
                )
                wrapper = built
                active = Active.AGENT
                activeBackend = "Hexagon NPU · QAIRT / HTP0"
                _agentState.value = State.Loaded(activeBackend)
                true
            }.getOrElse { e ->
                Log.w(TAG, "agent load failed: ${e.message}")
                _agentState.value = State.Failed(e.message ?: e.javaClass.simpleName)
                false
            }
        }
    }

    suspend fun ensureCreativeLoadedIfPresent(): Boolean = withContext(Dispatchers.IO) {
        modelLock.withLock {
            if (active == Active.CREATIVE && wrapper != null) return@withLock true
            runCatching {
                ensureSdk()
                val paths = ModelManagerWrapper.getPaths(CREATIVE_MODEL) ?: run {
                    _creativeState.value = State.Missing
                    return@runCatching false
                }
                switchOutLocked()
                _creativeState.value = State.Loading

                // GGUF is not the precompiled QAIRT checkpoint. GenieX can still
                // expose Snapdragon compute units through its llama.cpp bridge.
                // Try the NPU compute target first, then Adreno GPU if unsupported.
                val baseConfig = ModelConfig(
                    nCtx = 4096,
                    nThreads = 4,
                    nBatch = 1,
                    nUBatch = 1,
                    nGpuLayers = 999,
                    enable_thinking = false,
                )
                val runtimeId = paths.runtime_id.ifEmpty { "llama_cpp" }
                val first = tryBuildVlm(
                    VlmCreateInput(
                        model_name = paths.model_name,
                        model_path = paths.model_path,
                        mmproj_path = paths.mmproj_path,
                        config = baseConfig,
                        runtime_id = runtimeId,
                        compute_unit = ComputeUnitValue.NPU.value,
                    ),
                )
                val built: VlmWrapper
                val backend: String
                if (first.first != null) {
                    built = first.first!!
                    backend = "GenieX GGUF · Snapdragon NPU target"
                } else {
                    val second = tryBuildVlm(
                        VlmCreateInput(
                            model_name = paths.model_name,
                            model_path = paths.model_path,
                            mmproj_path = paths.mmproj_path,
                            config = baseConfig,
                            runtime_id = runtimeId,
                            compute_unit = ComputeUnitValue.GPU.value,
                        ),
                    )
                    built = second.first ?: error(second.second ?: first.second ?: "creative model init failed")
                    backend = "GenieX GGUF · Adreno GPU"
                }
                wrapper = built
                active = Active.CREATIVE
                activeBackend = backend
                _creativeState.value = State.Loaded(backend)
                true
            }.getOrElse { e ->
                Log.w(TAG, "creative load failed: ${e.message}")
                _creativeState.value = State.Failed(e.message ?: e.javaClass.simpleName)
                false
            }
        }
    }

    suspend fun unload() = withContext(Dispatchers.IO) {
        modelLock.withLock {
            switchOutLocked()
            refreshState()
        }
    }

    /** Agent/FCC path: always the official QAIRT model, Gemma fallback is handled by LocalGemmaChat. */
    suspend fun runAgentRaw(prompt: String, maxLen: Int = 6000): String? {
        if (!ensureAgentLoadedIfPresent()) return null
        return runActive(prompt, null, maxLen)
    }

    /** Creative path: uncensored GGUF when installed; otherwise falls back to official QAIRT. */
    suspend fun runCreativeRaw(prompt: String, maxLen: Int = 9000): String? {
        if (ensureCreativeLoadedIfPresent()) return runActive(prompt, null, maxLen)
        return runAgentRaw(prompt, maxLen)
    }

    /** v6 compatibility: selected mode for ordinary chat. */
    suspend fun runRaw(prompt: String, maxLen: Int = 6000): String? =
        if (isCreativeMode()) runCreativeRaw(prompt, maxLen) else runAgentRaw(prompt, maxLen)

    suspend fun describeImage(imageFile: File, prompt: String): String? {
        if (!imageFile.exists() || imageFile.length() <= 0L || prompt.isBlank()) return null
        val loaded = if (isCreativeMode()) ensureCreativeLoadedIfPresent() else ensureAgentLoadedIfPresent()
        if (!loaded) return null
        return runActive(prompt, imageFile, 4000)
    }

    private suspend fun runActive(prompt: String, imageFile: File?, maxLen: Int): String? = withContext(Dispatchers.IO) {
        if (prompt.isBlank()) return@withContext null
        inferenceLock.withLock {
            val vlm = wrapper ?: return@withLock null
            runCatching {
                val contents = buildList {
                    if (imageFile != null) add(VlmContent("image", imageFile.absolutePath))
                    add(VlmContent("text", prompt))
                }
                val msg = VlmChatMessage(role = "user", contents = contents)
                val formatted = applyTemplate(vlm, arrayOf(msg))
                val base = GenerationConfig(maxTokens = charsToTokens(maxLen))
                val config = if (imageFile != null) vlm.injectMediaPathsToConfig(arrayOf(msg), base) else base
                val out = StringBuilder()
                vlm.generateStreamFlow(formatted, config).collect { ev ->
                    when (ev) {
                        is LlmStreamResult.Token -> out.append(ev.text)
                        is LlmStreamResult.Completed -> Unit
                        else -> Unit
                    }
                }
                out.toString().trim().take(maxLen).ifBlank { null }
            }.getOrElse { e ->
                Log.w(TAG, "inference failed ($active/$activeBackend): ${e.message}")
                null
            }
        }
    }

    private suspend fun downloadModel(
        modelName: String,
        precision: String,
        hub: HubSource,
        chipset: String?,
        stateFlow: MutableStateFlow<State>,
    ): Boolean = withContext(Dispatchers.IO) {
        runCatching {
            ensureSdk()
            if (ModelManagerWrapper.getPaths(modelName) != null) {
                stateFlow.value = State.Downloaded
                return@runCatching true
            }
            stateFlow.value = State.Downloading(0)
            val input = ModelPullInput(
                model_name = modelName,
                precision = precision,
                hub = hub,
                chipset = chipset,
                display_name = null,
            )
            var completed = false
            ModelManagerWrapper.pullFlow(input).collect { event ->
                when (event) {
                    is ModelManagerWrapper.PullEvent.Progress -> {
                        val total = event.files.sumOf { if (it.total_bytes > 0) it.total_bytes else 0L }
                        val done = event.files.sumOf { it.downloaded_bytes }
                        val pct = if (total > 0) ((done * 100) / total).toInt().coerceIn(0, 100) else 0
                        stateFlow.update { State.Downloading(pct) }
                    }
                    is ModelManagerWrapper.PullEvent.Completed -> {
                        completed = true
                        stateFlow.value = State.Downloaded
                    }
                    is ModelManagerWrapper.PullEvent.Error -> error("모델 다운로드 실패 (${event.code}): ${event.message}")
                }
            }
            completed || ModelManagerWrapper.getPaths(modelName) != null
        }.getOrElse { e ->
            Log.e(TAG, "download failed for $modelName", e)
            stateFlow.value = State.Failed(e.message ?: e.javaClass.simpleName)
            false
        }
    }

    private fun applyTemplate(vlm: VlmWrapper, messages: Array<VlmChatMessage>): String {
        var formatted: String? = null
        var errorMessage: String? = null
        vlm.applyChatTemplate(messages, null, false)
            .onSuccess { formatted = it.formattedText }
            .onFailure { errorMessage = it.message.toString() }
        return formatted ?: error(errorMessage ?: "chat template failed")
    }

    private fun buildVlm(input: VlmCreateInput): VlmWrapper {
        val pair = tryBuildVlm(input)
        return pair.first ?: error(pair.second ?: "VLM init failed")
    }

    private fun tryBuildVlm(input: VlmCreateInput): Pair<VlmWrapper?, String?> {
        var built: VlmWrapper? = null
        var errorMessage: String? = null
        VlmWrapper.builder().vlmCreateInput(input).build()
            .onSuccess { built = it }
            .onFailure { errorMessage = it.message.toString() }
        return built to errorMessage
    }

    private fun switchOutLocked() {
        runCatching { wrapper?.stopStream() }
        runCatching { wrapper?.destroy() }
        wrapper = null
        active = Active.NONE
        activeBackend = ""
    }

    private suspend fun ensureSdk() {
        if (sdkReady) return
        sdkLock.withLock {
            if (sdkReady) return@withLock
            _agentState.value = State.Initializing
            val ok = suspendCancellableCoroutine<Boolean> { cont ->
                GenieXSdk.getInstance().init(
                    ctx,
                    object : GenieXSdk.InitCallback {
                        override fun onSuccess() { if (cont.isActive) cont.resume(true) }
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
        private const val TAG = "Mythara/HybridQwen"
        const val AGENT_MODEL = "ai-hub-models/Qwen3-VL-4B-Instruct"
        const val AGENT_PRECISION = "w4a16"
        const val CHIPSET = "SM8750"
        const val CREATIVE_MODEL = "mradermacher/Qwen3-VL-4B-Instruct-Uncensored-abliterated-GGUF"
        const val CREATIVE_PRECISION = "Q4_K_M"
        private const val KEY_CREATIVE_MODE = "creative_mode"
    }
}
''')

# -----------------------------------------------------------------------------
# Setup VM updated for both Qwen models and mode switch.
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
    val state: StateFlow<QwenNpuRuntime.State> = runtime.agentState
    val creativeState: StateFlow<QwenNpuRuntime.State> = runtime.creativeState
    val mode: StateFlow<QwenNpuRuntime.Mode> = runtime.mode

    init { viewModelScope.launch { runtime.refreshState() } }

    fun downloadAndLoad() { viewModelScope.launch { runtime.downloadAgentAndLoad() } }
    fun downloadCreativeAndLoad() { viewModelScope.launch { runtime.downloadCreativeAndLoad() } }
    fun retryLoad() { viewModelScope.launch { runtime.ensureAgentLoadedIfPresent() } }
    fun retryCreativeLoad() { viewModelScope.launch { runtime.ensureCreativeLoadedIfPresent() } }
    fun setCreativeMode(enabled: Boolean) { runtime.setCreativeMode(enabled) }
    fun unload() { viewModelScope.launch { runtime.unload() } }
}
''')

# -----------------------------------------------------------------------------
# ACE-Step settings/client. Native async API avoids giant base64 JSON responses.
# Generated audio is written to MediaStore Music/Mythara and returned as content:// URI.
# -----------------------------------------------------------------------------
(qdir / 'AceStepSettings.kt').write_text(r'''package com.mythara.local

import android.content.Context
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class AceStepSettings @Inject constructor(@ApplicationContext ctx: Context) {
    data class Config(
        val baseUrl: String = "",
        val apiKey: String = "",
        val model: String = "acestep-v15-turbo",
        val thinking: Boolean = true,
    )

    private val prefs = ctx.getSharedPreferences("mythara_acestep", Context.MODE_PRIVATE)
    private val _config = MutableStateFlow(load())
    val config: StateFlow<Config> = _config.asStateFlow()

    fun save(baseUrl: String, apiKey: String, model: String, thinking: Boolean) {
        val clean = baseUrl.trim().removeSuffix("/")
        prefs.edit()
            .putString("base_url", clean)
            .putString("api_key", apiKey.trim())
            .putString("model", model.trim().ifBlank { "acestep-v15-turbo" })
            .putBoolean("thinking", thinking)
            .apply()
        _config.value = Config(clean, apiKey.trim(), model.trim().ifBlank { "acestep-v15-turbo" }, thinking)
    }

    private fun load() = Config(
        baseUrl = prefs.getString("base_url", "").orEmpty(),
        apiKey = prefs.getString("api_key", "").orEmpty(),
        model = prefs.getString("model", "acestep-v15-turbo").orEmpty().ifBlank { "acestep-v15-turbo" },
        thinking = prefs.getBoolean("thinking", true),
    )
}
''')

(qdir / 'AceStepClient.kt').write_text(r'''package com.mythara.local

import android.content.ContentValues
import android.content.Context
import android.os.Environment
import android.provider.MediaStore
import android.util.Log
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.concurrent.TimeUnit
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class AceStepClient @Inject constructor(
    @ApplicationContext private val ctx: Context,
    private val settings: AceStepSettings,
) {
    data class MusicRequest(
        val prompt: String,
        val lyrics: String,
        val durationSec: Int,
        val bpm: Int?,
        val keyScale: String?,
        val timeSignature: String?,
        val vocalLanguage: String,
        val format: String,
    )
    data class Generated(val uri: String, val fileName: String, val serverModel: String)

    private val json = Json { ignoreUnknownKeys = true; isLenient = true }
    private val http = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(120, TimeUnit.SECONDS)
        .writeTimeout(60, TimeUnit.SECONDS)
        .build()

    suspend fun health(): Pair<Boolean, String> = withContext(Dispatchers.IO) {
        val c = settings.config.value
        if (c.baseUrl.isBlank()) return@withContext false to "서버 주소가 비어 있습니다."
        runCatching {
            request(c.baseUrl + "/health", "GET", null, c.apiKey).use { resp ->
                if (!resp.isSuccessful) false to "HTTP ${resp.code}" else true to "ACE-Step 서버 연결됨"
            }
        }.getOrElse { false to (it.message ?: it.javaClass.simpleName) }
    }

    suspend fun generate(req: MusicRequest): Generated = withContext(Dispatchers.IO) {
        val c = settings.config.value
        require(c.baseUrl.isNotBlank()) { "ACE-Step 서버 주소가 설정되지 않았습니다." }

        val bodyJson = buildJsonObject {
            put("prompt", JsonPrimitive(req.prompt))
            put("lyrics", JsonPrimitive(req.lyrics))
            put("thinking", JsonPrimitive(c.thinking))
            put("use_format", JsonPrimitive(false))
            put("vocal_language", JsonPrimitive(req.vocalLanguage))
            put("audio_format", JsonPrimitive(req.format))
            put("audio_duration", JsonPrimitive(req.durationSec.coerceIn(10, 600)))
            put("model", JsonPrimitive(c.model))
            put("batch_size", JsonPrimitive(1))
            put("inference_steps", JsonPrimitive(8))
            put("task_type", JsonPrimitive("text2music"))
            req.bpm?.let { put("bpm", JsonPrimitive(it.coerceIn(30, 300))) }
            req.keyScale?.takeIf { it.isNotBlank() }?.let { put("key_scale", JsonPrimitive(it)) }
            req.timeSignature?.takeIf { it.isNotBlank() }?.let { put("time_signature", JsonPrimitive(it)) }
        }
        val release = request(
            c.baseUrl + "/release_task",
            "POST",
            bodyJson.toString(),
            c.apiKey,
        ).use { resp ->
            val text = resp.body?.string().orEmpty()
            if (!resp.isSuccessful) error("ACE-Step 작업 생성 실패 HTTP ${resp.code}: ${text.take(240)}")
            text
        }
        val taskId = json.parseToJsonElement(release).jsonObject["data"]
            ?.jsonObject?.get("task_id")?.jsonPrimitive?.contentOrNull
            ?: error("ACE-Step 응답에 task_id가 없습니다.")

        var audioRelative: String? = null
        var serverModel = c.model
        repeat(MAX_POLLS) {
            delay(POLL_MS)
            val queryBody = buildJsonObject {
                put("task_id_list", buildJsonArray { add(JsonPrimitive(taskId)) })
            }
            val query = request(c.baseUrl + "/query_result", "POST", queryBody.toString(), c.apiKey).use { resp ->
                val text = resp.body?.string().orEmpty()
                if (!resp.isSuccessful) error("ACE-Step 상태 조회 실패 HTTP ${resp.code}: ${text.take(240)}")
                text
            }
            val root = json.parseToJsonElement(query).jsonObject
            val row = (root["data"] as? JsonArray)?.firstOrNull()?.jsonObject
            val status = row?.get("status")?.jsonPrimitive?.intOrNull ?: 0
            if (status == 2) error("ACE-Step 음악 생성 실패")
            if (status == 1) {
                val resultText = row["result"]?.jsonPrimitive?.contentOrNull.orEmpty()
                val results = runCatching { json.parseToJsonElement(resultText).jsonArray }.getOrNull()
                val item = results?.firstOrNull()?.jsonObject
                audioRelative = item?.get("file")?.jsonPrimitive?.contentOrNull
                serverModel = item?.get("dit_model")?.jsonPrimitive?.contentOrNull ?: c.model
                if (!audioRelative.isNullOrBlank()) return@repeat
            }
            if (!audioRelative.isNullOrBlank()) return@repeat
        }
        val rel = audioRelative ?: error("ACE-Step 생성 시간이 제한을 초과했습니다.")
        val url = if (rel.startsWith("http://") || rel.startsWith("https://")) rel else c.baseUrl + rel
        val fileName = "Mythara_${System.currentTimeMillis()}.${req.format.lowercase()}"
        val uri = saveAudio(url, fileName, req.format, c.apiKey)
        Generated(uri.toString(), fileName, serverModel)
    }

    private fun request(url: String, method: String, body: String?, key: String): okhttp3.Response {
        val b = Request.Builder().url(url)
        if (key.isNotBlank()) b.header("Authorization", "Bearer $key")
        if (method == "POST") {
            b.post((body ?: "{}").toRequestBody("application/json; charset=utf-8".toMediaType()))
        } else b.get()
        return http.newCall(b.build()).execute()
    }

    private fun saveAudio(url: String, fileName: String, format: String, key: String): android.net.Uri {
        val mime = when (format.lowercase()) {
            "wav" -> "audio/wav"
            "flac" -> "audio/flac"
            else -> "audio/mpeg"
        }
        val values = ContentValues().apply {
            put(MediaStore.Audio.Media.DISPLAY_NAME, fileName)
            put(MediaStore.Audio.Media.MIME_TYPE, mime)
            put(MediaStore.Audio.Media.RELATIVE_PATH, Environment.DIRECTORY_MUSIC + "/Mythara")
            put(MediaStore.Audio.Media.IS_PENDING, 1)
        }
        val collection = MediaStore.Audio.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
        val uri = ctx.contentResolver.insert(collection, values) ?: error("음원 저장 위치를 만들 수 없습니다.")
        try {
            request(url, "GET", null, key).use { resp ->
                if (!resp.isSuccessful) error("음원 다운로드 실패 HTTP ${resp.code}")
                val src = resp.body?.byteStream() ?: error("음원 응답이 비어 있습니다.")
                ctx.contentResolver.openOutputStream(uri)?.use { out -> src.use { it.copyTo(out, 256 * 1024) } }
                    ?: error("음원 파일을 열 수 없습니다.")
            }
            values.clear()
            values.put(MediaStore.Audio.Media.IS_PENDING, 0)
            ctx.contentResolver.update(uri, values, null, null)
            return uri
        } catch (e: Throwable) {
            runCatching { ctx.contentResolver.delete(uri, null, null) }
            throw e
        }
    }

    companion object {
        private const val TAG = "Mythara/ACE-Step"
        private const val POLL_MS = 2_000L
        private const val MAX_POLLS = 300 // up to ~10 minutes
    }
}
''')

(qdir / 'MusicSetupViewModel.kt').write_text(r'''package com.mythara.local

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class MusicSetupViewModel @Inject constructor(
    private val settings: AceStepSettings,
    private val client: AceStepClient,
) : ViewModel() {
    val config = settings.config
    private val _testResult = MutableStateFlow("")
    val testResult: StateFlow<String> = _testResult.asStateFlow()

    fun save(url: String, key: String, model: String, thinking: Boolean) = settings.save(url, key, model, thinking)
    fun test() {
        viewModelScope.launch {
            _testResult.value = "연결 확인 중…"
            val (ok, msg) = client.health()
            _testResult.value = if (ok) "✓ $msg" else "✕ $msg"
        }
    }
}
''')

# -----------------------------------------------------------------------------
# Actual music tools.
# -----------------------------------------------------------------------------
tools_dir = Path('app/src/main/kotlin/com/mythara/agent/tools')
(tools_dir / 'GenerateMusicTool.kt').write_text(r'''package com.mythara.agent.tools

import com.mythara.agent.Tool
import com.mythara.agent.ToolResult
import com.mythara.local.AceStepClient
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonPrimitive
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class GenerateMusicTool @Inject constructor(
    private val client: AceStepClient,
) : Tool {
    override val name = "generate_music"
    override val description = "Generate a complete vocal/instrumental song with ACE-Step 1.5 and save it to Music/Mythara."
    override val parameters: JsonElement = buildJsonObject {
        put("type", JsonPrimitive("object"))
        put("properties", buildJsonObject {
            put("prompt", buildJsonObject { put("type", JsonPrimitive("string")); put("description", JsonPrimitive("Genre, mood, instruments, vocal style and production description")) })
            put("lyrics", buildJsonObject { put("type", JsonPrimitive("string")); put("description", JsonPrimitive("Complete lyrics with [Verse]/[Chorus]/[Bridge] structure")) })
            put("duration_sec", buildJsonObject { put("type", JsonPrimitive("integer")); put("minimum", JsonPrimitive(10)); put("maximum", JsonPrimitive(600)) })
            put("bpm", buildJsonObject { put("type", JsonPrimitive("integer")); put("minimum", JsonPrimitive(30)); put("maximum", JsonPrimitive(300)) })
            put("key_scale", buildJsonObject { put("type", JsonPrimitive("string")) })
            put("time_signature", buildJsonObject { put("type", JsonPrimitive("string")) })
            put("vocal_language", buildJsonObject { put("type", JsonPrimitive("string")); put("description", JsonPrimitive("Language code, e.g. ko/en/ja")) })
            put("format", buildJsonObject { put("type", JsonPrimitive("string")); put("enum", kotlinx.serialization.json.buildJsonArray { add(JsonPrimitive("mp3")); add(JsonPrimitive("wav")); add(JsonPrimitive("flac")) }) })
        })
        put("required", kotlinx.serialization.json.buildJsonArray { add(JsonPrimitive("prompt")); add(JsonPrimitive("lyrics")) })
    }

    override suspend fun execute(args: JsonObject): ToolResult {
        val prompt = args["prompt"]?.jsonPrimitive?.contentOrNull?.trim().orEmpty()
        val lyrics = args["lyrics"]?.jsonPrimitive?.contentOrNull?.trim().orEmpty()
        if (prompt.isBlank()) return ToolResult.fail("prompt required")
        if (lyrics.isBlank()) return ToolResult.fail("lyrics required")
        val duration = args["duration_sec"]?.jsonPrimitive?.intOrNull ?: 180
        val bpm = args["bpm"]?.jsonPrimitive?.intOrNull
        val key = args["key_scale"]?.jsonPrimitive?.contentOrNull
        val timeSig = args["time_signature"]?.jsonPrimitive?.contentOrNull
        val lang = args["vocal_language"]?.jsonPrimitive?.contentOrNull?.ifBlank { "ko" } ?: "ko"
        val format = args["format"]?.jsonPrimitive?.contentOrNull?.lowercase()?.takeIf { it in setOf("mp3", "wav", "flac") } ?: "mp3"
        return runCatching {
            client.generate(
                AceStepClient.MusicRequest(prompt, lyrics, duration, bpm, key, timeSig, lang, format),
            )
        }.fold(
            onSuccess = { g -> ToolResult.ok("{\"uri\":${JsonPrimitive(g.uri)},\"file_name\":${JsonPrimitive(g.fileName)},\"model\":${JsonPrimitive(g.serverModel)},\"saved_to\":\"Music/Mythara\"}") },
            onFailure = { e -> ToolResult.fail("ACE-Step generation failed: ${e.message ?: e.javaClass.simpleName}") },
        )
    }
}
''')

(tools_dir / 'PlayAudioTool.kt').write_text(r'''package com.mythara.agent.tools

import android.content.Context
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.net.Uri
import com.mythara.agent.Tool
import com.mythara.agent.ToolResult
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonPrimitive
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class PlayAudioTool @Inject constructor(
    @ApplicationContext private val ctx: Context,
) : Tool {
    override val name = "play_audio"
    override val description = "Play or stop a generated local audio content URI."
    override val parameters: JsonElement = buildJsonObject {
        put("type", JsonPrimitive("object"))
        put("properties", buildJsonObject {
            put("action", buildJsonObject { put("type", JsonPrimitive("string")); put("description", JsonPrimitive("play or stop")) })
            put("uri", buildJsonObject { put("type", JsonPrimitive("string")) })
        })
        put("required", kotlinx.serialization.json.buildJsonArray { add(JsonPrimitive("action")) })
    }

    private var player: MediaPlayer? = null

    override suspend fun execute(args: JsonObject): ToolResult {
        val action = args["action"]?.jsonPrimitive?.contentOrNull?.lowercase().orEmpty()
        if (action == "stop") {
            releasePlayer()
            return ToolResult.ok("{\"status\":\"stopped\"}")
        }
        val uriText = args["uri"]?.jsonPrimitive?.contentOrNull.orEmpty()
        if (uriText.isBlank()) return ToolResult.fail("uri required")
        return runCatching {
            releasePlayer()
            player = MediaPlayer().apply {
                setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_MEDIA)
                        .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                        .build(),
                )
                setDataSource(ctx, Uri.parse(uriText))
                setOnCompletionListener { releasePlayer() }
                prepare()
                start()
            }
            ToolResult.ok("{\"status\":\"playing\",\"uri\":${JsonPrimitive(uriText)}}")
        }.getOrElse { ToolResult.fail("audio playback failed: ${it.message}") }
    }

    private fun releasePlayer() {
        runCatching { player?.stop() }
        runCatching { player?.release() }
        player = null
    }
}
''')

# Register tools.
p = Path('app/src/main/kotlin/com/mythara/agent/ToolRegistry.kt')
s = p.read_text()
anchor = '    generateImageTool: com.mythara.agent.tools.GenerateImageTool,\n'
if anchor not in s:
    raise SystemExit('ToolRegistry constructor anchor not found')
s = s.replace(anchor, anchor + '    generateMusicTool: com.mythara.agent.tools.GenerateMusicTool,\n    playAudioTool: com.mythara.agent.tools.PlayAudioTool,\n', 1)
anchor2 = '        generateImageTool,\n'
if anchor2 not in s:
    raise SystemExit('ToolRegistry list anchor not found')
s = s.replace(anchor2, anchor2 + '        generateMusicTool, playAudioTool,\n', 1)
p.write_text(s)

# -----------------------------------------------------------------------------
# Settings UI: official NPU agent + creative GGUF + ACE-Step server.
# -----------------------------------------------------------------------------
Path('app/src/main/kotlin/com/mythara/ui/settings/QwenAccelerationPanel.kt').write_text(r'''package com.mythara.ui.settings

import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
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
import com.mythara.ui.theme.Glyph
import com.mythara.ui.theme.MytharaColors

@Composable
fun QwenAccelerationPanel(vm: QwenSetupViewModel = hiltViewModel()) {
    val agent by vm.state.collectAsState()
    val creative by vm.creativeState.collectAsState()
    val mode by vm.mode.collectAsState()

    Column(Modifier.fillMaxWidth().border(1.dp, MytharaColors.SurfaceHigh, RoundedCornerShape(14.dp)).padding(14.dp)) {
        Text("Snapdragon AI · 듀얼 모델", style = MaterialTheme.typography.titleMedium, color = MytharaColors.Fg)
        Spacer(Modifier.height(8.dp))
        Text("1) Android Agent / FCC", color = MytharaColors.Fg)
        Text("Qwen3-VL-4B-Instruct · QAIRT w4a16 · SM8750 Hexagon NPU", style = MaterialTheme.typography.bodySmall, color = MytharaColors.FgDim)
        Text(stateText(agent), style = MaterialTheme.typography.bodyMedium, color = MytharaColors.Fg)
        if (agent is QwenNpuRuntime.State.Missing || agent is QwenNpuRuntime.State.Failed) {
            Button(onClick = vm::downloadAndLoad, colors = ButtonDefaults.buttonColors(containerColor = MytharaColors.Charple, contentColor = MytharaColors.Fg)) { Text("공식 NPU 모델 다운로드") }
        }

        Spacer(Modifier.height(14.dp))
        Text("2) 자유 대화 / 가사", color = MytharaColors.Fg)
        Text("Qwen3-VL-4B-Instruct-Uncensored-abliterated · GGUF Q4_K_M", style = MaterialTheme.typography.bodySmall, color = MytharaColors.FgDim)
        Text(stateText(creative), style = MaterialTheme.typography.bodyMedium, color = MytharaColors.Fg)
        if (creative is QwenNpuRuntime.State.Missing || creative is QwenNpuRuntime.State.Failed) {
            Button(onClick = vm::downloadCreativeAndLoad) { Text("자유 대화 모델 다운로드 (~3GB + vision)") }
        }

        Spacer(Modifier.height(10.dp))
        Row(
            Modifier.fillMaxWidth().clickable { vm.setCreativeMode(mode != QwenNpuRuntime.Mode.CREATIVE) }.padding(vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(if (mode == QwenNpuRuntime.Mode.CREATIVE) Glyph.CircleFilled else Glyph.CircleOutline, color = MytharaColors.Charple)
            Spacer(Modifier.padding(end = 6.dp))
            Text("자유 대화 모드", color = MytharaColors.Fg)
        }
        Text(
            "휴대폰 제어/FCC는 항상 공식 QAIRT 모델을 사용합니다. 자유 대화 모드에서는 일반 대화·가사·사진 설명만 Uncensored 모델을 사용합니다. 두 모델을 동시에 RAM에 올리지 않고 필요할 때 교체합니다.",
            style = MaterialTheme.typography.bodySmall,
            color = MytharaColors.FgDim,
        )
    }
}

@Composable
private fun stateText(s: QwenNpuRuntime.State): String = when (s) {
    QwenNpuRuntime.State.Missing -> "상태: 미설치"
    QwenNpuRuntime.State.Initializing -> "상태: 런타임 초기화 중…"
    is QwenNpuRuntime.State.Downloading -> "상태: 다운로드 ${s.percent}%"
    QwenNpuRuntime.State.Downloaded -> "상태: 다운로드 완료"
    QwenNpuRuntime.State.Loading -> "상태: 로드 중…"
    is QwenNpuRuntime.State.Loaded -> "상태: ${s.backend}"
    is QwenNpuRuntime.State.Failed -> "상태: 실패 · ${s.message}"
}
''')

Path('app/src/main/kotlin/com/mythara/ui/settings/AceStepPanel.kt').write_text(r'''package com.mythara.ui.settings

import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.mythara.local.MusicSetupViewModel
import com.mythara.ui.theme.MytharaColors

@Composable
fun AceStepPanel(vm: MusicSetupViewModel = hiltViewModel()) {
    val config by vm.config.collectAsState()
    val testResult by vm.testResult.collectAsState()
    var url by remember { mutableStateOf(config.baseUrl) }
    var key by remember { mutableStateOf(config.apiKey) }
    var model by remember { mutableStateOf(config.model) }
    var thinking by remember { mutableStateOf(config.thinking) }
    LaunchedEffect(config) { url = config.baseUrl; key = config.apiKey; model = config.model; thinking = config.thinking }

    Column(Modifier.fillMaxWidth().border(1.dp, MytharaColors.SurfaceHigh, RoundedCornerShape(14.dp)).padding(14.dp)) {
        Text("ACE-Step 1.5 · 실제 노래 생성", style = MaterialTheme.typography.titleMedium, color = MytharaColors.Fg)
        Text("Fold7은 가사/곡 설계를 담당하고, 보컬+반주 합성은 PC/서버의 ACE-Step이 담당합니다.", style = MaterialTheme.typography.bodySmall, color = MytharaColors.FgDim)
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(value = url, onValueChange = { url = it }, label = { Text("서버 주소") }, placeholder = { Text("http://192.168.0.10:8001") }, singleLine = true, modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(6.dp))
        OutlinedTextField(value = key, onValueChange = { key = it }, label = { Text("API 키 (선택)") }, visualTransformation = PasswordVisualTransformation(), singleLine = true, modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(6.dp))
        OutlinedTextField(value = model, onValueChange = { model = it }, label = { Text("ACE-Step 모델") }, singleLine = true, modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(8.dp))
        Row {
            Button(onClick = { thinking = !thinking }) { Text(if (thinking) "5Hz LM: 켜짐" else "5Hz LM: 꺼짐") }
            Spacer(Modifier.padding(horizontal = 4.dp))
            Button(onClick = { vm.save(url, key, model, thinking) }) { Text("저장") }
            Spacer(Modifier.padding(horizontal = 4.dp))
            Button(onClick = { vm.save(url, key, model, thinking); vm.test() }) { Text("연결 테스트") }
        }
        if (testResult.isNotBlank()) Text(testResult, modifier = Modifier.padding(top = 6.dp), color = MytharaColors.Fg)
        Spacer(Modifier.height(6.dp))
        Text("생성된 MP3/WAV/FLAC은 휴대폰 Music/Mythara에 저장되고 자동 재생됩니다. 같은 Wi-Fi, Tailscale 또는 HTTPS 주소를 사용할 수 있습니다.", style = MaterialTheme.typography.bodySmall, color = MytharaColors.FgDim)
    }
}
''')

# Insert ACE panel after Qwen panel.
p = Path('app/src/main/kotlin/com/mythara/ui/settings/SettingsScreen.kt')
s = p.read_text()
anchor = '        QwenAccelerationPanel()\n\n        Spacer(Modifier.height(16.dp))\n        AutopilotPanel()'
if anchor not in s:
    raise SystemExit('SettingsScreen v7 insertion anchor not found')
s = s.replace(anchor, '        QwenAccelerationPanel()\n\n        Spacer(Modifier.height(16.dp))\n        AceStepPanel()\n\n        Spacer(Modifier.height(16.dp))\n        AutopilotPanel()', 1)
p.write_text(s)

# -----------------------------------------------------------------------------
# FCC routing changes: official agent for tool decisions, creative model for
# ordinary free chat + music/lyrics planning, deterministic ACE-Step music tool.
# -----------------------------------------------------------------------------
p = Path('app/src/main/kotlin/com/mythara/local/LocalGemmaChat.kt')
s = p.read_text()
# qwen injection already added by v6 patch. Change agent runRaw implementation.
old = '''    private suspend fun runRaw(prompt: String, maxLen: Int): String {\n        val qwenOut = runCatching { qwen.runRaw(prompt, maxLen = maxLen) }.getOrNull()\n        val raw = if (!qwenOut.isNullOrBlank()) qwenOut else runCatching { gemma.runRaw(prompt, maxLen = maxLen) }.getOrNull()\n        return raw.orEmpty().let(Thinks::strip).trim()\n    }'''
new = '''    private suspend fun runRaw(prompt: String, maxLen: Int): String {\n        val qwenOut = runCatching { qwen.runAgentRaw(prompt, maxLen = maxLen) }.getOrNull()\n        val raw = if (!qwenOut.isNullOrBlank()) qwenOut else runCatching { gemma.runRaw(prompt, maxLen = maxLen) }.getOrNull()\n        return raw.orEmpty().let(Thinks::strip).trim()\n    }\n\n    private suspend fun runCreative(prompt: String, maxLen: Int): String {\n        val out = runCatching { qwen.runCreativeRaw(prompt, maxLen) }.getOrNull()\n        return out.orEmpty().let(Thinks::strip).trim()\n    }'''
if old not in s:
    raise SystemExit('LocalGemmaChat v6 runRaw anchor not found')
s = s.replace(old, new, 1)

# Insert music routing after capability check and before image generation.
needle = '''        if (isCapabilityQuestion(latestUser)) {\n            emit(StreamingChat.StreamEvent.Text(capabilitySummary(tools)))\n            emit(StreamingChat.StreamEvent.Done("stop"))\n            return@flow\n        }\n\n        // Image generation already exists in upstream Mythara.'''
insert = '''        if (isCapabilityQuestion(latestUser)) {\n            emit(StreamingChat.StreamEvent.Text(capabilitySummary(tools)))\n            emit(StreamingChat.StreamEvent.Done("stop"))\n            return@flow\n        }\n\n        // Actual vocal music: let the freer local Qwen build lyrics + metadata,\n        // then send that structured plan to the ACE-Step synthesis tool.\n        if (isMusicGenerationRequest(latestUser)) {\n            val musicTool = tools.firstOrNull { it.function.name == "generate_music" }\n            if (musicTool != null) {\n                var plan = runCreative(musicPlanPrompt(messages), MUSIC_PLAN_OUT)\n                var args = firstJsonObject(plan)\n                if (args == null) {\n                    plan = runRaw(musicPlanPrompt(messages), MUSIC_PLAN_OUT)\n                    args = firstJsonObject(plan)\n                }\n                if (args == null) {\n                    val p = kotlinx.serialization.json.JsonPrimitive(latestUser).toString()\n                    args = "{\\\"prompt\\\":" + p + ",\\\"lyrics\\\":\\\"[Verse 1]\\n가사를 먼저 작성해 달라고 요청해 주세요.\\\",\\\"duration_sec\\\":180,\\\"vocal_language\\\":\\\"ko\\\",\\\"format\\\":\\\"mp3\\\"}"\n                }\n                emitDirectToolCall(musicTool, args, "WORKER")\n                return@flow\n            }\n        }\n\n        // Image generation already exists in upstream Mythara.'''
if needle not in s:
    raise SystemExit('LocalGemmaChat capability anchor not found')
s = s.replace(needle, insert, 1)

# Ordinary answer uses creative model when free mode is enabled, with agent fallback.
needle = '''        var answer = cleanAnswer(runRaw(mainAnswerPrompt(messages), ANSWER_OUT))'''
replacement = '''        var answer = if (qwen.isCreativeMode()) {\n            cleanAnswer(runCreative(mainAnswerPrompt(messages), ANSWER_OUT))\n        } else {\n            cleanAnswer(runRaw(mainAnswerPrompt(messages), ANSWER_OUT))\n        }'''
if needle not in s:
    raise SystemExit('LocalGemmaChat main answer anchor not found')
s = s.replace(needle, replacement, 1)

# Auto-play generated music before reviewer/final response.
needle = '''        // REVIEWER: must explicitly PASS or RETRY based on the actual tool output.\n'''
insert = '''        if (lastExecutedToolName(messages) == "generate_music") {\n            val uri = Regex("""["]uri["]\\s*:\\s*["]([^"]+)["]""")\n                .find(toolResult)?.groupValues?.getOrNull(1)\n            val playTool = tools.firstOrNull { it.function.name == "play_audio" }\n            if (!uri.isNullOrBlank() && playTool != null) {\n                val uriJson = kotlinx.serialization.json.JsonPrimitive(uri).toString()\n                emitDirectToolCall(playTool, "{\\\"action\\\":\\\"play\\\",\\\"uri\\\":" + uriJson + "}", "WORKER")\n                return\n            }\n        }\n\n        // REVIEWER: must explicitly PASS or RETRY based on the actual tool output.\n'''
if needle not in s:
    raise SystemExit('LocalGemmaChat reviewer anchor not found')
s = s.replace(needle, insert, 1)

# Add helper functions before MAIN section.
anchor = '''    // ── MAIN ────────────────────────────────────────────────────────────────\n'''
helpers = r'''    private fun isMusicGenerationRequest(text: String): Boolean {
        val t = text.replace(" ", "").lowercase()
        val music = listOf("노래", "음악", "곡", "보컬", "반주", "song", "music").any { t.contains(it) }
        val create = listOf("만들어줘", "만들어", "생성해줘", "생성해", "작곡해", "불러줘", "완성해").any { t.contains(it) }
        val question = t.endsWith("?") && listOf("가능", "할수", "돼", "되나").any { t.contains(it) }
        return music && create && !question
    }

    private fun musicPlanPrompt(messages: List<ChatMessage>): String = buildString {
        appendLine("[MYTHARA MUSIC PLANNER]")
        appendLine("사용자 요청을 ACE-Step 1.5가 바로 합성할 수 있는 곡 설계 JSON으로 만드세요.")
        appendLine("가사는 반드시 완성형으로 직접 작성하고 [Intro] [Verse 1] [Pre-Chorus] [Chorus] [Verse 2] [Bridge] [Final Chorus] 같은 섹션을 사용하세요.")
        appendLine("사용자가 한국어면 기본 vocal_language는 ko. 사용자가 원하는 분위기/표현 강도를 임의로 순화하지 마세요.")
        appendLine("JSON 객체만 출력. 필드: prompt, lyrics, duration_sec(10-600), bpm(30-300), key_scale, time_signature, vocal_language, format(mp3).")
        appendLine("최근 대화:")
        appendRecent(messages, ANSWER_CONTEXT)
        appendLine("JSON:")
    }.take(18000)

'''
if anchor not in s:
    raise SystemExit('LocalGemmaChat helper anchor not found')
s = s.replace(anchor, helpers + anchor, 1)

# Capability summary: reflect actual song synthesis tool.
old = '''        return "현재 이 폰에서 가능한 주요 작업은 다음과 같아.\\n$body\\n\\n현재 기본 도구에는 영상 생성이나 완성된 음악/노래 생성 엔진은 연결되어 있지 않아. 이미지 생성은 로컬 Gemma가 아니라 Gemini 이미지 API를 사용하므로 해당 기능만 인터넷과 Gemini API 키가 필요해."'''
new = '''        val musicNote = if ("generate_music" in names) "ACE-Step 서버가 설정되어 있으면 실제 보컬+반주 노래 생성과 MP3/WAV 저장도 가능해." else "ACE-Step 서버가 아직 연결되지 않아 실제 노래 합성은 비활성 상태야."\n        return "현재 이 폰에서 가능한 주요 작업은 다음과 같아.\\n$body\\n\\n$musicNote 영상 생성 엔진은 아직 연결되어 있지 않아. 이미지 생성은 Gemini 이미지 API를 사용하므로 해당 기능만 인터넷과 Gemini API 키가 필요해."'''
if old not in s:
    raise SystemExit('capability summary old note not found')
s = s.replace(old, new, 1)

# Add generate_music capability line.
needle = '''        if ("render_canvas" in names) {\n            parts += "Canvas에 카드·HTML·간단한 2D/3D 화면 표시"\n        }'''
replacement = '''        if ("render_canvas" in names) {\n            parts += "Canvas에 카드·HTML·간단한 2D/3D 화면 표시"\n        }\n        if ("generate_music" in names) {\n            parts += "ACE-Step 1.5 서버를 이용한 실제 보컬·반주 노래 생성 및 Music/Mythara 저장"\n        }'''
if needle not in s:
    raise SystemExit('capability list anchor not found')
s = s.replace(needle, replacement, 1)

# Companion constant.
needle = '''        private const val ARGS_OUT = 4000\n'''
if needle in s and 'MUSIC_PLAN_OUT' not in s:
    s = s.replace(needle, needle + '        private const val MUSIC_PLAN_OUT = 12000\n', 1)
elif 'MUSIC_PLAN_OUT' not in s:
    # fallback insert before closing companion by known MAX_FCC line
    s = s.replace('        private const val MAX_FCC_TOOL_ATTEMPTS = 3\n', '        private const val MAX_FCC_TOOL_ATTEMPTS = 3\n        private const val MUSIC_PLAN_OUT = 12000\n', 1)
p.write_text(s)

print('Mythara Local Fold7 KR FCC v7 hybrid patch applied')
