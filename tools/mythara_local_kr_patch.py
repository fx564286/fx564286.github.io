from pathlib import Path

# Korean UI overlay for the pinned Mythara Local Fold7 build.
# Run AFTER tools/mythara_local_patch.py inside the cloned upstream repo.


def replace_in(path, pairs):
    p = Path(path)
    if not p.exists():
        return
    s = p.read_text()
    for old, new in pairs:
        s = s.replace(old, new)
    p.write_text(s)

# Install side-by-side with the previous English local build.
replace_in('app/build.gradle.kts', [
    ('applicationIdSuffix = ".local"', 'applicationIdSuffix = ".localkr"'),
    ('versionNameSuffix = "-local-fold7"', 'versionNameSuffix = "-local-fold7-kr"'),
])

# Visible app name.
replace_in('app/src/main/res/values/strings.xml', [
    ('<string name="app_name">Mythara Local</string>', '<string name="app_name">Mythara 로컬</string>'),
    ('<string name="app_name">Mythara</string>', '<string name="app_name">Mythara 로컬</string>'),
])

# Main local-agent errors + language preference. Keep tool-routing markers in English
# because LocalGemmaChat parses them programmatically.
replace_in('app/src/main/kotlin/com/mythara/local/LocalGemmaChat.kt', [
    ('"Local Gemma model is not installed. Download Gemma 4 E2B in onboarding or Secret settings."',
     '"로컬 Gemma 4 E2B 모델이 설치되지 않았습니다. 설정의 로컬 AI 메뉴에서 모델을 설치해 주세요."'),
    ('"Local Gemma inference failed."', '"로컬 Gemma 추론에 실패했습니다."'),
    ('"Local model returned an empty answer."', '"로컬 모델이 빈 응답을 반환했습니다."'),
    ('appendLine("You are Mythara, a private Android assistant running entirely on this phone.")',
     'appendLine("You are Mythara, a private Android assistant running entirely on this phone. Always answer in Korean unless the user explicitly asks for another language.")'),
])

replace_in('app/src/main/kotlin/com/mythara/agent/AgentLoop.kt', [
    ('"Local Gemma 4 E2B is not installed yet. Download it in onboarding or Secret settings, then retry."',
     '"로컬 Gemma 4 E2B가 아직 설치되지 않았습니다. Secret 설정에서 모델을 설치한 뒤 다시 시도해 주세요."'),
])

# Right-side launcher/menu.
replace_in('app/src/main/kotlin/com/mythara/ui/system/MytharaSpine.kt', [
    ('LauncherEntry("apps",', 'LauncherEntry("앱",'),
    ('LauncherEntry("me",', 'LauncherEntry("나",'),
    ('LauncherEntry("people",', 'LauncherEntry("사람들",'),
    ('LauncherEntry("memory",', 'LauncherEntry("메모리",'),
    ('LauncherEntry("tasks",', 'LauncherEntry("작업",'),
    ('LauncherEntry("alerts",', 'LauncherEntry("알림",'),
    ('LauncherEntry("calls",', 'LauncherEntry("통화",'),
    ('LauncherEntry("usage",', 'LauncherEntry("사용량",'),
    ('LauncherEntry("settings",', 'LauncherEntry("설정",'),
    ('LauncherEntry("triage",', 'LauncherEntry("자동 분류",'),
])

# About page + hidden-secret entry remains the same triple-tap gesture.
replace_in('app/src/main/kotlin/com/mythara/ui/about/AboutScreen.kt', [
    ('Panel("version")', 'Panel("버전")'),
    ('Panel("privacy")', 'Panel("개인정보 보호")'),
    ('Panel("created by")', 'Panel("제작")'),
    ('Panel("credits")', 'Panel("오픈소스 / 구성요소")'),
    ('"field intelligence in your pocket."', '"내 손안의 로컬 AI 어시스턴트."'),
    ('"Mythara has no backend, no telemetry, no analytics. The only network calls are to the MiniMax endpoint you configured and (if enabled) your GitHub memory repo."',
     '"Mythara는 별도 백엔드·텔레메트리·분석 서버를 사용하지 않습니다. 이 로컬판의 메인 AI 추론은 기기 안에서 실행됩니다."'),
    ('"API keys and the device-secret password stay on the phone, encrypted at rest. Chat history, learnings, and non-secret settings can sync to a private GitHub repo you control."',
     '"비밀번호와 민감한 설정은 휴대폰에 저장됩니다. 선택한 경우에만 메모리 데이터를 사용자가 관리하는 GitHub 저장소와 동기화할 수 있습니다."'),
    ('"Mythara is your personal field intelligence agent."', '"Mythara는 개인용 로컬 AI 에이전트입니다."'),
])

