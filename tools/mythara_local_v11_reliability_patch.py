from pathlib import Path

# Mythara Local Fold7 KR FCC v11 reliability hotfix
# - update Qualcomm GenieX Android runtime
# - retry/resume transient model-hub network failures (-100005)
# - make the Stable Diffusion 1041-file downloader conservative and resumable
# - stop ACE-Step from automatically LAN-scanning as soon as Settings opens
# - make ACE-Step UI explicit that an external :8001 server is required

# -----------------------------------------------------------------------------
# Version + newer GenieX Android SDK.
# -----------------------------------------------------------------------------
p = Path('app/build.gradle.kts')
s = p.read_text()
s = s.replace('versionNameSuffix = "-local-fold7-kr-v10"', 'versionNameSuffix = "-local-fold7-kr-v11"')
s = s.replace('versionCode = 10', 'versionCode = 11', 1)
s = s.replace('implementation("com.qualcomm.qti:geniex-android:0.3.5")', 'implementation("com.qualcomm.qti:geniex-android:0.3.12")')
p.write_text(s)

# -----------------------------------------------------------------------------
# Qwen / GenieX model pulls: keep partial caches and retry transient network
# failures. -100005 is GENIEX_ERROR_COMMON_NETWORK.
# -----------------------------------------------------------------------------
p = Path('app/src/main/kotlin/com/mythara/local/QwenNpuRuntime.kt')
s = p.read_text()
if 'import kotlinx.coroutines.delay\n' not in s:
    s = s.replace('import kotlinx.coroutines.Dispatchers\n', 'import kotlinx.coroutines.Dispatchers\nimport kotlinx.coroutines.delay\n', 1)

start = s.find('    private suspend fun downloadModel(')
end = s.find('    private fun applyTemplate(', start)
if start < 0 or end < 0:
    raise SystemExit('v11 Qwen downloadModel anchors not found')

new_download = r'''    private suspend fun downloadModel(
        modelName: String,
        precision: String?,
        hub: HubSource,
        chipset: String?,
        stateFlow: MutableStateFlow<State>,
    ): Boolean = withContext(Dispatchers.IO) {
        ensureSdk()
        if (ModelManagerWrapper.getPaths(modelName) != null) {
            stateFlow.value = State.Downloaded
            return@withContext true
        }

        var lastError = "모델 다운로드가 완료되지 않았습니다."
        for (attempt in 1..MODEL_PULL_ATTEMPTS) {
            var completed = false
            var transientNetworkError = false
            try {
                stateFlow.value = State.Downloading(0)
                val input = ModelPullInput(
                    model_name = modelName,
                    precision = precision,
                    hub = hub,
                    chipset = chipset,
                    display_name = null,
                )
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
                        is ModelManagerWrapper.PullEvent.Error -> {
                            val code = event.code.toString()
                            val msg = event.message.orEmpty()
                            lastError = "모델 다운로드 실패 ($code): $msg"
                            val lower = msg.lowercase()
                            transientNetworkError = code == "-100005" ||
                                lower.contains("network") || lower.contains("timeout") ||
                                lower.contains("connection reset") || lower.contains("temporarily")
                            throw IllegalStateException(lastError)
                        }
                    }
                }
                if (completed || ModelManagerWrapper.getPaths(modelName) != null) {
                    stateFlow.value = State.Downloaded
                    return@withContext true
                }
            } catch (e: Throwable) {
                if (lastError.startsWith("모델 다운로드가 완료되지")) {
                    lastError = e.message ?: e.javaClass.simpleName
                }
                val lower = lastError.lowercase()
                val shouldRetry = transientNetworkError || lower.contains("-100005") ||
                    lower.contains("network") || lower.contains("timeout") ||
                    lower.contains("connection reset")
                if (!shouldRetry || attempt >= MODEL_PULL_ATTEMPTS) break

                // GenieX ModelManager keeps its partial cache. Do not clean it here:
                // a fresh pull can resume/reconcile the existing model files.
                val backoff = (attempt * 2_000L).coerceAtMost(10_000L)
                stateFlow.value = State.Downloading(0)
                delay(backoff)
            }
        }

        Log.e(TAG, "download failed for $modelName after retries: $lastError")
        stateFlow.value = State.Failed("$lastError · 네트워크가 안정되면 다시 누르면 이어서 시도합니다.")
        false
    }

'''
s = s[:start] + new_download + s[end:]

