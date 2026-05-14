-- RPA 원격 트리거 명령 테이블
CREATE TABLE IF NOT EXISTS rpa_commands (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    command_type TEXT NOT NULL DEFAULT 'sync_inventory',
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, running, completed, failed
    message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    result_summary TEXT,
    requested_by TEXT DEFAULT 'admin'
);

-- RLS 정책 (필요 시)
ALTER TABLE rpa_commands ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all for authenticated" ON rpa_commands FOR ALL USING (true);
