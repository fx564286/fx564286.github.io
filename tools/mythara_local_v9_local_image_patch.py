from pathlib import Path

# Mythara Local Fold7 KR FCC v9
# - local-first image generation with MediaPipe Image Generator + converted SD 1.5
# - no Gemini API key required for normal image generation
# - one-time ~2.1 GB model download from a public CreativeML OpenRAIL-M HF repo
# - MediaPipe/OpenCL GPU path on Fold7; Gemini remains optional fallback only
# - stable package/signing retained from v5

# -----------------------------------------------------------------------------
# Version + MediaPipe Image Generator dependency.
# -----------------------------------------------------------------------------
p = Path('app/build.gradle.kts')
s = p.read_text()
s = s.replace('versionNameSuffix = "-local-fold7-kr-v8"', 'versionNameSuffix = "-local-fold7-kr-v9"')
s = s.replace('versionCode = 8', 'versionCode = 9', 1)
if 'tasks-vision-image-generator:0.10.14' not in s:
    s = s.replace(
        'dependencies {\n',
        'dependencies {\n    // v9: on-device Stable Diffusion 1.5 via MediaPipe/OpenCL.\n    implementation("com.google.mediapipe:tasks-vision-image-generator:0.10.14")\n\n',
        1,
    )
p.write_text(s)

# Android 12+ OpenCL discovery required by MediaPipe Image Generator.
p = Path('app/src/main/AndroidManifest.xml')
s = p.read_text()
if 'libOpenCL.so' not in s:
    anchor = '        tools:targetApi="36">\n'
    libs = '''        <uses-native-library android:name="libOpenCL.so" android:required="false" />\n        <uses-native-library android:name="libOpenCL-car.so" android:required="false" />\n        <uses-native-library android:name="libOpenCL-pixel.so" android:required="false" />\n\n'''
    if anchor not in s:
        raise SystemExit('v9 manifest application anchor not found')
    s = s.replace(anchor, anchor + libs, 1)
p.write_text(s)

qdir = Path('app/src/main/kotlin/com/mythara/local')
qdir.mkdir(parents=True, exist_ok=True)

