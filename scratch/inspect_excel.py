import pandas as pd
import os
from datetime import datetime

mmdd = datetime.now().strftime("%m%d")
dl_path = r"C:\Users\admin\Desktop\Ecount_Exports"
target_file = os.path.join(dl_path, f"{mmdd}_창고별재고현황(1).xlsx")

print(f"[*] 파일 분석 중: {target_file}")
if os.path.exists(target_file):
    try:
        # 헤더를 찾기 위해 상단 10줄 출력
        df_preview = pd.read_excel(target_file, header=None, nrows=10)
        print("\n--- [상단 10줄 데이터 미리보기] ---")
        print(df_preview.to_string())
        
        # 실제 데이터 시작점(헤더) 추정 시도
        # '품목코드'라는 단어가 포함된 행 찾기
        for i, row in df_preview.iterrows():
            if '품목코드' in row.values:
                print(f"\n✅ 발견: {i}번 행에 '품목코드' 컬럼이 있습니다.")
                break
    except Exception as e:
        print(f"❌ 분석 실패: {e}")
else:
    print("❌ 파일을 찾을 수 없습니다.")
