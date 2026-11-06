"""현재 로컬 서비스 구조를 기술 아이콘을 포함한 SVG로 작성합니다."""
import base64
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs' / 'architecture'
ICONS = json.loads((OUT / 'icon-sources.json').read_text(encoding='utf-8'))
W,H = 2560,1460
parts=[]
TEXT='#243344'; MUTED='#637385'; LINE='#53677c'; TEAL='#207f83'; BLUE='#27638d'; ORANGE='#ad6439'


def text(x,y,value,size=23,weight=400,color=TEXT,anchor='start'):
    parts.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{color}" text-anchor="{anchor}">{html.escape(value)}</text>')


def rect(x,y,w,h,stroke='#c4ced8',fill='white',radius=3,dash=None,width=1.6):
    extra=f' stroke-dasharray="{dash}"' if dash else ''
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="{width}"{extra}/>')


def icon(name,x,y,w=50,h=None):
    spec=ICONS[name]
    if spec['status']!='downloaded':
        raise ValueError('Missing technology icon: '+name)
    svg=(OUT/spec['file']).read_text(encoding='utf-8')
    if spec['color']:
        svg=svg.replace('<svg ',f'<svg fill="{spec["color"]}" ',1)
    encoded=base64.b64encode(svg.encode()).decode()
    parts.append(f'<image x="{x}" y="{y}" width="{w}" height="{h or w}" preserveAspectRatio="xMidYMid meet" href="data:image/svg+xml;base64,{encoded}"/>')


def path(points,color=LINE,dash=None,both=False,width=2.3,arrow=True):
    data='M '+' L '.join(f'{x} {y}' for x,y in points)
    attrs=f' stroke-dasharray="{dash}"' if dash else ''
    if arrow:
        attrs+=' marker-end="url(#arrow-'+('orange' if color==ORANGE else 'gray' if color=='#8b98a5' else 'main')+')"'
    if both:
        attrs+=' marker-start="url(#arrow-start)"'
    parts.append(f'<path d="{data}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linejoin="round"{attrs}/>')


def badge(x,y,n):
    rect(x-16,y-17,32,32,stroke='none',fill=BLUE,radius=3)
    text(x,y+6,str(n),21,700,'white','middle')


def note(x,y,value,size=20,color=MUTED):
    width=len(value)*size*.57+18
    rect(x-6,y-size+1,width,size+8,stroke='none',fill='white',radius=0)
    text(x,y,value,size,color=color)


def store(x,y,w,title,subtitle,detail,filename,logo='sqlite'):
    rect(x,y,w,190,stroke='#b8c8d4')
    if logo=='chroma':
        icon('chroma',x+23,y+23,150,38)
        text(x+23,y+94,title,24,700)
        text(x+23,y+126,subtitle,19,color=MUTED)
        text(x+23,y+156,detail,18,color=MUTED)
    else:
        icon(logo,x+22,y+23,53)
        text(x+94,y+47,'SQLite',25,700)
        text(x+24,y+104,title,25,700)
        text(x+24,y+139,subtitle,20,color=MUTED)
        text(x+24,y+170,detail,18,color=MUTED)
    text(x+w/2,y+220,filename,18,color=MUTED,anchor='middle')