# Add retry constant without disturbing existing public constants.
if 'MODEL_PULL_ATTEMPTS' not in s[s.find('companion object'):]:
    s = s.replace(
        '        private const val KEY_CREATIVE_MODE = "creative_mode"\n',
        '        private const val KEY_CREATIVE_MODE = "creative_mode"\n        private const val MODEL_PULL_ATTEMPTS = 5\n',
        1,
    )
p.write_text(s)

# Make the Settings copy explain the actual error class instead of looking like
# an NPU incompatibility when the model hub connection failed.
p = Path('app/src/main/kotlin/com/mythara/ui/settings/QwenAccelerationPanel.kt')
s = p.read_text()
s = s.replace(
    'Galaxy Z Fold7 / SM8750 · Hexagon NPU 자동 선택',
    'Galaxy Z Fold7 / SM8750 · Hexagon NPU 자동 선택 · 네트워크 실패 시 최대 5회 재시도',
)
p.write_text(s)

# -----------------------------------------------------------------------------
# Stable Diffusion model store: fewer simultaneous HF connections plus robust
# per-file retries and HTTP Range resume. The repo has ~1041 files; 8 concurrent
# downloads was unnecessarily aggressive on a phone and made CDN resets fatal.
# -----------------------------------------------------------------------------
p = Path('app/src/main/kotlin/com/mythara/local/LocalImageModelStore.kt')
s = p.read_text()

s = s.replace(
    '''    private val http = OkHttpClient.Builder()\n        .connectTimeout(20, TimeUnit.SECONDS)\n        .readTimeout(10, TimeUnit.MINUTES)\n        .writeTimeout(60, TimeUnit.SECONDS)\n        .followRedirects(true)\n        .followSslRedirects(true)\n        .build()''',
    '''    private val http = OkHttpClient.Builder()\n        .connectTimeout(30, TimeUnit.SECONDS)\n        .readTimeout(10, TimeUnit.MINUTES)\n        .writeTimeout(60, TimeUnit.SECONDS)\n        .retryOnConnectionFailure(true)\n        .followRedirects(true)\n        .followSslRedirects(true)\n        .build()''',
    1,
)
s = s.replace('private const val MAX_PARALLEL = 8', 'private const val MAX_PARALLEL = 2')

# Replace fetchFileList with a retrying implementation.
start = s.find('    private fun fetchFileList(): List<RemoteFile> {')
end = s.find('    private fun downloadOne(', start)
if start < 0 or end < 0:
    raise SystemExit('v11 image fetchFileList anchors not found')
new_list = r'''    private fun fetchFileList(): List<RemoteFile> {
        var last: Throwable? = null
        for (attempt in 1..LIST_ATTEMPTS) {
            try {
                val req = Request.Builder()
                    .url(HF_API)
                    .header("User-Agent", "Mythara-Fold7-v11")
                    .get()
                    .build()
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
            } catch (e: Throwable) {
                last = e
                Log.w(TAG, "file-list attempt $attempt/$LIST_ATTEMPTS failed: ${e.message}")
                if (attempt < LIST_ATTEMPTS) Thread.sleep((attempt * 1_500L).coerceAtMost(6_000L))
            }
        }
        throw last ?: IllegalStateException("모델 파일 목록을 가져올 수 없습니다.")
    }

'''
s = s[:start] + new_list + s[end:]

# Replace per-file download with retry + range resume.
start = s.find('    private fun downloadOne(')
end = s.find('    private fun publishProgress(', start)
if start < 0 or end < 0:
    raise SystemExit('v11 image downloadOne anchors not found')
