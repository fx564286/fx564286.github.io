from pathlib import Path

# Mythara Local Fold7 KR FCC v8
# Fixes observed on the user's Android 17 / 16KB-page Fold7:
# - explicitly enable Android 16KB backcompat so incompatible vendor .so files do not trigger the launch warning
# - make Qualcomm AI Hub model pull resilient: Qwen3-VL-4B first, then proven SM8750 Qwen2.5-VL-7B fallback
# - do not force HTP0 for QAIRT bundles; let Qualcomm select the NPU compute unit from the bundle
# - ACE-Step behaves like the desktop CLI: default acestep-v15-turbo, no required address field,
#   automatically discovers a healthy :8001 server on localhost / same LAN and remembers it

# -----------------------------------------------------------------------------
# Version + Android 16KB page-size compatibility mode.
# -----------------------------------------------------------------------------
p = Path('app/build.gradle.kts')
s = p.read_text()
s = s.replace('versionNameSuffix = "-local-fold7-kr-v7"', 'versionNameSuffix = "-local-fold7-kr-v8"')
s = s.replace('versionCode = 7', 'versionCode = 8', 1)
p.write_text(s)

p = Path('app/src/main/AndroidManifest.xml')
s = p.read_text()
if 'android:pageSizeCompat=' not in s:
    s = s.replace('<application', '<application\n        android:pageSizeCompat="enabled"', 1)
p.write_text(s)

# -----------------------------------------------------------------------------
# Qualcomm runtime hotfixes.
# -----------------------------------------------------------------------------
p = Path('app/src/main/kotlin/com/mythara/local/QwenNpuRuntime.kt')
s = p.read_text()

old = '''            _agentState.value = when {
                active == Active.AGENT && wrapper != null -> State.Loaded(activeBackend)
                ModelManagerWrapper.getPaths(AGENT_MODEL) != null -> State.Downloaded
                else -> State.Missing
            }'''
new = '''            _agentState.value = when {
                active == Active.AGENT && wrapper != null -> State.Loaded(activeBackend)
                ModelManagerWrapper.getPaths(AGENT_MODEL) != null -> State.Downloaded
                ModelManagerWrapper.getPaths(AGENT_FALLBACK_MODEL) != null -> State.Downloaded
                else -> State.Missing
            }'''
if old not in s:
    raise SystemExit('v8 qwen refreshState anchor not found')
s = s.replace(old, new, 1)

old = '''    suspend fun downloadAgentAndLoad(): Boolean = withContext(Dispatchers.IO) {
        downloadModel(
            modelName = AGENT_MODEL,
            precision = AGENT_PRECISION,
            hub = HubSource.AUTO,
            chipset = CHIPSET,
            stateFlow = _agentState,
        ) && ensureAgentLoadedIfPresent()
    }'''
new = '''    suspend fun downloadAgentAndLoad(): Boolean = withContext(Dispatchers.IO) {
        // Qualcomm's Android ModelManager selects the precompiled AI-Hub precision itself.
        // Passing a precision can fail for a model/chipset combination even when an asset exists.
        val primaryPulled = downloadModel(
            modelName = AGENT_MODEL,
            precision = null,
            hub = HubSource.AUTO,
            chipset = CHIPSET,
            stateFlow = _agentState,
        )
        if (primaryPulled && ensureAgentLoadedIfPresent()) return@withContext true

        // Qwen3-VL-4B AI-Hub assets have varied by SDK release. Qwen2.5-VL-7B has a
        // published GENIEX_QAIRT w4a16 Snapdragon 8 Elite bundle, so use it automatically.
        _agentState.value = State.Missing
        val fallbackPulled = downloadModel(
            modelName = AGENT_FALLBACK_MODEL,
            precision = null,
            hub = HubSource.AUTO,
            chipset = CHIPSET,
            stateFlow = _agentState,
        )
        fallbackPulled && ensureAgentLoadedIfPresent()
    }'''
if old not in s:
    raise SystemExit('v8 qwen downloadAgentAndLoad anchor not found')
s = s.replace(old, new, 1)

old = '''                val paths = ModelManagerWrapper.getPaths(AGENT_MODEL) ?: run {
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
                true'''