def main():
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="title desc">')
    parts.append('<title id="title">WONIT 사내 규정 AI 업무 도우미 시스템 아키텍처</title>')
    parts.append('<desc id="desc">웹 사용자와 FastAPI, 로컬 Ollama, MCP 업무 도구 프로세스, BGE-M3와 ChromaDB, 분리된 SQLite 저장소, 외부 n8n 및 Google Sheets의 실제 연결 구조.</desc>')
    parts.append('<defs>')
    for name,color in [('main',LINE),('orange',ORANGE),('gray','#8b98a5')]:
        parts.append(f'<marker id="arrow-{name}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 1 1 L 9 5 L 1 9" fill="none" stroke="{color}" stroke-width="1.5"/></marker>')
    parts.append(f'<marker id="arrow-start" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 1 1 L 9 5 L 1 9" fill="none" stroke="{LINE}" stroke-width="1.5"/></marker></defs>')
    parts.append('<g font-family="Malgun Gothic, Arial, sans-serif">')
    rect(0,0,W,H,stroke='none',radius=0)
    text(60,64,'WONIT  사내 규정 AI 업무 도우미',38,700)
    text(62,102,'SYSTEM ARCHITECTURE  /  Local LLM · MCP · RAG',21,color=MUTED)
    text(2490,74,'현재 구현 기준',20,color=MUTED,anchor='end')

    # 실행 경계와 역할. 구름·VPC 등 사용하지 않는 인프라를 추가하지 않습니다.
    rect(600,145,1480,1165,stroke=BLUE,dash='10 7',fill='#fcfdff',radius=0,width=1.8)
    text(625,184,'LOCAL RUNTIME',23,700,BLUE)
    text(850,184,'현재 개발 PC',21,color=MUTED)
    rect(2155,145,345,1165,stroke='#bdc8d3',dash='8 6',fill='#fffdfb',radius=0)
    text(2181,184,'EXTERNAL SERVICES',21,700)

    # 웹 클라이언트
    parts.append('<g stroke="#637385" stroke-width="2.7" fill="none"><circle cx="110" cy="487" r="20"/><path d="M75 550v-17c0-20 16-34 35-34s35 14 35 34v17z"/></g>')
    text(110,593,'임직원',24,700,anchor='middle')
    rect(245,417,285,260,stroke='#9eb2c3')
    icon('googlechrome',267,438,51)
    text(335,464,'Web Browser',26,700)
    text(269,510,'WONIT v7 UI',25,700)
    text(269,546,'채팅 · 계산기 · 규정집',21,color=MUTED)
    text(269,578,'사원 검색 · 이력 · 평가',21,color=MUTED)
    icon('html5',272,609,36);icon('css',324,609,36);icon('javascript',376,609,36)
    text(269,709,'HTML / CSS / JavaScript',18,color=MUTED)

    # Ollama는 Agent와 HTTP로 연결되는 독립 프로세스입니다.
    rect(662,229,481,166,stroke='#9babb9')
    icon('ollama',687,251,62)
    text(772,279,'Ollama',30,700)
    text(772,315,'gemma4:e2b',23)
    text(687,364,'도구 선택(JSON) · 근거 기반 답변 생성',21,color=MUTED)

    # FastAPI 프로세스의 내부 오케스트레이션 기능
    rect(650,507,505,397,stroke=TEAL,width=2)
    icon('fastapi',678,532,62)
    text(761,565,'FastAPI',31,700)
    icon('python',1065,544,43)
    text(680,611,'Agent Orchestrator',25,700)
    path([(679,632),(1120,632)],color='#d4dde4',arrow=False,width=1.2)
    text(682,678,'사용자·세션 / 대화 컨텍스트',23)
    text(682,725,'도구 선택 규칙 / 인자 검증',23)
    text(682,772,'근거 조합 / 답변 검증',23)
    text(682,819,'담당자 추천 / 대화·평가 저장',23)
    text(682,870,'Python · Uvicorn · SSE',19,color=MUTED)

    # MCP 업무 도구 서버는 별도 Python 자식 프로세스입니다.
    rect(1260,452,720,452,stroke='#778d9f',width=1.8)
    icon('modelcontextprotocol',1288,477,58)
    text(1365,514,'MCP 업무 도구 서버',29,700)
    icon('python',1902,485,43)
    text(1290,552,'별도 Python 프로세스 · 9개 업무 도구',21,color=MUTED)
    path([(1290,576),(1948,576)],color='#d4dde4',arrow=False,width=1.2)
    for y,value in [(616,'인사·고용  /  근무·노사  /  급여·복지'),(655,'계약·회계  /  감사·윤리  /  보안·안전'),(694,'조직·경영  /  연구·품질  /  출장·여비')]:
        text(1290,y,value,23)
    text(1290,740,'DB 조회 · Python 계산 · 규정 검색(RAG)',22,700)
    rect(1289,769,650,100,stroke='#d1dbe4',fill='#f9fbfd')
    icon('huggingface',1310,788,57)
    text(1387,805,'BGE-M3 / Sentence Transformers',23,700)
    text(1387,843,'로컬 질문 임베딩 · 1,024차원',20,color=MUTED)

    # 데이터 준비 경로: 앱의 실시간 처리와 구분합니다.
    rect(1390,229,575,156,stroke='#bcc7d0',dash='5 4')
    parts.append('<g transform="translate(1414 251)" fill="none" stroke="#7d8a98" stroke-width="2.4"><path d="M0 0h34l13 13v50H0z M34 0v14h13 M9 30h27 M9 40h27 M9 50h20"/></g>')
    text(1484,275,'규정 PDF · 사전 색인 구축',26,700)
    text(1484,315,'Docling → 청킹 → BGE-M3',21,color=MUTED)
    text(1484,351,'원본 PDF / 구조화 문서 / 검색 색인',19,color=MUTED)

    # 로컬 저장소
    store(650,1060,412,'대화 · 평가 DB','질문 / 답변 / 컨텍스트','세션 · 평가 · 종료 이벤트','data/app.sqlite3')
    store(1166,1060,412,'사원 · 조직 DB','프로필 / 부서 / 역할 / 연락처','읽기 전용 디렉터리','employee_directory.sqlite3')
    store(1682,1060,346,'Vector Store','규정 59개 / 조각 7,117개','본문 · 페이지 · 출처 메타데이터','chroma.sqlite3 + 벡터 색인',logo='chroma')

    # 외부 자동화 노드
    rect(2190,467,275,190,stroke='#d3b9bf')
    icon('n8n',2288,490,70)
    text(2327,601,'n8n Cloud',28,700,anchor='middle')
    text(2327,633,'Webhook · 이벤트 분기',20,color=MUTED,anchor='middle')
    rect(2190,842,275,190,stroke='#bbd4c7')
    icon('googlesheets',2302,863,50)
    text(2327,966,'Google Sheets',26,700,anchor='middle')
    text(2327,1004,'세션 · 질문/답변 · 평가',19,color=MUTED,anchor='middle')

    # 실시간 서비스 연결: 직각 경로로 교차와 선 겹침을 줄입니다.
    path([(154,545),(245,545)],both=True)
    path([(530,600),(650,600)],both=True)
    badge(590,558,1)
    text(546,639,'HTTP · SSE',18,color=MUTED)
    path([(902,507),(902,395)],both=True)
    badge(868,450,2)
    note(928,451,'HTTP :11434',18)
    path([(1155,609),(1260,609)],both=True)
    badge(1208,566,3)
    text(1173,649,'stdio',19,color=MUTED)
    text(1171,677,'MCP',19,color=MUTED)

    # 사원 데이터는 API와 MCP에서 함께 조회합니다.
    path([(824,904),(824,1060)],both=True)
    badge(790,987,5)
    note(849,989,'저장 / 조회',18)
    path([(1070,904),(1070,1016),(1264,1016),(1264,1060)])
    note(1079,1006,'사용자 조회',18)
    path([(1410,904),(1410,1060)])
    note(1435,1038,'사원 조회',18)
    path([(1815,904),(1815,1060)],both=True)
    badge(1780,988,4)
    note(1840,989,'벡터 검색',18)

    # PDF 구축은 상시 요청 경로가 아닌 사전 작업입니다.
    path([(1965,304),(2044,304),(2044,1000),(1976,1000),(1976,1060)],color='#8b98a5',dash='6 6')
    text(1998,697,'사전',18,color=MUTED)
    text(1998,727,'적재',18,color=MUTED)

    # 비동기 이벤트는 요청 경로와 구분해 표시합니다.
    path([(1155,849),(1206,849),(1206,955),(2112,955),(2112,562),(2190,562)],color=ORANGE,dash='9 6')
    badge(2055,950,6)
    note(1518,947,'백그라운드 이벤트 · HTTPS POST',19,color=ORANGE)
    path([(2327,657),(2327,842)],color=ORANGE,dash='9 6')
    note(2198,759,'이벤트별 행 추가 / 갱신',18,color=ORANGE)

    # 선의 의미를 하단 범례에 표시합니다.
    path([(72,1380),(145,1380)],arrow=False)
    text(161,1387,'요청 · 조회 · 응답',19,color=MUTED)
    path([(439,1380),(512,1380)],color=ORANGE,dash='9 6',arrow=False)
    text(528,1387,'외부 이벤트 전송',19,color=MUTED)
    path([(810,1380),(883,1380)],color='#8b98a5',dash='6 6',arrow=False)
    text(899,1387,'사전 데이터 구축',19,color=MUTED)
    text(2490,1390,'WONIT  /  2026.11',19,color=MUTED,anchor='end')
    parts.append('</g></svg>')
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'system-architecture.svg').write_text('\n'.join(parts),encoding='utf-8')
    print(OUT/'system-architecture.svg')


if __name__=='__main__':
    main()
