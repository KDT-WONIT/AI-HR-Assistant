"""아키텍처 다이어그램용 공개 기술 아이콘을 로컬에 보관합니다."""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1] / 'docs' / 'architecture'
ASSETS = ROOT / 'icons'
SIMPLE = 'https://cdn.jsdelivr.net/npm/simple-icons@16.0.0/icons/'
ICONS = {
    'fastapi': (SIMPLE+'fastapi.svg', '#009688'),
    'python': (SIMPLE+'python.svg', '#3776AB'),
    'html5': (SIMPLE+'html5.svg', '#E34F26'),
    'css': (SIMPLE+'css.svg', '#663399'),
    'javascript': (SIMPLE+'javascript.svg', '#B89D00'),
    'googlechrome': (SIMPLE+'googlechrome.svg', '#4285F4'),
    'sqlite': (SIMPLE+'sqlite.svg', '#003B57'),
    'ollama': (SIMPLE+'ollama.svg', '#242424'),
    'n8n': (SIMPLE+'n8n.svg', '#EA4B71'),
    'googlesheets': (SIMPLE+'googlesheets.svg', '#0F9D58'),
    'modelcontextprotocol': (SIMPLE+'modelcontextprotocol.svg', '#30343B'),
    'huggingface': ('https://huggingface.co/front/assets/huggingface_logo-noborder.svg', None),
    'chroma': ('https://www.trychroma.com/_next/static/immutable/media/chroma-wordmark.3omc55d6a9e1l.svg', None),
}


def fetch(item):
    name,(url,color) = item
    try:
        request=Request(url,headers={'User-Agent':'Architecture-diagram/1.0'})
        with urlopen(request,timeout=20) as response:
            content=response.read()
        if b'<svg' not in content:
            raise ValueError('Not SVG')
        (ASSETS/(name+'.svg')).write_bytes(content)
        return name,dict(url=url,color=color,file='icons/'+name+'.svg',status='downloaded')
    except Exception as exc:
        return name,dict(url=url,color=color,status='failed',error=type(exc).__name__)


def main():
    ASSETS.mkdir(parents=True,exist_ok=True)
    with ThreadPoolExecutor(max_workers=5) as pool:
        manifest=dict(pool.map(fetch,ICONS.items()))
    (ROOT/'icon-sources.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({name:value['status'] for name,value in manifest.items()},ensure_ascii=False))


if __name__=='__main__':
    main()
