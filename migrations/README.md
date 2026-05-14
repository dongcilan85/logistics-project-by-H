# Migrations

이 폴더는 **이력 보존용** 마이그레이션 스크립트입니다.
운영 환경의 최신 스키마는 항상 **`../db_master.sql`** 을 기준으로 합니다.

## 파일 목록

| 파일 | 용도 | 상태 |
|---|---|---|
| `add_site_table.sql` | site_names 테이블 추가 | ✅ db_master.sql에 통합됨 |
| `create_site_names.sql` | site_names 초기 생성 | ✅ db_master.sql에 통합됨 |
| `create_rpa_commands.sql` | rpa_commands 테이블 추가 | ✅ db_master.sql에 통합됨 |
| `warehouse_full_setup.sql` | 창고 테이블 초기 셋업 (⚠️ DROP CASCADE 포함) | ⚠️ 운영 실행 금지 |

## 주의
- 신규 환경 셋업 시에도 `db_master.sql` 만 실행하면 충분합니다.
- 이 폴더의 파일은 **참고/이력용**이며 운영 DB에 직접 실행하지 마세요.
- 새 마이그레이션이 필요하면 이 폴더에 추가하고 `db_master.sql`에도 멱등성 형태로 반영하세요.