# -----------------------------------------------------------------------------
# Model store: public MediaPipe-converted Stable Diffusion 1.5.
# The upstream converted checkpoint contains ~1040 bin files (~2.07 GB), so
# production installs download the snapshot concurrently and resume .part files.
# -----------------------------------------------------------------------------
(qdir / 'LocalImageModelStore.kt').write_text(r'''package com.mythara.local

import android.content.Context
import android.os.StatFs
import android.util.Log
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.sync.withPermit
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.longOrNull
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.net.URLEncoder
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicLong
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class LocalImageModelStore @Inject constructor(
    @ApplicationContext private val ctx: Context,
) {
    sealed interface State {
        data object Missing : State
        data object Listing : State
        data class Downloading(val percent: Int, val doneFiles: Int, val totalFiles: Int) : State
        data object Ready : State
        data class Failed(val message: String) : State
    }

    data class RemoteFile(val path: String, val size: Long)

    private val _state = MutableStateFlow<State>(if (isReadyOnDisk()) State.Ready else State.Missing)
    val state: StateFlow<State> = _state.asStateFlow()
    private val installLock = Mutex()
    private val json = Json { ignoreUnknownKeys = true; isLenient = true }
    private val http = OkHttpClient.Builder()
        .connectTimeout(20, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.MINUTES)
        .writeTimeout(60, TimeUnit.SECONDS)
        .followRedirects(true)
        .followSslRedirects(true)
        .build()

    val modelDir: File get() = File(ctx.filesDir, "image_generator/bins")

    fun refresh() {
        _state.value = if (isReadyOnDisk()) State.Ready else State.Missing
    }

    suspend fun ensureReady(autoInstall: Boolean = false): Boolean {
        if (isReadyOnDisk()) {
            _state.value = State.Ready
            return true
        }
        return if (autoInstall) install() else false
    }

    suspend fun install(): Boolean = installLock.withLock {
        if (isReadyOnDisk()) {
            _state.value = State.Ready
            return@withLock true
        }
        withContext(Dispatchers.IO) {
            runCatching {
                val free = StatFs(ctx.filesDir.absolutePath).availableBytes
                require(free >= MIN_FREE_BYTES) {
                    "로컬 이미지 모델 설치에 저장공간이 부족합니다. 최소 3GB 이상 비워 주세요."
                }
                modelDir.mkdirs()
                _state.value = State.Listing
                val files = fetchFileList()
                require(files.size > 500) { "이미지 모델 파일 목록이 비정상적입니다 (${files.size}개)." }

                val totalBytes = files.sumOf { it.size.coerceAtLeast(0L) }
                val doneBytes = AtomicLong(0L)
                val doneFiles = AtomicLong(0L)
                val sem = Semaphore(MAX_PARALLEL)

                // Count already-complete files before starting network work.
                files.forEach { rf ->
                    val target = File(modelDir, rf.path)
                    if (target.isFile && (rf.size <= 0L || target.length() == rf.size)) {
                        doneBytes.addAndGet(if (rf.size > 0L) rf.size else target.length())
                        doneFiles.incrementAndGet()
                    }
                }
                publishProgress(doneBytes.get(), totalBytes, doneFiles.get().toInt(), files.size)

                for (chunk in files.chunked(64)) {
                    coroutineScope {
                        chunk.map { rf ->
                            async(Dispatchers.IO) {
                                sem.withPermit {
                                    val target = File(modelDir, rf.path)
                                    if (target.isFile && (rf.size <= 0L || target.length() == rf.size)) return@withPermit
                                    downloadOne(rf, target) { delta ->
                                        val now = doneBytes.addAndGet(delta)
                                        publishProgress(now, totalBytes, doneFiles.get().toInt(), files.size)
                                    }
                                    val count = doneFiles.incrementAndGet().toInt()
                                    publishProgress(doneBytes.get(), totalBytes, count, files.size)
                                }
                            }
                        }.awaitAll()
                    }
                }

                require(isReadyOnDisk()) { "모델 다운로드가 완료됐지만 필수 파일 검증에 실패했습니다." }
                _state.value = State.Ready
                true
            }.getOrElse { e ->
                Log.e(TAG, "local image model install failed", e)
                _state.value = State.Failed(e.message ?: e.javaClass.simpleName)
                false
            }
        }
    }

    fun clear() {
        runCatching { File(ctx.filesDir, "image_generator").deleteRecursively() }
        _state.value = State.Missing
    }

    private fun isReadyOnDisk(): Boolean {
        val manifest = File(modelDir, "manifest.json")
        val vocab = File(modelDir, "bpe_simple_vocab_16e6.txt")
        if (!manifest.isFile || !vocab.isFile) return false
        val files = modelDir.listFiles()?.size ?: return false
        if (files < 500) return false
        val bytes = runCatching { modelDir.walkTopDown().filter { it.isFile }.sumOf { it.length() } }.getOrDefault(0L)
        return bytes >= MIN_VALID_BYTES
    }

    private fun fetchFileList(): List<RemoteFile> {
        val req = Request.Builder().url(HF_API).get().build()
        http.newCall(req).execute().use { resp ->
            val body = resp.body?.string().orEmpty()
            if (!resp.isSuccessful) error("모델 파일 목록 조회 실패 HTTP ${resp.code}")
            val root = json.parseToJsonElement(body).jsonObject
            return root["siblings"]?.jsonArray.orEmpty().mapNotNull { el ->
                val o = el.jsonObject
                val name = o["rfilename"]?.jsonPrimitive?.contentOrNull ?: return@mapNotNull null
                if (name == "README.md" || name == ".gitattributes" || name.startsWith(".")) return@mapNotNull null
                val lfsSize = runCatching { o["lfs"]?.jsonObject?.get("size")?.jsonPrimitive?.longOrNull }.getOrNull()
                val directSize = o["size"]?.jsonPrimitive?.longOrNull
                RemoteFile(name, lfsSize ?: directSize ?: 0L)
            }
        }
    }

    private fun downloadOne(rf: RemoteFile, target: File, onBytes: (Long) -> Unit) {
        target.parentFile?.mkdirs()
        val part = File(target.absolutePath + ".part")
        val existing = part.takeIf { it.exists() }?.length() ?: 0L
        val encoded = rf.path.split('/').joinToString("/") {
            URLEncoder.encode(it, "UTF-8").replace("+", "%20")
        }
        val rb = Request.Builder().url("$HF_RESOLVE/$encoded?download=true").get()
        if (existing > 0L) rb.header("Range", "bytes=$existing-")
        http.newCall(rb.build()).execute().use { resp ->
            if (!resp.isSuccessful) error("${rf.path} 다운로드 실패 HTTP ${resp.code}")
            val append = existing > 0L && resp.code == 206
            if (!append && existing > 0L) part.delete()
            val body = resp.body ?: error("${rf.path} 응답이 비어 있습니다")
            part.outputStream().buffered(256 * 1024).use { out0 ->
                val out = if (append) java.io.FileOutputStream(part, true).buffered(256 * 1024) else out0
                if (append) {
                    // out0 was opened/truncated by outputStream(); reopen correctly before writing.
                    runCatching { out0.close() }
                }
                out.use { dst ->
                    body.byteStream().use { src ->
                        val buf = ByteArray(256 * 1024)
                        while (true) {
                            val n = src.read(buf)
                            if (n <= 0) break
                            dst.write(buf, 0, n)
                            onBytes(n.toLong())
                        }
                    }
                }
            }
        }
        if (rf.size > 0L && part.length() != rf.size) {
            error("${rf.path} 크기 불일치 (${part.length()}/${rf.size})")
        }
        if (target.exists()) target.delete()
        if (!part.renameTo(target)) {
            part.copyTo(target, overwrite = true)
            part.delete()
        }
    }

    private fun publishProgress(done: Long, total: Long, doneFiles: Int, totalFiles: Int) {
        val pct = if (total > 0L) ((done * 100L) / total).toInt().coerceIn(0, 100)
        else ((doneFiles * 100) / totalFiles.coerceAtLeast(1)).coerceIn(0, 100)
        _state.value = State.Downloading(pct, doneFiles, totalFiles)
    }

    companion object {
        private const val TAG = "Mythara/LocalImageModel"
        private const val REPO = "cutie26/sd-v1-5-mediapipe-image-generator"
        private const val HF_API = "https://huggingface.co/api/models/$REPO?blobs=true"
        private const val HF_RESOLVE = "https://huggingface.co/$REPO/resolve/main"
        private const val MAX_PARALLEL = 8
        private const val MIN_VALID_BYTES = 1_500_000_000L
        private const val MIN_FREE_BYTES = 3_000_000_000L
    }
}
''')

