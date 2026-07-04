import requests, re

codes = ["501018", "161226"]

for code in codes:
    print(f"\n=== {code} ===")
    
    # 1. Check basic fund info to identify what type it is
    r = requests.get('https://fundgz.1234567.com.cn/js/' + code + '.js',
                     headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://fund.eastmoney.com/'}, timeout=10)
    print(f"  fundgz: {r.text[:200]}")
    
    # 2. Try jjcc with different type values
    for type_val in ['jjcc', 'ccbd', 'zcch', 'bondhold', 'qhhold']:
        params = {'type': type_val, 'code': code, 'topline': '300', 'year': '2026', 'month': '', 'rt': '0.5'}
        r = requests.get('https://fundf10.eastmoney.com/FundArchivesDatas.aspx',
                         params=params,
                         headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://fund.eastmoney.com/'}, timeout=15)
        has_content = 'content:' in r.text and len(r.text) > 100
        print(f"  type={type_val}: len={len(r.text)}, has_content={has_content}")
        if has_content:
            match = re.search(r'var apidata\s*=\s*\{.*?content:"(.*?)".*?\}', r.text, re.DOTALL)
            if match:
                content = match.group(1).replace('\\"', '"')
                print(f"    content_len={len(content)}, first 200: {content[:200]}")
    
    # 3. Try jjcc with year=2025, 2024, empty
    for year in ['2025', '2024', '']:
        params = {'type': 'jjcc', 'code': code, 'topline': '300', 'year': year, 'month': '', 'rt': '0.5'}
        r = requests.get('https://fundf10.eastmoney.com/FundArchivesDatas.aspx',
                         params=params,
                         headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://fund.eastmoney.com/'}, timeout=15)
        match = re.search(r'var apidata\s*=\s*\{.*?content:"(.*?)".*?\}', r.text, re.DOTALL)
        if match:
            content = match.group(1).replace('\\"', '"')
            print(f"  jjcc year={year or 'auto'}: content_len={len(content)}")
            if len(content) > 0:
                print(f"    first 200: {content[:200]}")
        else:
            print(f"  jjcc year={year or 'auto'}: no content, raw_len={len(r.text)}")
    
    # 4. Try the datacenter API for fund portfolio
    for reportName in ['RPT_DMSK_FN_FUNDPORTFOLIODATE', 'RPT_DMSK_FN_FUNDHOLDSTOCK', 'RPT_FUND_PORTFOLIO']:
        params = {
            'reportName': reportName,
            'columns': 'ALL',
            'filter': f'(FCODE={code})',
            'pageNumber': '1',
            'pageSize': '5',
            'source': 'HSF10',
            'client': 'PC',
        }
        r = requests.get('https://datacenter-web.eastmoney.com/api/data/v1/get',
                         params=params, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        d = r.json()
        if d.get('success'):
            data = d.get('result', {}).get('data', [])
            print(f"  datacenter {reportName}: success, count={len(data)}")
            if data:
                print(f"    keys: {list(data[0].keys())}")
        else:
            print(f"  datacenter {reportName}: fail, msg={d.get('message', '')[:50]}")