new = '''                val selectedModel = when {
                    ModelManagerWrapper.getPaths(AGENT_MODEL) != null -> AGENT_MODEL
                    ModelManagerWrapper.getPaths(AGENT_FALLBACK_MODEL) != null -> AGENT_FALLBACK_MODEL
                    else -> null
                } ?: run {
                    _agentState.value = State.Missing
                    return@runCatching false
                }
                val paths = ModelManagerWrapper.getPaths(selectedModel) ?: run {
                    _agentState.value = State.Missing
                    return@runCatching false
                }
                switchOutLocked()
                _agentState.value = State.Loading
                val conf = ModelConfig(enable_thinking = false)
                val built = buildVlm(
                    VlmCreateInput(
                        model_name = paths.model_name,
                        model_path = paths.model_path,
                        mmproj_path = paths.mmproj_path,
                        config = conf,
                        runtime_id = paths.runtime_id.ifEmpty { "qairt" },
                        // For precompiled QAIRT bundles, null lets the bundle select NPU.
                        compute_unit = null,
                    ),
                )
                wrapper = built
                active = Active.AGENT
                activeBackend = if (selectedModel == AGENT_MODEL) {
                    "Qwen3-VL-4B · Hexagon NPU · QAIRT"
                } else {
                    "Qwen2.5-VL-7B · Hexagon NPU · QAIRT"
                }
                _agentState.value = State.Loaded(activeBackend)
                true'''
if old not in s:
    raise SystemExit('v8 qwen ensureAgentLoaded anchor not found')
s = s.replace(old, new, 1)

s = s.replace('        precision: String,\n', '        precision: String?,\n', 1)
if 'const val AGENT_FALLBACK_MODEL' not in s:
    s = s.replace(
        '        const val AGENT_MODEL = "ai-hub-models/Qwen3-VL-4B-Instruct"\n',
        '        const val AGENT_MODEL = "ai-hub-models/Qwen3-VL-4B-Instruct"\n'
        '        const val AGENT_FALLBACK_MODEL = "ai-hub-models/Qwen2.5-VL-7B-Instruct"\n',
        1,
    )
p.write_text(s)

# Settings text should describe what the runtime actually does.
p = Path('app/src/main/kotlin/com/mythara/ui/settings/QwenAccelerationPanel.kt')
s = p.read_text()
s = s.replace(
    'Qwen3-VL-4B-Instruct · Qualcomm QAIRT w4a16',
    'Qwen3-VL-4B 우선 · Qwen2.5-VL-7B 자동 대체 · Qualcomm QAIRT',
)
s = s.replace('Galaxy Z Fold7 / SM8750 · Hexagon NPU(HTP0) 우선', 'Galaxy Z Fold7 / SM8750 · Hexagon NPU 자동 선택')
s = s.replace('공식 NPU 모델 다운로드', 'NPU 모델 자동 설치')
p.write_text(s)

# -----------------------------------------------------------------------------
# ACE-Step config: manual URL becomes optional; auto-discovered endpoint is cached.
# -----------------------------------------------------------------------------
qdir = Path('app/src/main/kotlin/com/mythara/local')
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
        val thinking: Boolean = false,
    )

    private val prefs = ctx.getSharedPreferences("mythara_acestep", Context.MODE_PRIVATE)
    private val _config = MutableStateFlow(load())
    val config: StateFlow<Config> = _config.asStateFlow()

    val resolvedUrl: String
        get() = prefs.getString("resolved_url", "").orEmpty()

    fun rememberResolved(url: String) {
        prefs.edit().putString("resolved_url", url.trim().removeSuffix("/")).apply()
    }

    fun clearResolved() {
        prefs.edit().remove("resolved_url").apply()
    }

    fun save(baseUrl: String, apiKey: String, model: String, thinking: Boolean) {
        val clean = baseUrl.trim().removeSuffix("/")
        prefs.edit()
            .putString("base_url", clean)
            .putString("api_key", apiKey.trim())
            .putString("model", model.trim().ifBlank { "acestep-v15-turbo" })
            .putBoolean("thinking", thinking)
            .apply()
        _config.value = Config(clean, apiKey.trim(), model.trim().ifBlank { "acestep-v15-turbo" }, thinking)
        if (clean.isNotBlank()) rememberResolved(clean)
    }

    private fun load() = Config(
        baseUrl = prefs.getString("base_url", "").orEmpty(),
        apiKey = prefs.getString("api_key", "").orEmpty(),
        model = prefs.getString("model", "acestep-v15-turbo").orEmpty().ifBlank { "acestep-v15-turbo" },
        thinking = prefs.getBoolean("thinking", false),
    )
}
''')

(qdir / 'AceStepClient.kt').write_text(r'''package com.mythara.local