# -----------------------------------------------------------------------------
# Local MediaPipe Stable Diffusion runtime.
# -----------------------------------------------------------------------------
(qdir / 'LocalImageRuntime.kt').write_text(r'''package com.mythara.local

import android.content.Context
import android.graphics.Bitmap
import android.util.Log
import com.google.mediapipe.framework.image.BitmapExtractor
import com.google.mediapipe.tasks.vision.imagegenerator.ImageGenerator
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream
import java.util.UUID
import javax.inject.Inject
import javax.inject.Singleton
import kotlin.random.Random

@Singleton
class LocalImageRuntime @Inject constructor(
    @ApplicationContext private val ctx: Context,
    private val store: LocalImageModelStore,
) {
    private val lock = Mutex()
    @Volatile private var generator: ImageGenerator? = null

    suspend fun generate(prompt: String, iterations: Int = 12): Result<File> = withContext(Dispatchers.IO) {
        runCatching {
            require(prompt.isNotBlank()) { "이미지 설명이 비어 있습니다." }
            require(store.ensureReady(autoInstall = true)) {
                val state = store.state.value
                val detail = (state as? LocalImageModelStore.State.Failed)?.message
                detail ?: "로컬 이미지 모델을 설치할 수 없습니다."
            }
            lock.withLock {
                val gen = generator ?: createGenerator().also { generator = it }
                val seed = Random.nextInt(1, Int.MAX_VALUE)
                val result = gen.generate(prompt, iterations.coerceIn(4, 30), seed)
                val bitmap = BitmapExtractor.extract(result.generatedImage())
                save(bitmap)
            }
        }.onFailure { Log.e(TAG, "MediaPipe image generation failed", it) }
    }

    fun unload() {
        runCatching { generator?.close() }
        generator = null
    }

    private fun createGenerator(): ImageGenerator {
        val options = ImageGenerator.ImageGeneratorOptions.builder()
            .setImageGeneratorModelDirectory(store.modelDir.absolutePath)
            .build()
        return ImageGenerator.createFromOptions(ctx, options)
    }

    private fun save(bitmap: Bitmap): File {
        val dir = File(ctx.filesDir, "canvas/images").apply { mkdirs() }
        val out = File(dir, "local_${UUID.randomUUID()}.png")
        FileOutputStream(out).use { fos ->
            if (!bitmap.compress(Bitmap.CompressFormat.PNG, 100, fos)) error("PNG 저장 실패")
        }
        return out
    }

    companion object { private const val TAG = "Mythara/LocalImage" }
}
''')

