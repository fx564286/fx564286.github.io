# UI5-013 · 캐릭터 그래픽 고품질 임시 아트 적용

- **Task ID:** `UI5-013`
- **담당 섹션:** 이 채팅의 5번 UI/UX. 중앙 Space 기준 UI/UX는 6번으로 표기되어 번호 충돌 **미해소**.
- **기준 일자:** 2026-11-20
- **진행 상태:** 고해상도 임시 원화 웹 반영·공개 Chromium 검증 **완료**. 공식 캐릭터 아트 승인 및 게임 엔진 통합 **미완료**.
- **배포:** https://fx564286.github.io/game-uiux-section5-preview/one-screen.html?build=ui5-013
- **변경 파일:** `game-uiux-section5-preview/one-screen.html` (내장 WebP 원화 + 전신/얼굴 검사 + 인터랙션)
- **추가 테스트:** `game-uiux-section5-preview/tests/ui5-013-character-art.cjs` 
- **변경 테스트:** `game-uiux-section5-preview/tests/ui5-012-state-and-a11y.cjs`
- **개발 환경:** ECC 거점 미러 `ccd8da1`; `tdd-workflow` 기반 RED→GREEN·Chrome 브라우저 검증.

## 자산

- **신규 이미지:** 1024×1536 RGBA 투명 배경 캐릭터 원화 → WebP 변환 후 HTML 내 `HERO_ART_URI`로 내장.
- **전신 WebP 원본 SHA-256:** `fdc988547766b60412ebfd16030db186ed139ad843dfb55d85f34712a0b7f295`
- **최종 배포 HTML SHA-256:** `c2fd9cedc0ed220ed84db812cff18c1b984982fe0e57736e06940936c58c4df4`
- **형태:** 안면 노출, 검은 머리·실버 헤어 포인트, 청록 망토, 은·금 트림 갑옷, 롱소드, 장갑·부츠 전신.
- **제한:** AI 생성 1장의 정적 컨셉 아트. 스프라이트 시트, 골격 리깅, 타격 모션 프레임, 장비 6부위 분리 레이어, 직업/성별 선택, 최종 디자인 승인을 대체하지 않음.

## 변경 사항

1. 상단 자동 사냥의 무표정 도형 SVG를 실제 사람 형태의 반투명/투명 PNG 기반 WebP 일러스트로 대체.
2. 캐릭터 클릭(터치 및 키보드 접근)을 허용하여 `외형` 탭으로 진입.
3. 하단 성장 설정에 **외형** 탭 추가; 전신 일러스트, 얼굴/상체 상세, 150% 확대 및 복귀 제공.
4. HUD 라벨이 얼굴과 겹치지 않도록 상단 전투 레이어 조정.
5. 기존 7개 적 이동·자동 사냥과 능력치·스킬트리·6부위 장비·펫·탈것/포션 시연 데이터 모델 유지.
6. 외부 이미지 URL 없이 단일 HTML 제공. 실험용 UI 자산이 실제 장비 강화/진화 상태를 표현한다고 주장하지 않음.

## ECC TDD / 결함 재현

- **RED:** 브라우저에서 신규 원화는 표시되었으나 이전 UI의 `pointer-events:none`이 남아 캐릭터 클릭이 불가능. `ui5-013-character-art.cjs`의 click 검사에서 Playwright timeout 30s 확인.
- **FIX:** `.hero-unit{pointer-events:auto;}`로 전투 캐릭터의 클릭 이벤트 활성화. UI5-013 전용 검사 및 이전 UI5-012 검사 회귀 수행.
- **GREEN:** 320×720, 390×844, 768×900, 1365×900에서 원화의 1024×1536 원본 디코딩, 구형 플레이어 SVG 0건, 캐릭터 클릭→외형 탭, 전신·얼굴 렌더, 150% 확대/복귀, 몬스터 7마리 유지, 가로 오버플로 없음, JS 예외 0건.
- **회귀:** UI5-012 스탯 배분·환원, 자동 포션, 스킬트리, 장비 6부위, 펫/탈것 게이트, 고정 전투/하단 스크롤, reduce-motion, 320/390/768/1365px 우→좌 몬스터 이동 검사 **통과**.
- **배포 QA:** GitHub Pages GET HTTP 200; source HTML SHA-256 일치 확인 후 **공개 URL 대상** UI5-013 + UI5-012 두 검사를 실행, 종료 코드 0.

## 연동/영향

- **1번 중앙 총괄/핵심 개발:** 실제 게임 프레임 렌더러·combat.snapshot 계약 및 UI 통합 승인 확인 대기.
- **7번 아트/애니메이션:** ART-015 및 장비 시각 레이어 원본 파일/스키마가 현재 제출 자료에 없어 확정 자산으로 연결되지 않음; 이번 이미지는 **UI 섹션 임시 자산**.
- **3번 성장/밸런스 및 8번 데이터:** 장비 ID·외형 레이어/펫·스킬 스키마 확정 정보 미확인.
- **QA:** 정적 화면 브라우저 테스트만 수행; 실제 Android/iOS Safari, Godot/엔진, 대규모 장비 조합, 서버 보상 권위는 미검증.
- **차단된 의존성:** 7번 정식 아트 시트/리그·6부위 분리 레이어, 1번 게임 렌더 API, 3·8번 공식 데이터 계약.
- **다음 작업:** 아트 섹션 최종 원본을 받은 뒤 임시 WebP 교체, 코어 애니메이션 루프·장비 외형 머징·타격 모션으로 전환. 본 단일 일러스트의 CSS idle 움직임은 애니메이션 리깅이 아니다.

## 관련 링크

- [UI5-013 단일 화면](https://fx564286.github.io/game-uiux-section5-preview/one-screen.html?build=ui5-013)
- [UI5-013 브라우저 테스트](https://github.com/fx564286/fx564286.github.io/blob/main/game-uiux-section5-preview/tests/ui5-013-character-art.cjs)
- [기존 UI5-012 검증/단일 화면 계약](https://github.com/fx564286/fx564286.github.io/blob/main/game-uiux-section5-preview/UI5_012_RELEASE.md)
