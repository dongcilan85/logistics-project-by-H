-- =========================================================
-- IWP 창고관리 시스템 (Phase 7) 기반 DB 스키마 셋업
-- =========================================================

-- 1. 기존에 창고 테이블이 있다면 삭제하고 처음부터 깔끔하게 생성합니다.
-- (만약 기존 데이터를 보존해야 한다면 아래 DROP TABLE 구문을 지우고 실행해 주세요!)
drop table if exists public.warehouse_history cascade;
drop table if exists public.warehouse_inventory cascade;

-- 2. 핵심 재고 및 원가 테이블 생성
create table if not exists public.warehouse_inventory (
    id bigint primary key generated always as identity,
    item_name text not null,
    category text not null,
    current_quantity int default 0,
    max_capacity int default 1000,
    location_zone text default 'A구역',
    unit_type text default '개',
    unit_price int default 0, -- 재고 비용 파악을 위한 1단위당 단가
    updated_at timestamptz default now()
);

-- 3. 이력(히스토리) 테이블 생성 (Top Mover 등 변동량 추적용)
create table if not exists public.warehouse_history (
    id bigint primary key generated always as identity,
    item_id bigint references public.warehouse_inventory(id) on delete cascade,    
    item_name text not null,
    before_quantity int default 0,
    after_quantity int default 0,
    diff_amount int default 0,
    record_date date default current_date,
    created_at timestamptz default now()
);

-- 4. 기초 더미 데이터(Dummy Data) 등록
insert into public.warehouse_inventory (item_name, category, current_quantity, max_capacity, location_zone, unit_type, unit_price) values 
('안전모', '안전장비', 120, 200, 'A구역', '개', 15000),
('현장작업복 (L)', '안전장비', 85, 100, 'A구역', '벌', 35000),
('건축용 목재 (규격A)', '자재', 450, 500, 'B구역', '묶음', 12000),
('철근 10mm', '자재', 7000, 10000, 'B구역', 'kg', 200),
('드릴 공구 세트', '공구', 15, 20, 'C구역', '세트', 85000),
('포장용 래핑 필름', '소모품', 5, 50, 'C구역', '롤', 5000);

-- 5. 테스트를 위한 과거 히스토리 데이터(어제 기록) 생성 (변동량 1위 감지 기능 점검용)
insert into public.warehouse_history (item_id, item_name, before_quantity, after_quantity, diff_amount, record_date)
select id, item_name, current_quantity - 350, current_quantity, +350, current_date - interval '1 day'
from public.warehouse_inventory where item_name='철근 10mm';

insert into public.warehouse_history (item_id, item_name, before_quantity, after_quantity, diff_amount, record_date)
select id, item_name, current_quantity + 20, current_quantity, -20, current_date - interval '1 day'
from public.warehouse_inventory where item_name='안전모';

insert into public.warehouse_history (item_id, item_name, before_quantity, after_quantity, diff_amount, record_date)
select id, item_name, current_quantity - 5, current_quantity, +5, current_date - interval '1 day'
from public.warehouse_inventory where item_name='드릴 공구 세트';