# -----------------------------------------------------------------------------
# Settings VM + panel.
# -----------------------------------------------------------------------------
(qdir / 'LocalImageSetupViewModel.kt').write_text(r'''package com.mythara.local

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class LocalImageSetupViewModel @Inject constructor(
    private val store: LocalImageModelStore,
    private val runtime: LocalImageRuntime,
) : ViewModel() {
    val state: StateFlow<LocalImageModelStore.State> = store.state
    init { store.refresh() }
    fun install() { viewModelScope.launch { store.install() } }
    fun clear() { runtime.unload(); store.clear() }
}
''')

Path('app/src/main/kotlin/com/mythara/ui/settings/LocalImagePanel.kt').write_text(r'''package com.mythara.ui.settings

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
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.mythara.local.LocalImageModelStore
import com.mythara.local.LocalImageSetupViewModel
import com.mythara.ui.theme.MytharaColors

@Composable
fun LocalImagePanel(vm: LocalImageSetupViewModel = hiltViewModel()) {
    val state by vm.state.collectAsState()
    Column(Modifier.fillMaxWidth().border(1.dp, MytharaColors.SurfaceHigh, RoundedCornerShape(14.dp)).padding(14.dp)) {
        Text("로컬 이미지 생성 · Stable Diffusion 1.5", style = MaterialTheme.typography.titleMedium, color = MytharaColors.Fg)
        Text("Gemini API 키 없이 Fold7에서 MediaPipe/OpenCL GPU로 이미지를 생성합니다.", style = MaterialTheme.typography.bodySmall, color = MytharaColors.FgDim)
        Spacer(Modifier.height(8.dp))
        Text(when (val s = state) {
            LocalImageModelStore.State.Missing -> "상태: 모델 미설치 · 최초 1회 약 2.1GB 다운로드"
            LocalImageModelStore.State.Listing -> "상태: 모델 파일 목록 확인 중…"
            is LocalImageModelStore.State.Downloading -> "상태: 다운로드 ${s.percent}% · ${s.doneFiles}/${s.totalFiles} 파일"
            LocalImageModelStore.State.Ready -> "상태: 준비됨 · 로컬 이미지 생성 사용 가능"
            is LocalImageModelStore.State.Failed -> "상태: 실패 · ${s.message}"
        }, color = MytharaColors.Fg)
        Spacer(Modifier.height(8.dp))
        Row {
            when (state) {
                LocalImageModelStore.State.Missing, is LocalImageModelStore.State.Failed -> Button(onClick = vm::install) { Text("로컬 이미지 모델 설치") }
                LocalImageModelStore.State.Ready -> Button(onClick = vm::clear) { Text("모델 삭제") }
                else -> Unit
            }
        }
        Spacer(Modifier.height(6.dp))
        Text("이미지 요청 시 모델이 없으면 자동 설치도 시도합니다. 모델은 CreativeML OpenRAIL-M 기반 공개 변환본이며 APK에는 포함되지 않습니다. Gemini는 키가 설정된 경우에만 선택적 폴백으로 사용합니다.", style = MaterialTheme.typography.bodySmall, color = MytharaColors.FgDim)
    }
}
''')

