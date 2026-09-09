from pathlib import Path

# Mythara Local Fold7 KR v4 — expanded Korean UI overlay.
# Applied after the existing Korean overlay. Only explicit visible Compose
# strings are replaced; navigation routes, enum values and protocol payloads
# are intentionally left untouched.

ROOT = Path('app/src/main/kotlin/com/mythara')


def replace_in(rel, pairs):
    p = ROOT / rel
    if not p.exists():
        print(f'[skip] {rel}')
        return
    s = p.read_text()
    before = s
    for old, new in pairs:
        s = s.replace(old, new)
    if s != before:
        p.write_text(s)
        print(f'[ko] {rel}')

replace_in('ui/secret/SecretUnlock.kt', [
    ('"set a secret password"', '"Secret 비밀번호 설정"'),
    ('"biometric unlock"', '"생체 인증으로 잠금 해제"'),
    ('"secret mode"', '"Secret 모드"'),
    ('"this is the password for Observe controls (later: continuous learning + memory tools). keep it different from your device PIN. minimum 6 characters."',
     '"Observe 제어와 메모리 기능에 사용할 비밀번호입니다. 휴대폰 PIN과 다른 비밀번호를 사용하세요. 최소 6자입니다."'),
    ('"use face / fingerprint / device pin to continue. tap below to fall back to the secret password."',
     '"얼굴·지문·기기 PIN으로 계속하세요. 아래 버튼을 누르면 Secret 비밀번호 입력 방식으로 전환합니다."'),
    ('"enter your secret password."', '"Secret 비밀번호를 입력하세요."'),
    ('"${Glyph.Arrow} use password instead"', '"${Glyph.Arrow} 비밀번호로 입력"'),
    ('Text("password", color = MytharaColors.FgDim)', 'Text("비밀번호", color = MytharaColors.FgDim)'),
    ('Text("confirm", color = MytharaColors.FgDim)', 'Text("비밀번호 확인", color = MytharaColors.FgDim)'),
    ('"${Glyph.Refresh} prompt again"', '"${Glyph.Refresh} 다시 인증"'),
    ('"${Glyph.Ellipsis} checking"', '"${Glyph.Ellipsis} 확인 중"'),
    ('"${Glyph.Check} set + unlock"', '"${Glyph.Check} 설정하고 열기"'),
    ('"${Glyph.Check} unlock"', '"${Glyph.Check} 잠금 해제"'),
    ('Text("cancel", color = MytharaColors.FgMute)', 'Text("취소", color = MytharaColors.FgMute)'),
])

replace_in('ui/chat/ConfirmationDialog.kt', [
    ('"always allow — stop treating this app as critical"', '"항상 허용 — 이 앱을 중요 앱 목록에서 제외"'),
    ('"always allow this"', '"이 작업 항상 허용"'),
    ('"${Glyph.Cross} deny"', '"${Glyph.Cross} 거부"'),
    ('"${Glyph.Check} allow"', '"${Glyph.Check} 허용"'),
])

replace_in('ui/tasks/TasksScreen.kt', [
    ('"${Glyph.DiamondFilled} tasks"', '"${Glyph.DiamondFilled} 작업"'),
    ('"${pending.size} pending · ${terminal.size} done"', '"대기 ${pending.size}개 · 완료 ${terminal.size}개"'),
    ('"${Glyph.Refresh} sync now"', '"${Glyph.Refresh} 지금 동기화"'),
    ('"${Glyph.DiamondFilled} new"', '"${Glyph.DiamondFilled} 새 작업"'),
    ('"${Glyph.CircleOutline} no tasks yet. Tap ${Glyph.DiamondFilled} new to add one."', '"${Glyph.CircleOutline} 아직 작업이 없습니다. ${Glyph.DiamondFilled} 새 작업을 눌러 추가하세요."'),
    ('"${Glyph.Dot} notification reply queue"', '"${Glyph.Dot} 알림 답장 대기열"'),
    ('"${Glyph.Ellipsis} pending"', '"${Glyph.Ellipsis} 대기 중"'),
    ('"${Glyph.Check} done"', '"${Glyph.Check} 완료"'),
    ('"attempt ${notif.attempts}"', '"시도 ${notif.attempts}회"'),
    ('"${Glyph.Cross} skip (don\'t auto-reply)"', '"${Glyph.Cross} 건너뛰기 (자동 답장 안 함)"'),
    ('"any device"', '"모든 기기"'),
    ('"from this device"', '"이 기기에서 요청"'),
    ('"from ${task.requesterDeviceId.takeLast(6)}"', '"${task.requesterDeviceId.takeLast(6)}에서 요청"'),
    ('"claimed: ${task.claimedByDeviceId.takeLast(6)}"', '"처리 기기: ${task.claimedByDeviceId.takeLast(6)}"'),
    ('"${Glyph.Cross} cancel"', '"${Glyph.Cross} 취소"'),
])

