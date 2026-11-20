# UI6-014 — 단일 화면 UI의 외부 게임 상태 연결 경계 (중앙 승인 전 제안)

- Task ID: UI6-014
- 공식 소유 범위: 06 UI/UX. 현재 채팅 표시 05 UI/UX ↔ 중앙 06 UI/UX 번호 충돌은 01 중앙 총괄의 명시적 결정 대기.
- 상태: UI 소유 통합 어댑터 코드 작성 + 브라우저 계약 테스트 / 실제 게임 코어 연결 미완료 / Android 검증 미실시.
- 수정 파일: game-uiux-section5-preview/one-screen.html (연결 스크립트 삽입 한 줄)
- 추가 파일: game-uiux-section5-preview/ui6-runtime-adapter.js, tests/ui6-014-integration-port.cjs, tests/ui6-014-rejection-restore.cjs
- 기존 독립 시연은 보존: one-screen.html (쿼리 없음)
- 통합 전용 진입: one-screen.html?mode=integration

## 1. 해결하는 실제 통합 위험

UI5-013은 브라우저 mock 타이머, 시연용 1,240 골드, 7개 가짜 몬스터, 독립 스탯 상태를 자체 생성한다. 이를 공식 Core와 단순히 붙이면 표시·게임 권위·저장 상태가 분리되며 인벤토리/보상 중복 또는 UI 가짜 상태가 실제 값처럼 보일 위험이 있다.

UI6-014에서는 연결 모드에서 mock 타이머를 종료하고 mock getState API를 노출하지 않는다. 외부 런타임 상태가 없는 경우 전투 상태, HP, 골드, 몬스터 수를 임의로 채우지 않는다. 확인된 코어 스냅샷을 UI 고유 모델로 정규화한 값만 표시하며, UI가 전투 계산·드롭·장착·재화를 직접 저장하지 않는다.

## 2. 제공/소비 계약과 승인 상태

- Provides (UI-owned, proposal): ui6.view@0.1-proposal — 받아들이는 구조만 엄격히 검증하는 UI 투영 계약.
- Provides (UI-owned, proposal): ui6.command@0.1-proposal — 명령 의도 전달 형식; 완료 보장/권위 아님.
- Consumes candidate (unverified): core.combat_event_feed@0.2 (01 ECL-CORE-002의 제안). Core 원본 ZIP과 내부 read_event_page의 실제 JSON 구조를 이 작업에서 읽거나 실행하지 못했으므로 **직접 매핑 구현·검증하지 않음**.
- Requires: 01 승인된 게임 클라이언트/전투 스냅샷 어댑터, 08 장비 6개 공식 slotId, 07 장비 비주얼 레이어, 09 신뢰할 수 있는 상태·저장/보상 경계.
- 이 코드는 게임 공통 API가 아니라 UI 전용 제안이다. 중앙 승인 없이 01/07/08/09의 계약이나 파일을 수정하지 않는다.

## 3. 런타임 호출 계약

외부의 신뢰된 동일 페이지 호스트(게임 엔진 WebView 브리지 등)가 아래 단방향 호출을 수행한다. 아래 예시는 개념 계약이며 공식 Core API 코드가 아니다.

    const ui = window.ECLIPSE_UI_PORT;
    // Native/engine host must authenticate requests and validate commands itself.
    ui.connect({dispatch: command => gameCommandGateway(command)});
    gameSnapshotStream.on('validated-projection', view => {
      const verdict = ui.acceptSnapshot(view);
      if (!verdict.ok) recordDiagnostic(verdict.reason);
    });

통합용 진입 URL: one-screen.html?mode=integration. 연결 모드 이외에는 기존 mock 시연 동작이 그대로 유지된다. DOM 브리지에서는 window.postMessage, 원격 네트워크 연결, localStorage, 재화 쓰기, 보상 지급을 사용하지 않는다.

### UI 투영 예시 (형식 제안, authoritative 값이 아님)

    {
      "contract":"ui6.view@0.1-proposal",
      "runId":"game-session-001",
      "revision":7,
      "stage":{"title":"균열 초입","index":1},
      "player":{
        "name":"개척자","level":12,"hp":95,"maxHp":120,
        "gold":350,"statPoints":3,"power":150,
        "stats":{"str":12,"agi":9,"vit":10,"int":8}
      },
      "combat":{"kills":2,"status":"active"},
      "enemies":[
        {"id":"spawn-1","x":80,"lane":30,"hp":70,"maxHp":100},
        {"id":"spawn-2","x":50,"lane":60,"hp":42,"maxHp":100}
      ]
    }

위 형식은 별도 UI 호환 시험용 후보일 뿐 01 섹션의 event_feed 원본 필드 구조로 간주하지 않는다. 01이 snapshot 좌표계·스킬·장비 권위 구조를 확정하면 그 명세로 매퍼를 작성해야 한다.

선택 데이터가 없으면 **미확인**으로 처리한다.

- skills: {id,name,enabled}[] (최대 16개)
- equipment: {slotId,label,item}[] 정확히 6개, item은 null 허용; id 명칭은 중앙 확정 전 강제하지 않음
- companions: {kind:'pet'|'mount',slotId,name}[] (최대 3개, name null 허용)
- potion: {enabled,threshold,count} (threshold: 1~100)
- absent optional fields => 해당 탭에 '계약 미연결' 표시. 기존 mock 장비/펫을 실장착처럼 보여 주지 않음.

