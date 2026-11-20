# UI6-015 — 런타임 전투 세션 전환 중 명령 대기 교착 및 응답 경합 수정

- **Task ID:** `UI6-015`
- **담당:** UI/UX (중앙 원장 **06**, 현재 채팅 호칭 **05**; 01 총괄 번호·소유권 확정 대기)
- **변경 상태:** UI 소유 독립 웹 파일 수정 및 실브라우저 테스트 완료 / **실제 Core·Android 통합 미완료**
- **기준:** 중앙 Space의 단일 세로 화면 계약 및 이전 `UI6-014` 제안 스냅샷 경계.
- **변경 대상:** `game-uiux-section5-preview/ui6-runtime-adapter.js`
- **회귀 추가:** `game-uiux-section5-preview/tests/ui6-015-command-lifecycle.cjs`
- **테스트 구성:** `game-uiux-section5-preview/tests/package.json`에 `test:port:race` 등록.
- **수정 코드 커밋:** [65ab9b3](https://github.com/fx564286/fx564286.github.io/commit/65ab9b3183d48c98cd011cd646bfc6bfa61e84e5)
- **새 회귀 테스트 커밋:** [26e52aa](https://github.com/fx564286/fx564286.github.io/commit/26e52aa3adaa54de3553c6753b7920dd04c84961)
- **테스트 등록 커밋:** [afa369c](https://github.com/fx564286/fx564286.github.io/commit/afa369c2814d0e6f8d8999d6744397a6630d349)

## 1. 결함 및 재현

`UI6-014` 통합 진입(`one-screen.html?mode=integration`)에서 `stat.allocate`를 전달하는 외부 호스트 콜백이 미해결 Promise를 반환하면 `pending=true`가 유지된다. 이때 **새로운 runId의 정상 스냅샷을 받아도 명령 버튼이 다시 활성화되지 않아** 실제 전투 세션 복원·재시작 후 UI가 잠길 수 있었다.

- ECC TDD **RED A**: `node tests/ui6-015-command-lifecycle.cjs` — 새 run `session-b` 수락 후 활성 `+` 버튼 기대 4개, 실제 0개. **exit 1**.
- 첫 수정에서는 새 revision마다 pending을 해제했지만, 정기 전투 틱은 해당 명령의 확인 응답이 아니므로 연속 클릭·중복 명령을 유도할 수 있었다.
- ECC TDD **RED B**: 동일 `session-a`의 revision 1→2 틱 중 미해결 명령이 있을 때 활성 버튼 기대 0개, 실제 4개. **exit 1**.

## 2. 최소 수정

- `commandEpoch` 토큰을 추가하고 전투 runId가 바뀔 때에만 이전 세션 명령 대기 상태를 무효화한다.
- **동일 runId의 증가하는 revision은 명령 ACK가 아니므로 pending 잠금을 유지**한다.
- 외부 dispatch Promise의 결과가 뒤늦게 도착해도 epoch가 달라졌다면 새 run의 pending 상태나 알림 텍스트를 덮어쓰지 않는다.
- 코어의 명령 검증·보상·저장·장비 스키마 또는 전투 권위 연산을 수정하지 않는다. 신규 공개 API를 추가하지 않는다.
- **계약 불변:** `ui6.view@0.1-proposal`, `ui6.command@0.1-proposal` 유지. `core.combat_event_feed@0.2`와의 실제 매핑은 미승인/미구현.

## 3. 실제 검증

로컬 Chromium:
```bash
node --check ui6-runtime-adapter.js
node tests/ui6-015-command-lifecycle.cjs
node tests/ui6-014-integration-port.cjs
node tests/ui6-014-rejection-restore.cjs
node tests/ui5-012-one-screen.cjs
node tests/ui5-012-state-and-a11y.cjs
node tests/ui5-013-character-art.cjs
```

**GREEN:** UI6-015, UI6-014 통합 320·390·1365px, 부정 입력·XSS·이전 run replay·복원, UI5-012 및 UI5-013 일반 시연 호환 검사 모두 exit **0**. 기존 이미지 자산·골드 mock·7몬스터 시연 계약은 `mode=integration`이 아닌 일반 화면에만 남겨 두었다.

공개 GitHub Pages Chromium:
```bash
UI6_URL='https://fx564286.github.io/game-uiux-section5-preview/one-screen.html?mode=integration&build=ui6-015' node tests/ui6-015-command-lifecycle.cjs
UI6_URL='https://fx564286.github.io/game-uiux-section5-preview/one-screen.html?mode=integration&build=ui6-015' node tests/ui6-014-integration-port.cjs
UI6_URL='https://fx564286.github.io/game-uiux-section5-preview/one-screen.html?mode=integration&build=ui6-015' node tests/ui6-014-rejection-restore.cjs
```

**공개 3종 검사 종료 코드 0**. JS 파일 HTTP 200, 배포 바이트와 로컬 수정본 일치. 
- 어댑터 SHA-256: `16064c5323aa198a5bb6856e0da704d1c576b1bdd47ecdbf66248a993f24899c` (13,607 bytes)
- 새 테스트 SHA-256: `27d98de6a305c63b90ed60419888d73900f3a8d5aa139e12382c4f63317942cd` (4,520 bytes)

**미수행:** TypeScript 타입 검사(정적 JS 프로젝트), 정량 커버리지, 공식 게임 Core 원본 E2E, Android 빌드 및 실기기, 서버 영속 저장·재화 지급 권위.

## 4. 안전성·계약 및 남은 리스크

- 외부 호스트 `dispatch()`가 **같은 runId에서 영원히 미해결**이면 UI 버튼은 계속 비활성화된다. 상태를 추측해 중복 명령을 발생시키지 않기 위한 보수적 동작이다. 따라서 01/09는 명령 ACK·타임아웃·중복방지 정책을 승인해야 한다.
- 새 runId 이전에 전송한 요청이 외부 코어에 뒤늦게 도착한다면 Core 측에서 runId/revision/요청 ID를 검증해야 한다. UI의 epoch는 **표시상 경합 방지이지 서버-side 취소/인증이 아니다.**
- `ui6.view`는 UI 소유 제안이며 실제 `core.combat_event_feed@0.2` ZIP 원본 필드와 호환 확인이 되지 않았다.
- 07 정식 리그/6부위 비주얼, 08 데이터 ID, 09 보상/저장 원자성, 02 QA의 동일 Android 빌드 검증은 아직 통합되지 않았다.
- 공통 게임 Git/실제 게임엔진 저장소가 공식 확정되지 않아 이 커밋은 **독립 UI 시연 저장소에만** 존재한다.

## 5. 협업·차단·다음 작업

- **1번 중앙 총괄:** 05↔06 UI/UX 번호 및 실제 게임 저장소/전투 이벤트·명령 ACK 계약 확정 필요.
- **01 Core / 09 Infra:** runId/revision 재전송·timeout/retry/명령 멱등성·보상 권위 계약 승인 후 동작 확인 필요.
- **02 QA:** 동일 게임 빌드에서 명령 지연·재접속·재시작 경합 및 Android 복원 테스트.
- **07/08:** 6부위 렌더 리그/ID 및 펫·스킬 상태 스키마 확정 시 UI 모델 매핑.
- **다음 우선순위:** 01이 공식 이벤트·상태 필드를 제출하면 독립 mock 대신 **실제 Core 상태 매핑** 구현 및 동일 클라이언트에서 검증.

**판정:** `CODE_VERIFIED / BROWSER_VERIFIED / NOT_STAGED / NOT_GAME_INTEGRATED / ANDROID_UNVERIFIED`.
