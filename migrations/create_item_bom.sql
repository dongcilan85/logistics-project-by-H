-- =========================================================================
-- IWP BOM (자재명세서) 테이블 생성 SQL
-- =========================================================================

CREATE TABLE IF NOT EXISTS public.item_bom (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    parent_item_code TEXT NOT NULL, -- 완제품(제품) 코드
    child_item_code TEXT NOT NULL,  -- 구성품(부자재) 코드
    quantity INT NOT NULL DEFAULT 1, -- 완제품 1개 당 소요량
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- 완제품과 구성품 매핑의 중복 방지 제약조건
    CONSTRAINT unique_parent_child UNIQUE (parent_item_code, child_item_code)
);

-- 권한 부여
GRANT ALL ON public.item_bom TO anon, authenticated, service_role;

-- 캐시 새로고침
NOTIFY pgrst, 'reload schema';