### 명령 의도 예시 (UI에서 상태를 바꾸지 않음)

    {
      "contract":"ui6.command@0.1-proposal",
      "requestId":"ui6-1",
      "runId":"game-session-001",
      "baseRevision":7,
      "op":"stat.allocate",
      "payload":{"stat":"str","delta":1}
    }

- 입력: stat.allocate / skill.auto.set / potion.auto.set.
- 각 버튼은 호스트 dispatch() 콜백을 통해 의도를 전달한다.
- 콜백 성공은 명령 적용 완료가 아니다. authoritative 이후 revision 스냅샷이 오기 전까지 화면 상태를 낙관적으로 변경하지 않는다.
- 명령 인증, 중복 실행 방지, 재화/장비 검증, 저장/보상 트랜잭션은 게임 코어/서버가 책임진다.
- 연결 전 명령 버튼은 비활성화되며 코어 전송에 실패해도 로컬 스탯을 증가시키지 않는다.

## 4. 유효성·동시성·보안 경계

- 잘못된 contract, revision 역행, 중복 적 ID, 잘못된 HP/좌표, 비유한 숫자, 33개 이상 적, 6개가 아닌 장비, 중복 슬롯을 거부한다.
- 같은 runId의 revision은 단조 증가만 수락한다. 최근 퇴역 runId를 재사용하는 스냅샷도 거부한다. 이 검사는 인증이 아니다.
- 유효성 검사를 완료하기 전까지 DOM을 수정하지 않는 원자적 진입 검사.
- 외부 문자열은 textContent로 출력한다. HTML 태그는 실행하지 않는다.
- 같은 적 ID는 DOM 인스턴스를 보존하여 Core 틱마다 전신 그래픽이 재생성되지 않도록 한다.
- 외부 데이터 수신 없이 브라우저를 새로고침하면 빈 상태에서 Core 재동기화를 기다린다. UI 로컬 스토리지를 게임 저장으로 취급하지 않는다.
- host API 연결은 동일 JS 실행환경에서만 제공하므로 출처 인증 자체를 제공하지 않는다. 브리지의 호출 권한·replay 보호·명령 검증은 01/09 소유.
- actor 시각 그래픽은 기존 임시 SVG/캐릭터 WebP 그대로. 07에서 승인한 스프라이트 리그·장비 6레이어 조합과 아직 미연동.

## 5. ECC TDD 검증

RED: ui6-014-integration-port.cjs 실행 시 'UI integration port exposed' assertion 실패 (exit 1).

GREEN (로컬 Chromium): 320×720, 390×844, 1365×900에서 초기 가짜 상태 0개, 스냅샷 후 정확한 적 3개·체력·골드·좌표, 동기화 revision, 오래된 스냅샷·중복 적 거부, stat.allocate 명령 하나만 전달·낙관적 수치 변경 없음, 장비/펫 데이터 부재 시 비어 있는 안내 표시 등 PASS.

부정 검사: 코어 미연결 시간 1250ms 동안 가짜 적 생성 없음, 부적절한 수치·계약·아이템·스킬·몬스터 및 중복 runId 검사, HTML 주입 문자열 텍스트 출력, 새로고침 후 Core 스냅샷 재전달 대기 PASS.

기존 UI5-012/013 단일 화면·전신 이미지·능력치·자동 사냥 3개 회귀 명령을 함께 실행하여 demo 기본 모드와의 호환성을 검사한다.

테스트 명령:

    node --check game-uiux-section5-preview/ui6-runtime-adapter.js
    node game-uiux-section5-preview/tests/ui6-014-integration-port.cjs
    node game-uiux-section5-preview/tests/ui6-014-rejection-restore.cjs

Chromium 또는 Google Chrome이 설치되어 있어야 한다. UI5_CHROME_PATH와 UI6_URL 환경변수로 브라우저 파일 및 검증 대상 URL을 지정할 수 있다. 이 브라우저 테스트는 **모의 계약 주입 E2E**이며 실제 게임 엔진 통합·Android 런타임 또는 서버 저장 검증은 아니다.

## 6. 섹션 의존성 및 다음 단계

1. 01 중앙 총괄: 05(채팅)↔06(공식) UI/UX 번호 충돌 해결. 이벤트 커서·런ID·HP·좌표계·스탯/스킬 명령 계약과 게임 클라이언트 원본 제출 및 명시적 API 승인.
2. 06 UI: 승인된 core.combat_event_feed 모델을 ui6.view 투영으로 바꾸는 실제 매퍼와 명령 라우팅 구현. 이 작업이 끝나기 전에는 UI6-014를 GAME_INTEGRATED로 표시하지 않음.
3. 08 데이터: 공식 장비 6슬롯 ID와 item→visual 매핑 제공 후 UI 표시 연결.
4. 07 그래픽: 승인된 스프라이트/리그·장비 별 레이어를 현재 정적 UI 아트 대신 실제 렌더에 연결.
5. 09 인프라: persistence, 보상 원자성, 복원·동기화 출처를 검증.
6. 02 QA: 동일 커밋에서 통합 Core/게임 실행/Android 빌드·실기기 회귀 별도 검증.

**상태:** UI_BOUNDARY_IMPLEMENTED / BROWSER_CONTRACT_VERIFIED / NOT_STAGED / NOT_GAME_INTEGRATED / ANDROID_UNVERIFIED.
