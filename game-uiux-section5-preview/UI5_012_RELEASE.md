# UI5-012 — 중앙 제품 계약 기반 단일 화면 UI 시연

**Task ID:** `UI5-012`  
**제출 식별자(제안):** `ECL_UI_012_PENDING_INTAKE`  
**담당:** 이 대화의 **5번 UI/UX**. 중앙 Space 기준 **6번 UI/UX**이므로 번호 불일치 **미해소**. 공식 `section_id=06`으로 승인된 제출은 아님.  
**진행 상태:** 독립 HTML UI 구현·Chromium 검증·GitHub Pages 배포 완료. **중앙 STAGED/PROMOTED/RELEASE VERIFIED 아님.**

## 1. 구현 결과

- [단일 화면 v0.6 웹 실행](https://fx564286.github.io/game-uiux-section5-preview/one-screen.html?build=ui5-012)
- [원본 HTML](https://github.com/fx564286/fx564286.github.io/blob/main/game-uiux-section5-preview/one-screen.html) (`sha256 35a0a30edce97069fd9ee458bb111745c524d8b0a9a598ab2931ac31c50e83da`)
- [이전 메뉴형 시연](https://fx564286.github.io/game-uiux-section5-preview/?build=ui5-012)은 유지. 메인 거점 화면에 새 단일 화면 링크 추가.
- [브라우저 계약 테스트](https://github.com/fx564286/fx564286.github.io/blob/main/game-uiux-section5-preview/tests/ui5-012-one-screen.cjs) (`sha256 394e45c63c53137478447d99f3b2ac9f8270eb1d52e2315d5e042290180eb6f9`)
- [상태/접근성 테스트](https://github.com/fx564286/fx564286.github.io/blob/main/game-uiux-section5-preview/tests/ui5-012-state-and-a11y.cjs) (`sha256 950a987a6380a6dc6f892eea2ba312cbc7c2757960f22aa0c2d17907d2e8c8e4`)

## 2. 중앙 제품 계약과 일치하는 UI 동작

| 중앙 계약 | 구현(시각 검증 범위) |
|---|---|
| 단일 세로형 화면 | 전투가 화면 상단에 상시 존재하고 아래 설정 패널만 스크롤/탭 전환 |
| 캐릭터는 왼쪽 | 좌측 고정 임시 SVG로 표시 |
| 다수 몬스터 우측 출현 → 좌측 이동 | 7개 시연 인스턴스의 CSS 좌향 이동 |
| 전투 수동 입력 없음 | 수동 공격/스킬 발동 컨트롤 없음. 샘플 전투 틱만 자동 표시 |
| 스탯·스킬트리·자동 스킬 | STR/AGI/VIT/INT 분배·환원, 시연용 경로 3개, 기본/보조 자동 기술 설정 |
| 장비 6부위 | 6개 임시 슬롯 표시(명칭과 스키마는 미승인) |
| 펫 2슬롯, 탈것 제안 | Lv.15/40 및 Lv.25 잠금 상태를 시연 레벨로 검토 |
| 조건부 자동 포션 | UI에서 ON/OFF, HP 발동 기준 변경 시연 |
| 상단 재화 간소화 | 골드 샘플만 표시; 제작 재료·포션 상단 배제 |

**한계:** 값 1,240 골드, LV.12, 전투력 150, 데미지, 스탯 보정, 임시 스킬트리/장비/펫 상태는 *화면 점검용 fixture*이며 실제 경제·전투·성장 시스템의 원본 데이터가 아님. 전투는 CSS 애니메이션과 로컬 타이머만 이용하는 연출이며 실제 충돌/AI/피해 권위 계산과 연결되지 않음.

## 3. 테스트 및 실행 로그

실행: Node.js + `playwright-core` + Chromium. 공개 URL에서 실행한 뒤 반환 코드 0.

```bash
UI5_PREVIEW_URL='https://fx564286.github.io/game-uiux-section5-preview/one-screen.html?build=ui5-012' \
UI5_CHROME_PATH=/absolute/path/to/chrome node tests/ui5-012-one-screen.cjs

UI5_PREVIEW_URL='https://fx564286.github.io/game-uiux-section5-preview/one-screen.html?build=ui5-012' \
UI5_CHROME_PATH=/absolute/path/to/chrome node tests/ui5-012-state-and-a11y.cjs
```

- **RED:** `one-screen.html` 부재 상태에서 계약 테스트 실패(`ERR_FILE_NOT_FOUND`, exit 1).
- **GREEN:** 320×720, 390×844, 768×900, 1365×900에서 화면 순서/수평 overflow/44px 기본 버튼/7개 몬스터/우→좌 X좌표 감소/단일 URL 설정 전환 검증 통과.
- 몬스터 첫 인스턴스의 600ms X좌표 감소: **15, 18, 26, 26 px**(위 화면 폭 순서).
- 상태 검증: 능력치 배분·환원, 자동 포션/임계값, 스킬 자동화/3개 임시 트리, 6개 장비 슬롯, 펫 2·탈것 1 슬롯 및 시연 레벨 조건, 전투 DOM 유지/하단 스크롤, 원본 임시 아트의 색상, JavaScript 오류 0건. Chromium reduced-motion 정책 적용 통과.
- 배포 검증: **HTTP 200**, 로컬·공개 사이트 HTML SHA-256 완전 일치.
- 기존 5탭 UI: 보존; 거점의 단일 화면 이동 링크에서 320/390/1365px overflow·버튼 높이 44px 확인.

## 4. 의존성 / 통합 영향

- **1번 중앙 총괄·핵심 개발:** authoritative `combat.snapshot` / 몬스터 스폰 ID / 보상·골드 동기화 계약 **미확인**. 중앙 통합 여부는 1번 승인 전 확정하지 않음.
- **2번 QA:** `qa/acceptance/one_screen_preview.html` 및 `unanchored_damage` 계약 요구는 QA 별도 산출물로 확인. 이 UI는 해당 코어 피해 이벤트·식별자를 소비하지 않으므로 실제 전투 표시 통합은 **미검증**.
- **3번 성장·밸런스:** 전투 수치·스탯 트리·레벨 조건의 운영 파라미터 미연결.
- **7번 캐릭터 아트:** 캐릭터/몬스터는 기존 공개 시연에서 가져온 임시 SVG. 공식 rig/sprite/6부위 애니메이션 자산 **미확인**.
- **8번 데이터:** 장비·스킬·펫 정식 스키마 및 API 버전 미확인.
- **9번 인프라:** Android/게임엔진 빌드, 서버 저장·권위 보상 정산 미연동.
- **영향받은 파일:** UI 소유 정적 시연 `game-uiux-section5-preview/one-screen.html`, 이전 시연의 홈 링크 `game-uiux-section5-preview/index.html`, 테스트 두 파일, 테스트 README/package 설정. 게임 엔진·다른 섹션 원본은 변경하지 않음.

## 5. 제공/소비 계약 (제안, 승인 아님)

- **provides:** `ui.one_screen_preview@0.1` / `ui.mock_settings_projection@0.1` — 정적 브라우저 UI 테스트용 계약만.
- **consumes (blocked):** `combat.snapshot@UNSPECIFIED`, `art.character_rig@1.x` (중앙 제출 예시, 원본 미확인), `progression.player_state@UNSPECIFIED`, `inventory.equipment_visual@UNSPECIFIED`.
- **requires:** 중앙 1번의 섹션 소유권 확인, 정식 전투 상태 API, 7번 캐릭터 리그/펫/장비 외형, 8번 스킬·장비 스키마 및 검증된 원본 소스.
- **통합 상태:** `NOT_STAGED / AWAITING_CENTRAL_REVIEW`. 1번 중앙 총괄 승인 없이 공식 게임 클라이언트에 병합 불가.

## 6. 다음 작업

1. 중앙 1번에 이 대화의 '5번 UI/UX'와 공통 원장의 '6번 UI/UX' 번호 충돌 전달 및 소유권 확정.
2. 공식 전투 스냅샷·스폰 인스턴스 ID 계약을 확인해 UI의 mock 타이머 제거.
3. 전투 피해 팝업의 `unanchored_damage` 분리 및 보상 권위 분리 테스트; 현재 UI 피해 숫자는 전투 결과·아이템 지급 기준이 아님.
4. 공식 캐릭터·몬스터·펫 및 장비 6부위 아트 연결; 스킬트리와 장비 슬롯 명칭을 원본 정의로 대체.
5. 실제 모바일 Safari / Godot / Android 빌드 검증은 별도 수행. **현재 수행하지 않음.**
