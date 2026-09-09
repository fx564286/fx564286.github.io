from pathlib import Path

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
print('Mythara v9 image downloader compile/runtime fix applied')
