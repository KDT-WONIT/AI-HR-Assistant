#!/usr/bin/env python3
# Internet-connected workstation only. Download 100 Pexels stock photo candidates for CLASSROOM DEMO.
import csv, os, time, hashlib, argparse, concurrent.futures
from pathlib import Path
import requests
from PIL import Image
from io import BytesIO

HERE=Path(__file__).resolve().parent
MANIFEST=HERE/'docs'/'employee_photo_manifest_100.csv'
OUTPUT=HERE/'assets'/'photos'

def download(r,session,retry=2):
    eid=r['employee_id'];dst=OUTPUT/f'{eid}.jpg';url=r['photo_url']
    if dst.is_file():
        try:
            with Image.open(dst) as im: im.verify()
            return eid,'EXISTS',dst.stat().st_size
        except Exception: dst.unlink()
    for n in range(retry+1):
        try:
            response=session.get(url,timeout=25,headers={'User-Agent':'Mozilla/5.0 (student project; non-commercial demo)'})
            response.raise_for_status()
            if not response.headers.get('content-type','').lower().startswith('image/'):
                raise ValueError('Non-image response')
            if len(response.content)<2500:raise ValueError('Too small image')
            with Image.open(BytesIO(response.content)) as im:
                im=im.convert('RGB');im.thumbnail((650,650)); im.save(dst,'JPEG',quality=83,optimize=True)
            return eid,'DOWNLOADED',dst.stat().st_size
        except Exception as e:
            if n==retry: return eid,'FAILED: '+str(e)[:100],0
            time.sleep(1.2)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--approved-only',action='store_true',help='Download only rows approved in docs/kdn_photo_review_results.csv')
    a=ap.parse_args()
    rows=list(csv.DictReader(open(MANIFEST,encoding='utf-8-sig')))
    reviews={}
    review_file=HERE/'docs'/'kdn_photo_review_results.csv'
    if a.approved_only:
        if not review_file.exists():raise SystemExit('검수 CSV를 docs/kdn_photo_review_results.csv에 저장한 다음 실행해 주세요.')
        reviews={x['employee_id']:x['review_status'] for x in csv.DictReader(open(review_file,encoding='utf-8-sig'))}
        rows=[r for r in rows if reviews.get(r['employee_id'])=='APPROVED']
    OUTPUT.mkdir(parents=True,exist_ok=True)
    results=[];session=requests.Session()
    for i,r in enumerate(rows,1):
        res=download(r,session);results.append(res)
        print(f'[{i:03}/{len(rows)}] {res[0]} {res[1]} ({res[2]} bytes)')
    hashes={};dups=[]
    for eid,st,_ in results:
        p=OUTPUT/f'{eid}.jpg'
        if p.is_file():
            h=hashlib.sha256(p.read_bytes()).hexdigest()
            if h in hashes:dups.append((hashes[h],eid))
            hashes[h]=eid
    with open(HERE/'docs'/'photo_download_report.csv','w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['employee_id','download_status','bytes']);w.writerows(results)
    print('처리 건수',len(results),'다운로드/기존',sum(s in ['EXISTS','DOWNLOADED'] for _,s,_ in results),'실패',sum(s.startswith('FAILED') for _,s,_ in results),'동일 파일',dups)
    print('이미지를 확인한 뒤 승인/교체 필요 여부를 검수 갤러리에 표시하세요.')
if __name__=='__main__':main()
