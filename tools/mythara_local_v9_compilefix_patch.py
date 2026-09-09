from pathlib import Path

# 1) Local image model downloader resume writer.
p = Path('app/src/main/kotlin/com/mythara/local/LocalImageModelStore.kt')
s = p.read_text()
old = '''            val body = resp.body ?: error("${rf.path} 응답이 비어 있습니다")
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
            }'''
new = '''            val body = resp.body ?: error("${rf.path} 응답이 비어 있습니다")
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
            }'''
if old not in s:
    raise SystemExit('v9 resume writer anchor not found')
s = s.replace(old, new, 1)
p.write_text(s)

# 2) GenerateImageTool uses the upstream SettingsStore package/API.
p = Path('app/src/main/kotlin/com/mythara/agent/tools/GenerateImageTool.kt')
s = p.read_text()
s = s.replace('import com.mythara.data.settings.SettingsStore', 'import com.mythara.data.SettingsStore')
s = s.replace('settings.geminiApiKey.first()', 'settings.geminiKeyFlow().first()')
p.write_text(s)

print('Mythara v9 image generation compile/runtime fixes applied')