replace_in('ui/settings/ShizukuPanel.kt', [
    ('"${Glyph.DiamondOutline} shizuku — privileged shell shim for cosmetic system changes"',
     '"${Glyph.DiamondOutline} Shizuku — 시스템 설정 변경용 권한 브리지"'),
    ('"${Glyph.Dot} state: ${state.name}"', '"${Glyph.Dot} 상태: ${state.name}"'),
    ('"${Glyph.AccentBar} Install the Shizuku app from Google Play (free, by RikkaW). " +\n                    "Once installed, return here."',
     '"${Glyph.AccentBar} Google Play에서 Shizuku 앱을 설치하세요. 설치한 뒤 이 화면으로 돌아오세요."'),
    ('"${Glyph.AccentBar} Open the Shizuku app and bootstrap it via wireless debugging " +\n                    "(Android 11+) or adb. Wait for the green \'Running\' status, then return here."',
     '"${Glyph.AccentBar} Shizuku 앱을 열고 무선 디버깅(Android 11+) 또는 ADB로 시작하세요. 실행 중 상태가 된 뒤 돌아오세요."'),
    ('"${Glyph.AccentBar} Shizuku is running but Mythara doesn\'t have permission yet. " +\n                        "Tap the button to request it."',
     '"${Glyph.AccentBar} Shizuku는 실행 중이지만 Mythara 권한이 아직 없습니다. 아래 버튼을 눌러 권한을 요청하세요."'),
    ('Text("request permission")', 'Text("권한 요청")'),
    ('"${Glyph.AccentBar} Shizuku ready. Mythara\'s `apply_cosmetic` agent tool can now " +\n                    "tweak font scale, dark mode, accent colour, gesture-nav style, animation speeds, " +\n                    "and the blue-light filter on demand."',
     '"${Glyph.AccentBar} Shizuku 준비 완료. 이제 Mythara가 글자 크기, 다크 모드, 강조색, 제스처 내비게이션, 애니메이션 속도, 블루라이트 필터 등을 변경할 수 있습니다."'),
])

replace_in('ui/settings/MemorySyncPanel.kt', [
    ('PanelLocal("memory sync")', 'PanelLocal("메모리 동기화")'),
    ('"${Glyph.AccentBar} learnings + settings (and optionally chat) sync to your private GitHub repo so they survive device switches. nothing secret leaves the phone."',
     '"${Glyph.AccentBar} 학습 메모리와 설정을 개인 GitHub 저장소에 동기화합니다. 선택하면 채팅 기록도 포함할 수 있습니다. Secret 비밀번호 등 민감 정보는 업로드하지 않습니다."'),
    ('"generate at github.com/settings/tokens · scope: repo"', '"github.com/settings/tokens에서 생성 · 권한 범위: repo"'),
    ('"${Glyph.Ellipsis} validating"', '"${Glyph.Ellipsis} 확인 중"'),
    ('"${Glyph.Check} validate"', '"${Glyph.Check} 확인"'),
    ('label = { Text("owner",', 'label = { Text("소유자",'),
    ('label = { Text("repo",', 'label = { Text("저장소",'),
    ('ToggleRow(label = "sync learnings"', 'ToggleRow(label = "학습 메모리 동기화"'),
    ('ToggleRow(label = "sync settings (region, model, prefs)"', 'ToggleRow(label = "설정 동기화 (지역, 모델, 환경설정)"'),
    ('ToggleRow(label = "sync chat history (sensitive — off by default)"', 'ToggleRow(label = "채팅 기록 동기화 (민감 정보 — 기본 꺼짐)"'),
    ('ToggleRow(label = "enable automatic nightly sync"', 'ToggleRow(label = "매일 밤 자동 동기화"'),
    ('"${Glyph.Ellipsis} syncing"', '"${Glyph.Ellipsis} 동기화 중"'),
    ('"${Glyph.Arrow} sync now"', '"${Glyph.Arrow} 지금 동기화"'),
    ('"${Glyph.Ellipsis} restoring"', '"${Glyph.Ellipsis} 복원 중"'),
    ('"${Glyph.Refresh} restore"', '"${Glyph.Refresh} 복원"'),
    ('text = "restore from repo?"', 'text = "저장소에서 복원할까요?"'),
    ('text = "this pulls learnings, settings, and (if synced) chat history from ${state.owner}/${state.repo}, replacing any data on this device. the api key stays local — re-enter if needed."',
     'text = "${state.owner}/${state.repo}에서 학습 메모리, 설정, 동기화된 채팅 기록을 가져와 이 기기의 해당 데이터를 바꿉니다. API 키는 복원되지 않으므로 필요하면 다시 입력하세요."'),
    ('Text("cancel", color = MytharaColors.FgMute)', 'Text("취소", color = MytharaColors.FgMute)'),
    ('text = "last sync: ${java.text.SimpleDateFormat', 'text = "마지막 동기화: ${java.text.SimpleDateFormat'),
])