import android.content.ContentValues
import android.content.Context
import android.os.Environment
import android.provider.MediaStore
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
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
import java.net.Inet4Address
import java.net.NetworkInterface
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
    private val probeHttp = OkHttpClient.Builder()
        .connectTimeout(350, TimeUnit.MILLISECONDS)
        .readTimeout(700, TimeUnit.MILLISECONDS)
        .callTimeout(1, TimeUnit.SECONDS)
        .build()

    suspend fun health(): Pair<Boolean, String> = withContext(Dispatchers.IO) {
        val url = resolveServer(forceScan = true)
            ?: return@withContext false to "ACE-Step :8001 서버를 자동으로 찾지 못했습니다."
        true to "ACE-Step 자동 연결됨 · $url"
    }

    suspend fun resolveServer(forceScan: Boolean = false): String? = withContext(Dispatchers.IO) {
        val c = settings.config.value
        val priority = linkedSetOf<String>()
        if (c.baseUrl.isNotBlank()) priority += c.baseUrl.normalizeUrl()
        if (!forceScan && settings.resolvedUrl.isNotBlank()) priority += settings.resolvedUrl.normalizeUrl()
        priority += "http://127.0.0.1:8001"
        priority += "http://localhost:8001"

        for (candidate in priority) {
            if (probe(candidate, c.apiKey)) {
                settings.rememberResolved(candidate)
                return@withContext candidate
            }
        }

        // The desktop CLI historically exposes ACE-Step on :8001. Scan only local /24
        // networks and common home-LAN ranges; never send payloads, only GET /health.
        val candidates = discoverLanCandidates().filterNot { it in priority }
        val sem = Semaphore(48)
        for (chunk in candidates.chunked(96)) {
            val found = coroutineScope {
                chunk.map { candidate ->
                    async(Dispatchers.IO) {
                        sem.withPermit { if (probe(candidate, c.apiKey)) candidate else null }
                    }
                }.awaitAll().firstOrNull { it != null }
            }
            if (found != null) {
                settings.rememberResolved(found)
                return@withContext found
            }
        }
        null
    }

    suspend fun generate(req: MusicRequest): Generated = withContext(Dispatchers.IO) {
        val c = settings.config.value
        val base = resolveServer(forceScan = false)
            ?: resolveServer(forceScan = true)
            ?: error("ACE-Step 서버를 자동으로 찾지 못했습니다. 데스크톱 CLI의 ACE-Step :8001 런타임이 실행 중인지 확인해 주세요.")

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
            // Keep the desktop-CLI balanced default for CPU-only ACE-Step hosts.
            put("inference_steps", JsonPrimitive(4))
            put("task_type", JsonPrimitive("text2music"))
            req.bpm?.let { put("bpm", JsonPrimitive(it.coerceIn(30, 300))) }
            req.keyScale?.takeIf { it.isNotBlank() }?.let { put("key_scale", JsonPrimitive(it)) }
            req.timeSignature?.takeIf { it.isNotBlank() }?.let { put("time_signature", JsonPrimitive(it)) }
        }
        val release = request(base + "/release_task", "POST", bodyJson.toString(), c.apiKey).use { resp ->
            val text = resp.body?.string().orEmpty()
            if (!resp.isSuccessful) error("ACE-Step 작업 생성 실패 HTTP ${resp.code}: ${text.take(240)}")
            text
        }
        val taskId = json.parseToJsonElement(release).jsonObject["data"]
            ?.jsonObject?.get("task_id")?.jsonPrimitive?.contentOrNull
            ?: error("ACE-Step 응답에 task_id가 없습니다.")

        var audioRelative: String? = null
        var serverModel = c.model
        for (poll in 0 until MAX_POLLS) {
            delay(POLL_MS)
            val queryBody = buildJsonObject {
                put("task_id_list", buildJsonArray { add(JsonPrimitive(taskId)) })
            }
            val query = request(base + "/query_result", "POST", queryBody.toString(), c.apiKey).use { resp ->
                val text = resp.body?.string().orEmpty()
                if (!resp.isSuccessful) error("ACE-Step 상태 조회 실패 HTTP ${resp.code}: ${text.take(240)}")
                text
            }
            val root = json.parseToJsonElement(query).jsonObject
            val row = (root["data"] as? JsonArray)?.firstOrNull()?.jsonObject
            val status = row?.get("status")?.jsonPrimitive?.intOrNull ?: 0
            if (status == 2) error("ACE-Step 음악 생성 실패")
            if (status == 1) {
                val resultText = row?.get("result")?.jsonPrimitive?.contentOrNull.orEmpty()
                val results = runCatching { json.parseToJsonElement(resultText).jsonArray }.getOrNull()
                val item = results?.firstOrNull()?.jsonObject
                audioRelative = item?.get("file")?.jsonPrimitive?.contentOrNull
                serverModel = item?.get("dit_model")?.jsonPrimitive?.contentOrNull ?: c.model
                if (!audioRelative.isNullOrBlank()) break
            }
        }
        val rel = audioRelative ?: error("ACE-Step 생성 시간이 제한을 초과했습니다.")
        val url = if (rel.startsWith("http://") || rel.startsWith("https://")) rel else base + rel
        val fileName = "Mythara_${System.currentTimeMillis()}.${req.format.lowercase()}"
        val uri = saveAudio(url, fileName, req.format, c.apiKey)
        Generated(uri.toString(), fileName, serverModel)
    }

    private fun probe(baseUrl: String, key: String): Boolean = runCatching {
        val b = Request.Builder().url(baseUrl.normalizeUrl() + "/health").get()
        if (key.isNotBlank()) b.header("Authorization", "Bearer $key")
        probeHttp.newCall(b.build()).execute().use { it.isSuccessful }
    }.getOrDefault(false)

    private fun discoverLanCandidates(): List<String> {
        val prefixes = linkedSetOf<String>()
        runCatching {
            val interfaces = NetworkInterface.getNetworkInterfaces()
            while (interfaces.hasMoreElements()) {
                val ni = interfaces.nextElement()
                if (!ni.isUp || ni.isLoopback) continue
                val addrs = ni.inetAddresses
                while (addrs.hasMoreElements()) {
                    val addr = addrs.nextElement()
                    if (addr is Inet4Address && !addr.isLoopbackAddress) {
                        val parts = addr.hostAddress?.split('.') ?: continue
                        if (parts.size == 4) prefixes += parts.take(3).joinToString(".")
                    }
                }
            }
        }
        prefixes += "192.168.0"
        prefixes += "192.168.1"
        return buildList {
            for (prefix in prefixes.take(5)) {
                for (host in 1..254) add("http://$prefix.$host:8001")
            }
        }.distinct()
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

    private fun String.normalizeUrl(): String = trim().removeSuffix("/")

    companion object {
        private const val POLL_MS = 2_000L
        private const val MAX_POLLS = 600 // CPU hosts can take ~20 minutes for full songs
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
    private val _testResult = MutableStateFlow("자동 연결 대기")
    val testResult: StateFlow<String> = _testResult.asStateFlow()

    init { autoDiscover() }

    fun save(url: String, key: String, model: String, thinking: Boolean) = settings.save(url, key, model, thinking)

    fun autoDiscover() {
        viewModelScope.launch {
            _testResult.value = "ACE-Step 자동 검색 중…"
            val (ok, msg) = client.health()
            _testResult.value = if (ok) "✓ $msg" else "✕ $msg"
        }
    }

    fun test() = autoDiscover()
}
''')

# Settings panel: auto discovery is the normal path; manual address remains only as an override.
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
        Text("ACE-Step 1.5 · 자동 노래 생성", style = MaterialTheme.typography.titleMedium, color = MytharaColors.Fg)
        Text("기존 CLI처럼 acestep-v15-turbo를 사용하고 :8001 런타임을 자동으로 찾아 연결합니다. 주소 입력은 보통 필요 없습니다.", style = MaterialTheme.typography.bodySmall, color = MytharaColors.FgDim)
        Spacer(Modifier.height(8.dp))
        Text(testResult, color = MytharaColors.Fg)
        Spacer(Modifier.height(8.dp))
        Row {
            Button(onClick = vm::autoDiscover) { Text("자동 검색") }
            Spacer(Modifier.padding(horizontal = 4.dp))
            Button(onClick = { thinking = !thinking; vm.save(url, key, model, thinking) }) {
                Text(if (thinking) "5Hz LM: 켜짐" else "5Hz LM: 꺼짐")
            }
        }
        Spacer(Modifier.height(10.dp))
        Text("고급 설정 · 자동 검색이 안 될 때만 사용", style = MaterialTheme.typography.bodySmall, color = MytharaColors.FgDim)
        OutlinedTextField(value = url, onValueChange = { url = it }, label = { Text("서버 주소 (선택)") }, placeholder = { Text("비워두면 자동 검색") }, singleLine = true, modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(6.dp))
        OutlinedTextField(value = key, onValueChange = { key = it }, label = { Text("API 키 (선택)") }, visualTransformation = PasswordVisualTransformation(), singleLine = true, modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(6.dp))
        OutlinedTextField(value = model, onValueChange = { model = it }, label = { Text("모델") }, singleLine = true, modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(6.dp))
        Button(onClick = { vm.save(url, key, model, thinking); vm.autoDiscover() }) { Text("고급 설정 저장") }
        Spacer(Modifier.height(6.dp))
        Text("기본값은 CPU 호스트에 맞춘 4-step balanced 생성입니다. 완성 음원은 Music/Mythara에 저장되고 자동 재생됩니다.", style = MaterialTheme.typography.bodySmall, color = MytharaColors.FgDim)
    }
}
''')

print('Mythara Fold7 KR FCC v8 fixes applied')