new_one = r'''    private fun downloadOne(rf: RemoteFile, target: File, onBytes: (Long) -> Unit) {
        target.parentFile?.mkdirs()
        val part = File(target.absolutePath + ".part")
        var last: Throwable? = null

        for (attempt in 1..FILE_ATTEMPTS) {
            try {
                if (rf.size > 0L && part.exists() && part.length() > rf.size) part.delete()
                if (rf.size > 0L && part.isFile && part.length() == rf.size) {
                    if (target.exists()) target.delete()
                    if (!part.renameTo(target)) {
                        part.copyTo(target, overwrite = true)
                        part.delete()
                    }
                    return
                }

                val existing = part.takeIf { it.exists() }?.length() ?: 0L
                val encoded = rf.path.split('/').joinToString("/") {
                    URLEncoder.encode(it, "UTF-8").replace("+", "%20")
                }
                val rb = Request.Builder()
                    .url("$HF_RESOLVE/$encoded?download=true")
                    .header("User-Agent", "Mythara-Fold7-v11")
                    .header("Accept-Encoding", "identity")
                    .get()
                if (existing > 0L) rb.header("Range", "bytes=$existing-")

                http.newCall(rb.build()).execute().use { resp ->
                    if (resp.code == 416 && rf.size > 0L && part.length() == rf.size) {
                        // CDN says the requested range is already complete.
                    } else {
                        if (!resp.isSuccessful) error("${rf.path} 다운로드 실패 HTTP ${resp.code}")
                        val append = existing > 0L && resp.code == 206
                        if (!append && existing > 0L) part.delete()
                        val body = resp.body ?: error("${rf.path} 응답이 비어 있습니다")
                        java.io.FileOutputStream(part, append).buffered(256 * 1024).use { dst ->
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
                return
            } catch (e: Throwable) {
                last = e
                Log.w(TAG, "${rf.path} attempt $attempt/$FILE_ATTEMPTS failed: ${e.message}")
                if (attempt < FILE_ATTEMPTS) {
                    Thread.sleep((attempt * attempt * 1_000L).coerceAtMost(15_000L))
                }
            }
        }
        throw last ?: IllegalStateException("${rf.path} 다운로드 실패")
    }

'''
s = s[:start] + new_one + s[end:]

# Add constants.
if 'LIST_ATTEMPTS' not in s[s.find('companion object'):]:
    s = s.replace(
        '        private const val MAX_PARALLEL = 2\n',
        '        private const val MAX_PARALLEL = 2\n        private const val LIST_ATTEMPTS = 4\n        private const val FILE_ATTEMPTS = 6\n',
        1,
    )
p.write_text(s)

# -----------------------------------------------------------------------------
# ACE-Step: this feature is a client for an ACE-Step API server, not an Android
# inference runtime. Do not hammer the LAN when Settings merely opens, and make
# that dependency explicit in the UI.
# -----------------------------------------------------------------------------
p = Path('app/src/main/kotlin/com/mythara/local/MusicSetupViewModel.kt')
s = p.read_text()
s = s.replace(
    'private val _testResult = MutableStateFlow("자동 연결 대기")',
    'private val _testResult = MutableStateFlow("서버 대기 · PC/Termux에서 ACE-Step API :8001 실행 후 ‘서버 찾기’를 누르세요.")',
)
s = s.replace('\n    init { autoDiscover() }\n', '\n')
p.write_text(s)

p = Path('app/src/main/kotlin/com/mythara/local/AceStepClient.kt')
s = p.read_text()
s = s.replace('val sem = Semaphore(48)', 'val sem = Semaphore(8)')
s = s.replace('for (chunk in candidates.chunked(96))', 'for (chunk in candidates.chunked(32))')
s = s.replace('for (prefix in prefixes.take(5))', 'for (prefix in prefixes.take(2))')
s = s.replace(
    'false to "ACE-Step :8001 서버를 자동으로 찾지 못했습니다."',
    'false to "ACE-Step :8001 서버가 실행 중인 기기를 찾지 못했습니다. 이 기능은 외부/LAN ACE-Step 서버가 필요합니다."',
)
p.write_text(s)

p = Path('app/src/main/kotlin/com/mythara/ui/settings/AceStepPanel.kt')
s = p.read_text()
s = s.replace('ACE-Step 1.5 · 자동 노래 생성', 'ACE-Step 1.5 · LAN/PC 노래 생성')
s = s.replace(
    '기존 CLI처럼 acestep-v15-turbo를 사용하고 :8001 런타임을 자동으로 찾아 연결합니다. 주소 입력은 보통 필요 없습니다.',
    '중요: ACE-Step 본체는 이 APK 안에서 실행되지 않습니다. PC 또는 Termux에서 ACE-Step API(:8001)를 먼저 실행한 뒤 같은 네트워크에서 연결합니다.',
)
s = s.replace('Text("자동 검색")', 'Text("서버 찾기")')
s = s.replace('Text(if (thinking) "5Hz LM: 켜짐" else "5Hz LM: 꺼짐")', 'Text(if (thinking) "서버 5Hz LM: 켜짐" else "서버 5Hz LM: 꺼짐")')
s = s.replace('고급 설정 · 자동 검색이 안 될 때만 사용', '고급 설정 · 서버 주소를 직접 알고 있을 때 사용')
s = s.replace('placeholder = { Text("비워두면 자동 검색") }', 'placeholder = { Text("예: http://192.168.0.10:8001") }')
p.write_text(s)

print('Mythara Fold7 KR FCC v11 reliability patch applied')