replace_in('ui/settings/TermuxSetupPanel.kt', [
    ('"exec threw"', '"실행 중 예외 발생"'),
    ('"Termux not installed — install from F-Droid."', '"Termux가 설치되지 않았습니다. F-Droid에서 설치하세요."'),
    ('"Play Store Termux is incompatible — install the F-Droid build instead."', '"Play Store판 Termux는 호환되지 않습니다. F-Droid판을 설치하세요."'),
    ('"RunCommandService not found — install the F-Droid Termux build (not the Play Store version)."', '"RunCommandService를 찾을 수 없습니다. Play Store판이 아닌 F-Droid판 Termux를 설치하세요."'),
    ('"Timed out. Did you set allow-external-apps=true in ~/.termux/termux.properties?"', '"시간 초과. ~/.termux/termux.properties에 allow-external-apps=true를 설정했는지 확인하세요."'),
    ('"Unexpected response: ${out.take(160)}"', '"예상하지 못한 응답: ${out.take(160)}"'),
    ('"${Glyph.DiamondOutline} termux — full GNU userland + Android platform tools"', '"${Glyph.DiamondOutline} Termux — GNU 사용자 환경 + Android 도구"'),
    ('"${Glyph.Dot} state: ${state.name}"', '"${Glyph.Dot} 상태: ${state.name}"'),
    ('"${Glyph.AccentBar} last verified ${formatRelative(ts)}"', '"${Glyph.AccentBar} 마지막 확인: ${formatRelative(ts)}"'),
    ('Text("grant RUN_COMMAND permission")', 'Text("RUN_COMMAND 권한 허용")'),
    ('Text("open F-Droid (com.termux)")', 'Text("F-Droid에서 Termux 열기")'),
    ('Text(if (running) "${Glyph.Ellipsis} verifying…" else "verify")', 'Text(if (running) "${Glyph.Ellipsis} 확인 중…" else "연결 확인")'),
])

replace_in('ui/settings/UserNamePanel.kt', [
    ('"e.g. Ankur, A, or just leave blank"', '"예: 홍길동, 길동 — 비워둬도 됩니다"'),
])
replace_in('ui/settings/FavoritesPanel.kt', [
    ('"${Glyph.Arrow} pick from contacts"', '"${Glyph.Arrow} 연락처에서 선택"'),
])
replace_in('ui/settings/SkillsPanel.kt', [
    ('"${Glyph.Cross} delete"', '"${Glyph.Cross} 삭제"'),
])
replace_in('ui/settings/McpServersPanel.kt', [
    ('"${Glyph.Refresh} re-discover"', '"${Glyph.Refresh} 다시 검색"'),
])
replace_in('ui/audit/AuditScreen.kt', [
    ('"${Glyph.Cross} clear"', '"${Glyph.Cross} 기록 삭제"'),
])
replace_in('ui/about/AboutMeScreen.kt', [
    ('Panel("loading")', 'Panel("불러오는 중")'),
    ('"reading the vault…"', '"메모리 저장소를 읽는 중…"'),
    ('Panel("your big five")', 'Panel("나의 Big Five")'),
])
replace_in('ui/secret/speaker/SpeakerEnrollmentDialog.kt', [
    ('"${Glyph.Cross} stop"', '"${Glyph.Cross} 중지"'),
])
replace_in('ui/settings/SettingsScreen.kt', [
    ('"remove key"', '"키 삭제"'),
    ('"clear key"', '"키 삭제"'),
])

strings = Path('app/src/main/res/values/strings.xml')
if strings.exists():
    s = strings.read_text()
    s = s.replace('<string name="app_name">Mythara 로컬</string>', '<string name="app_name">Mythara 로컬 KR</string>')
    strings.write_text(s)

print('Mythara Local Fold7 KR v4 expanded Korean UI overlay applied safely')