# Insert panel between Qwen and ACE-Step.
p = Path('app/src/main/kotlin/com/mythara/ui/settings/SettingsScreen.kt')
s = p.read_text()
anchor = '        QwenAccelerationPanel()\n\n        Spacer(Modifier.height(16.dp))\n        AceStepPanel()'
if anchor not in s:
    raise SystemExit('v9 SettingsScreen insertion anchor not found')
s = s.replace(
    anchor,
    '        QwenAccelerationPanel()\n\n        Spacer(Modifier.height(16.dp))\n        LocalImagePanel()\n\n        Spacer(Modifier.height(16.dp))\n        AceStepPanel()',
    1,
)
p.write_text(s)

# -----------------------------------------------------------------------------
# Replace Gemini-only GenerateImageTool with local-first + optional Gemini fallback.
# -----------------------------------------------------------------------------
Path('app/src/main/kotlin/com/mythara/agent/tools/GenerateImageTool.kt').write_text(r'''package com.mythara.agent.tools

import android.content.Context
import android.util.Base64
import com.mythara.agent.Tool
import com.mythara.agent.ToolResult
import com.mythara.data.settings.SettingsStore
import com.mythara.local.LocalImageRuntime
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.File
import java.util.UUID
import java.util.concurrent.TimeUnit
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class GenerateImageTool @Inject constructor(
    @ApplicationContext private val context: Context,
    private val settings: SettingsStore,
    private val local: LocalImageRuntime,
) : Tool {
    override val name = "generate_image"
    override val description = "Generate an image locally on-device with Stable Diffusion 1.5. Gemini is optional fallback only."
    override val parameters: JsonElement = buildJsonObject {
        put("type", JsonPrimitive("object"))
        put("properties", buildJsonObject {
            put("prompt", buildJsonObject { put("type", JsonPrimitive("string")); put("description", JsonPrimitive("Detailed image description")) })
            put("aspect_ratio", buildJsonObject { put("type", JsonPrimitive("string")); put("description", JsonPrimitive("Optional 1:1, 16:9, 9:16")) })
        })
        put("required", buildJsonArray { add(JsonPrimitive("prompt")) })
    }

    override suspend fun execute(args: JsonObject): ToolResult {
        val prompt = args["prompt"]?.jsonPrimitive?.contentOrNull?.trim().orEmpty()
        if (prompt.isBlank()) return ToolResult.fail("이미지 설명이 필요합니다.")
        val aspect = args["aspect_ratio"]?.jsonPrimitive?.contentOrNull?.trim().orEmpty()
        val localPrompt = if (aspect.isBlank()) prompt else "$prompt, composition optimized for aspect ratio $aspect"

        val localResult = local.generate(localPrompt, iterations = 12)
        localResult.getOrNull()?.let { file ->
            return ToolResult.ok(resultJson(file.absolutePath, "local_sd15_mediapipe"))
        }

        // Optional cloud fallback only when the user already configured Gemini.
        val key = runCatching { settings.geminiApiKey.first() }.getOrNull().orEmpty().trim()
        if (key.isNotBlank()) {
            val cloud = runCatching { generateWithGemini(prompt, key) }
            cloud.getOrNull()?.let { file ->
                return ToolResult.ok(resultJson(file.absolutePath, "gemini_fallback"))
            }
        }

        val reason = localResult.exceptionOrNull()?.message
            ?: "로컬 이미지 생성기를 초기화하지 못했습니다."
        return ToolResult.fail("로컬 이미지 생성 실패: $reason 설정의 '로컬 이미지 생성'에서 모델 상태를 확인해 주세요.")
    }

    private suspend fun generateWithGemini(prompt: String, key: String): File = withContext(Dispatchers.IO) {
        val payload = buildJsonObject {
            put("contents", buildJsonArray {
                add(buildJsonObject {
                    put("parts", buildJsonArray { add(buildJsonObject { put("text", JsonPrimitive(prompt)) }) })
                })
            })
            put("generationConfig", buildJsonObject {
                put("responseModalities", buildJsonArray { add(JsonPrimitive("TEXT")); add(JsonPrimitive("IMAGE")) })
            })
        }.toString()
        val client = OkHttpClient.Builder().connectTimeout(20, TimeUnit.SECONDS).readTimeout(120, TimeUnit.SECONDS).build()
        val request = Request.Builder()
            .url("https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent?key=$key")
            .post(payload.toRequestBody("application/json; charset=utf-8".toMediaType()))
            .build()
        client.newCall(request).execute().use { resp ->
            val text = resp.body?.string().orEmpty()
            if (!resp.isSuccessful) error("Gemini fallback HTTP ${resp.code}")
            val root = Json { ignoreUnknownKeys = true }.parseToJsonElement(text).jsonObject
            val parts = (((root["candidates"] as? JsonArray)?.firstOrNull()?.jsonObject?.get("content")?.jsonObject?.get("parts")) as? JsonArray).orEmpty()
            val inline = parts.firstNotNullOfOrNull { p ->
                runCatching { p.jsonObject["inlineData"]?.jsonObject }.getOrNull()
                    ?: runCatching { p.jsonObject["inline_data"]?.jsonObject }.getOrNull()
            } ?: error("Gemini fallback 이미지가 없습니다")
            val data = inline["data"]?.jsonPrimitive?.contentOrNull ?: error("Gemini fallback 데이터 없음")
            val mime = inline["mimeType"]?.jsonPrimitive?.contentOrNull ?: inline["mime_type"]?.jsonPrimitive?.contentOrNull ?: "image/png"
            val ext = if (mime.contains("jpeg", true) || mime.contains("jpg", true)) "jpg" else "png"
            val dir = File(context.filesDir, "canvas/images").apply { mkdirs() }
            val out = File(dir, "gemini_${UUID.randomUUID()}.$ext")
            out.writeBytes(Base64.decode(data, Base64.DEFAULT))
            out
        }
    }

    private fun resultJson(path: String, backend: String): String = buildJsonObject {
        put("path", JsonPrimitive(path))
        put("backend", JsonPrimitive(backend))
        put("status", JsonPrimitive("generated"))
    }.toString()
}
''')

# Capability copy: no longer claim a Gemini key is required.
p = Path('app/src/main/kotlin/com/mythara/local/LocalGemmaChat.kt')
s = p.read_text()
s = s.replace(
    'parts += "이미지 생성(Gemini API 키가 설정되어 있을 때)"',
    'parts += "이미지 생성(로컬 Stable Diffusion 1.5 · Gemini는 선택적 폴백)"',
)
s = s.replace(
    '이미지 생성은 로컬 Gemma가 아니라 Gemini 이미지 API를 사용하므로 해당 기능만 인터넷과 Gemini API 키가 필요해.',
    '이미지 생성은 로컬 Stable Diffusion 1.5를 우선 사용하므로 Gemini API 키가 없어도 가능해. 최초 1회 로컬 이미지 모델 설치가 필요해.',
)
s = s.replace(
    '이미지 생성은 Gemini API 키가 필요해.',
    '이미지 생성은 로컬 Stable Diffusion을 우선 사용해. Gemini API 키는 선택 사항이야.',
)
p.write_text(s)

print('Mythara Fold7 KR FCC v9 local image patch applied')