# Settings top-level panels and common controls. We intentionally leave API/model names
# (MiniMax, Gemini, Shizuku, LiteRT-LM, Supertonic) as product names.
replace_in('app/src/main/kotlin/com/mythara/ui/settings/SettingsScreen.kt', [
    ('Panel("region")', 'Panel("지역")'),
    ('Panel("api key")', 'Panel("API 키")'),
    ('Panel("model")', 'Panel("모델")'),
    ('Panel("on-device voice (supertonic-2)")', 'Panel("온디바이스 음성 (Supertonic-2)")'),
    ('"save & validate"', '"저장 및 확인"'),
    ('"test voice"', '"음성 테스트"'),
    ('"remove (~270 MB)"', '"삭제 (~270MB)"'),
    ('"re-open assistant settings"', '"어시스턴트 설정 다시 열기"'),
    ('"re-open accessibility settings"', '"접근성 설정 다시 열기"'),
    ('"active — Mythara is your default assistant"', '"활성 — Mythara가 기본 어시스턴트입니다"'),
    ('"active — read_screen tool is live"', '"활성 — 화면 읽기 도구를 사용할 수 있습니다"'),
])

# Secret settings — translate the parts that matter for local AI setup plus the common
# panels the user sees while scrolling to it.
replace_in('app/src/main/kotlin/com/mythara/ui/secret/SecretSettingsScreen.kt', [
    ('Panel("status")', 'Panel("상태")'),
    ('Panel("notes")', 'Panel("메모")'),
    ('Panel("unlock method")', 'Panel("잠금 해제 방식")'),
    ('Panel("permissions")', 'Panel("권한")'),
    ('Panel("controls")', 'Panel("제어")'),
    ('Panel("speech model (Vosk en-us, ~40MB)")', 'Panel("음성 인식 모델 (Vosk en-us, ~40MB)")'),
    ('Panel("embeddings (Universal Sentence Encoder, ~6MB)")', 'Panel("임베딩 (Universal Sentence Encoder, ~6MB)")'),
    ('Panel("speaker model (Vosk x-vector, ~13MB)")', 'Panel("화자 모델 (Vosk x-vector, ~13MB)")'),
    ('Panel("speakers")', 'Panel("등록된 화자")'),
    ('Panel("extractor model (Gemma 4 E2B via LiteRT-LM, ~2.6GB)")', 'Panel("로컬 AI 모델 (Gemma 4 E2B / LiteRT-LM, ~2.6GB)")'),
    ('Panel("episodic promotion (Gemma)")', 'Panel("에피소드 메모리 생성 (Gemma)")'),
    ('Panel("learning vault (durable)")', 'Panel("학습 메모리 저장소")'),
    ('Panel("recent transcripts (this device only)")', 'Panel("최근 기록 (이 기기에만 저장)")'),
    ('"not downloaded — required for transcription."', '"설치되지 않음 — 음성 인식에 필요합니다."'),
    ('"download model (40MB)"', '"모델 다운로드 (40MB)"'),
    ('"download embedder (6MB)"', '"임베더 다운로드 (6MB)"'),
    ('"download speaker model (13MB)"', '"화자 모델 다운로드 (13MB)"'),
    ('"no speakers enrolled yet."', '"등록된 화자가 없습니다."'),
    ('"enrol a speaker"', '"화자 등록"'),
    ('"not loaded. semantic extraction falls back to a regex heuristic until Gemma is available."',
     '"설치되지 않았습니다. Gemma를 설치할 때까지 간단한 규칙 기반 처리만 사용합니다."'),
    ('"download (2.6GB)"', '"로컬 AI 다운로드 (2.6GB)"'),
    ('"import .litertlm"', '".litertlm 파일 가져오기"'),
    ('"clear cache"', '"캐시 삭제"'),
    ('"retry"', '"다시 시도"'),
    ('"Gemma 4 E2B on disk — extraction stays on heuristic until you probe init successfully."',
     '"Gemma 4 E2B 설치 완료 — 초기화 테스트를 통과하면 로컬 AI를 사용할 수 있습니다."'),
    ('"not tested yet"', '"아직 테스트하지 않음"'),
    ('"running init probe…"', '"초기화 테스트 중…"'),
    ('"probe Gemma init"', '"Gemma 초기화 테스트"'),
    ('"Gemma extraction is DISABLED — Observe uses heuristic only"', '"Gemma 비활성 — 현재 규칙 기반 처리만 사용"'),
    ('"disable"', '"비활성화"'),
    ('"promote now"', '"지금 실행"'),
])

# Notes screen, useful for everyday use.
replace_in('app/src/main/kotlin/com/mythara/ui/notes/NotesScreen.kt', [
    ('Panel("capture")', 'Panel("내용")'),
    ('Panel("file it as")', 'Panel("저장 위치")'),
])

# Meta panel in Local build.
replace_in('app/src/main/kotlin/com/mythara/ui/settings/GlassesPanel.kt', [
    ('"Meta glasses integration is disabled in Mythara Local Fold7."', '"Mythara 로컬 Fold7 빌드에서는 Meta 안경 연동이 비활성화되어 있습니다."'),
    ('"Shizuku, phone control and local AI remain enabled."', '"Shizuku, 휴대폰 제어, 로컬 AI 기능은 그대로 사용할 수 있습니다."'),
])

print('Mythara Local Fold7 Korean overlay applied')
