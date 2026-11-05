'use strict';
/* WONIT Electronics v7 · 실제 API 연결형 프론트엔드 + 선택형 SSE 응답.
   테스트 데이터는 mock_server.py가 제공하며 브라우저 코드에서 규정·수치를 지어내지 않습니다.
   테스트 서버의 사번 확인은 실제 로그인/본인인증이 아닙니다. */
(() => {
  const cfg = window.WONIT_CONFIG || {};
  const $ = id => document.getElementById(id);
  const state = {
    view:'home', busy:false, employee:null, confirmedId:null, employeeBusy:false,
    selectedCategory:null, categories:[], conversation:[], last:null, requestCounter:0,
    sessionId:newSessionId(), sessionPersisted:false, closed:false, feedbackSaved:false, records:[], rating:0, ratedIds:new Set(), documentCategory:null, regulationDocs:[], questionBank:{},
    lastConnection:'unknown', stickToBottom:true, lastVerifiedEmployeeId:null, sessionGeneration:0
  };
  let toastTimer, employeeRequestId=0;
  function newSessionId(){return globalThis.crypto?.randomUUID?.() || `session-${Date.now()}-${Math.random().toString(36).slice(2)}`;}
  function show(id,on){$(id)?.classList.toggle('hidden',!on);}
  function el(tag,cls='',value){const n=document.createElement(tag);if(cls)n.className=cls;if(value!==undefined)n.textContent=String(value);return n;}
  function add(parent,tag,cls,value){const n=el(tag,cls,value);parent.append(n);return n;}
  function empty(n){n.replaceChildren();}
  function toast(s){$('toast').textContent=s;show('toast',true);clearTimeout(toastTimer);toastTimer=setTimeout(()=>show('toast',false),3600);}
  function warn(id,s){$(id).textContent=s;show(id,true);}
  function validUrl(s){try{const u=new URL(s,location.origin);return ['http:','https:'].includes(u.protocol)?u.href:null;}catch{return null;}}
  function safeResource(s){if(!s)return null;try{const u=new URL(s,location.origin);if(u.protocol==='https:'||(u.origin===location.origin&&['http:','https:'].includes(u.protocol)))return u.href;}catch{}return null;}
  function getError(e){if(e?.name==='AbortError')return '응답 시간 초과: 서버 상태를 확인해 주세요.';if(e instanceof TypeError)return '서버에 연결할 수 없습니다. 네트워크·CORS 설정을 확인해 주세요.';return e?.message||'요청을 처리하지 못했습니다.';}
  function setService(mode,label){state.lastConnection=mode;const n=$('serviceStatus');n.className='service-status '+({online:'service-online',error:'service-error',checking:'service-checking'}[mode]||'service-offline');$('serviceStatusText').textContent=label||{online:'서비스 응답 정상',error:'연결 오류',checking:'연결 확인 중',unknown:'연결 확인 전'}[mode];}
  async function post(key,body){const url=validUrl(cfg[key]);if(!url)throw new Error('서비스 연결 주소가 설정되지 않았습니다. config.js에서 '+key+'를 확인하세요.');setService('checking','연결 확인 중');const controller=new AbortController(),time=setTimeout(()=>controller.abort(),cfg.requestTimeoutMs||45000);try{
      const res=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:controller.signal});if(!res.ok){const err=await res.json().catch(()=>({}));throw new Error(typeof err.detail==='string'?err.detail:'서버 처리 오류 (HTTP '+res.status+')');}const data=await res.text();if(!data.trim())throw new Error('서버 응답이 비어 있습니다.');let json;try{json=JSON.parse(data);}catch{throw new Error('서버 응답이 JSON 형식이 아닙니다.');}
      setService('online',cfg.testMode?'로컬 테스트 연결됨':'서비스 응답 정상');if(Array.isArray(json)&&json.length===1&&json[0]?.json)return json[0].json;return json;
    }catch(e){setService('error','서비스 연결 오류');throw e;}finally{clearTimeout(time);}}
  // SSE 스트리밍: 서버가 답변을 조금씩 전송하면 같은 AI 말풍선에 실시간 누적합니다.
  // 최종 이벤트에는 기존 v5와 동일한 완전한 답변 JSON이 들어 있어야 합니다.
  async function streamChat(payload,pending){
    const url=validUrl(cfg.chatStreamUrl);if(!url)throw new Error('스트리밍 주소가 없습니다.');
    const ctrl=new AbortController(),timer=setTimeout(()=>ctrl.abort(),cfg.requestTimeoutMs||45000);
    setService('checking','답변 수신 중');let responseText='',finalJson=null,buffer='';
    function handleEvent(raw){
      let type='message',data='';for(const line of raw.replaceAll('\r','').split('\n')){
        if(line.startsWith('event:'))type=line.slice(6).trim();
        if(line.startsWith('data:'))data+=line.slice(5).trimStart();
      }
      if(!data)return;
      let parsed;try{parsed=JSON.parse(data);}catch{throw Error('스트리밍 JSON 이벤트가 올바르지 않습니다.');}
      if(type==='delta'){
        responseText=parsed.replace?String(parsed.text||''):responseText+String(parsed.text||'');
        if(pending?.bubble){empty(pending.bubble);add(pending.bubble,'div','chat-body',responseText+'▍');scrollLatest();}
      }else if(type==='status'){if(pending?.bubble&&!responseText){empty(pending.bubble);add(pending.bubble,'div','chat-body progress-message',parsed.text||'처리 중…');}}else if(type==='final'){finalJson=parsed;}
      else if(type==='error'){throw Error(String(parsed.error||'스트리밍 오류'));}
    }
    try{
      const res=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json','Accept':'text/event-stream'},body:JSON.stringify(payload),signal:ctrl.signal});
      if(!res.ok){let detail='';try{const body=await res.json();detail=body.error||'';}catch{}throw Error(`서버 처리 오류 (HTTP ${res.status})${detail?': '+detail:''}`);}
      if(!res.body)throw Error('브라우저가 스트리밍 응답을 지원하지 않습니다.');
      const reader=res.body.getReader(),decoder=new TextDecoder();
      while(true){const {value,done}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true});
        buffer=buffer.replaceAll('\r\n','\n');let end;
        while((end=buffer.indexOf('\n\n'))!==-1){const event=buffer.slice(0,end);buffer=buffer.slice(end+2);handleEvent(event);}
      }
      if(buffer.trim())handleEvent(buffer);
      if(!finalJson)throw Error('서버 스트리밍이 종료됐으나 최종 결과가 없습니다.');
      setService('online',cfg.testMode?'로컬 테스트 연결됨':'서비스 응답 정상');return finalJson;
    }catch(e){setService('error','서비스 연결 오류');throw e;}finally{clearTimeout(timer);}
  }
  async function checkHealth(){const url=validUrl(cfg.healthUrl);if(!url){if(!validUrl(cfg.chatWebhookUrl)&&!validUrl(cfg.employeeWebhookUrl))setService('unknown','서비스 미설정');else setService('unknown','연결 확인 전');return;}
    const ctrl=new AbortController(),t=setTimeout(()=>ctrl.abort(),5000);try{const resp=await fetch(url,{method:'GET',signal:ctrl.signal});if(!resp.ok)throw Error();const health=await resp.json();if(health.chat_available===false)throw Error();setService('online',cfg.testMode?'로컬 테스트 연결됨':'서비스 응답 정상');}catch{setService('error','상태 확인 실패');}finally{clearTimeout(t);}}
  function employeeId(){const digits=$('employeeId').value.replace(/\D/g,'');return digits?'WON'+digits:'';}
  function validateId(){const id=employeeId();if(!id)throw Error('사번을 먼저 입력해 주세요.');if(!/^[A-Z0-9_-]{2,40}$/.test(id))throw Error('사번은 영문·숫자·하이픈·밑줄로 입력해 주세요.');return id;}
  function profileAvatar(profile,className){
    const avatar=el('span','profile-avatar '+className);
    const label=(profile?.name||'사용자')+' 프로필 사진';
    const fallback=()=>{
      empty(avatar);avatar.setAttribute('role','img');avatar.setAttribute('aria-label',label);
      const icon=document.createElementNS('http://www.w3.org/2000/svg','svg');icon.classList.add('icon');icon.setAttribute('aria-hidden','true');
      const use=document.createElementNS('http://www.w3.org/2000/svg','use');use.setAttribute('href','#i-user');icon.append(use);avatar.append(icon);
    };
    const url=safeResource(profile?.image_url);
    if(!url){fallback();return avatar;}
    const image=document.createElement('img');image.src=url;image.alt=label;image.decoding='async';
    image.addEventListener('error',()=>{
      const resource=new URL(url,location.origin);
      if(!image.dataset.localFallback&&resource.origin===location.origin&&/^\/api\/users\/[^/]+\/photo$/.test(resource.pathname)){
        image.dataset.localFallback='1';resource.searchParams.set('fallback','true');image.src=resource.href;
      }else fallback();
    });avatar.append(image);return avatar;
  }
  function renderEmployeeSummary(profile){
    const summary=$('employeeSummary');empty(summary);summary.append(profileAvatar(profile,'summary-avatar'));
    const info=add(summary,'div','summary-person');add(info,'strong','',profile.name);
    add(info,'span','summary-person-details',[profile.department,profile.position||profile.job_title,profile.grade,profile.extension_number?'내선 '+profile.extension_number:'',profile.work_email].filter(Boolean).join(' · '));
  }
  function setBadge(profile,info){
    const badge=$('employeeBadge');empty(badge);badge.append(profileAvatar(profile,'badge-avatar'));
    add(badge,'span','',profile?.name?`${profile.name} · ${profile.department||''}`:info||'직원 미확인');
    $('chatEmployeeLabel').textContent=profile?.name?`${profile.name} · 직원 정보 확인`:employeeId()?'직원 조회 필요':'사번 입력 필요';
  }
  function clearSession(announce=false){state.sessionGeneration++;state.sessionPersisted=false;state.closed=false;state.feedbackSaved=false;rememberSession(null);$('chatInput').disabled=false;$('chatInput').value='';$('chatSend').disabled=false;show('endNotice',false);state.conversation=[];state.last=null;state.sessionId=newSessionId();state.ratedIds=new Set();empty($('chatMessages'));const box=el('div','chat-empty');box.id='chatEmpty';const icon=document.createElementNS('http://www.w3.org/2000/svg','svg');icon.classList.add('icon');const use=document.createElementNS('http://www.w3.org/2000/svg','use');use.setAttribute('href','#i-chat');icon.append(use);box.append(icon);add(box,'strong','','무엇이든 물어보세요');add(box,'p','','하나의 대화에서 연속 질문할 수 있습니다. 답변에는 확인된 규정 출처가 함께 표시됩니다.');$('chatMessages').append(box);$('chatSessionCaption').textContent='새 대화';$('openFeedback').disabled=true;show('chatError',false);if(announce)toast('새 대화를 시작했습니다.');}
  function onEmployeeInput(){const id=employeeId();if(id!==state.confirmedId){if(state.conversation.length)clearSession();state.employee=null;state.confirmedId=null;state.lastVerifiedEmployeeId=null;setBadge(null,id?`사번 ${id} · 확인 필요`:'직원 미확인');show('employeeSummary',false);employeeRequestId++;}}
  async function lookupEmployee(){let id;try{id=validateId();}catch(e){state.employee=null;setBadge(null);return false;}
    if(state.confirmedId===id&&state.employee?.name)return true;
    if(!validUrl(cfg.employeeWebhookUrl)){state.employee=null;state.confirmedId=null;setBadge(null,`사번 ${id} · 미확인`);warn('inputError','직원 조회 API 주소가 없습니다. 팀원에게 employeeWebhookUrl을 요청하세요.');return false;}
    const seq=++employeeRequestId;state.employeeBusy=true;const s=$('employeeSummary');s.textContent='직원 정보를 확인 중입니다...';show('employeeSummary',true);setBadge(null,'직원 확인 중');
    try{const raw=await post('employeeWebhookUrl',{employee_id:id});const p=raw.employee||raw.data?.employee||raw;const found=raw.found!==false&&raw.valid!==false&&raw.success!==false&&!!p?.name;if(!found)throw new Error('등록된 직원 정보를 찾을 수 없습니다. 사번을 확인하세요.');if(seq!==employeeRequestId||id!==employeeId())return false;
      state.employee=p;state.confirmedId=id;state.lastVerifiedEmployeeId=id;show('inputError',false);renderEmployeeSummary(p);setBadge(p);return true;
    }catch(e){if(seq!==employeeRequestId)return false;state.employee=null;state.confirmedId=null;setBadge(null,`사번 ${id} · 확인 실패`);s.textContent=getError(e);return false;
    }finally{state.employeeBusy=false;}}
  function nav(page){state.view=page;document.querySelector('.sidebar-categories')?.classList.toggle('hidden',!['home','answer'].includes(page));try{sessionStorage.setItem('wonit-hr-view',page);}catch{}document.body.classList.toggle('home-active',page==='home');['home','answer','rules','form','history','contacts','help'].forEach(x=>show(x+'View',x===page));document.querySelectorAll('.nav-btn').forEach(b=>b.classList.toggle('active',b.dataset.view===page||((page==='answer'||page==='form')&&b.dataset.view==='home')));closeMobile();if(page==='rules')renderCategoryList();if(page!=='answer')window.scrollTo(0,0);else{syncChatContext();scrollLatest(true);}}
  function closeMobile(){$('sidebar').classList.remove('open');show('mobileShade',false);}
  function category(){return state.categories.find(c=>c.id===state.selectedCategory);}
  function syncChatContext(){const c=category();$('chatCategoryLabel').textContent=c?'AI 질문 분야 · '+c.name:'분야 자동 선택';$('chatEmployeeLabel').textContent=state.employee?.name?`${state.employee.name} · 직원 정보 확인`:'직원 조회 필요';}
  function setCategory(id){state.selectedCategory=id||null;const c=category();show('categorySelection',!!c);if(c)$('categorySelectionText').textContent='AI 질문 분야 · '+c.name;syncChatContext();document.querySelectorAll('.sidebar-cat').forEach(b=>{const selected=(b.dataset.categoryId||'')===(id||'');b.classList.toggle('selected',selected);b.setAttribute('aria-pressed',String(selected));});}
  function chooseCategory(id){setCategory(id);renderQuestionExamples();closeMobile();const c=category();if(c){toast(c.name+' 분야를 선택했습니다.');if(state.view==='home')$('question').focus();else if(state.view==='answer')$('chatInput').focus();}else toast('분야 자동 선택으로 변경했습니다.');}
  function renderSidebarCategories(){const root=$('sidebarCategoryList');empty(root);const all=[{id:null,name:'분야 자동 선택'},...state.categories];const symbols=['✳','↗','◴','◇','▤','◎','⌘','▦','✧','➤','₩'];all.forEach((c,i)=>{const b=el('button','sidebar-cat');b.type='button';b.dataset.categoryId=c.id||'';b.setAttribute('aria-pressed',String((c.id||null)===state.selectedCategory));add(b,'span','sidebar-cat-icon',symbols[i]||'·');add(b,'span','',c.name);b.addEventListener('click',()=>chooseCategory(c.id));root.append(b);});setCategory(state.selectedCategory);}
  async function loadCategories(){
    try{const r=await fetch('/api/tools');if(!r.ok)throw Error();state.categories=(await r.json()).map(t=>({id:t.id,name:t.name,description:t.description}));}
    catch{state.categories=[];toast('업무 도구 목록을 불러오지 못했습니다.');}renderSidebarCategories();renderCategoryList();
  }
  async function loadQuestionBank(){
    try{const res=await fetch('assets/sample_questions.json',{cache:'no-store'});if(!res.ok)throw Error('질문 목록을 찾지 못했습니다.');const data=await res.json();const aliases={work_leave_labor:'work_labor',ethics_audit:'audit_ethics',organization:'organization_management',research_quality:'rnd_quality',travel:'travel_expenses',welfare:'pay_benefits',payroll:'pay_benefits'};state.questionBank={};for(const [key,items] of Object.entries(data.categories||{})){const id=aliases[key]||key;state.questionBank[id]=[...(state.questionBank[id]||[]),...items];}}
    catch(e){state.questionBank={};toast('질문 예시 파일을 읽을 수 없습니다.');}
    renderQuestionExamples();
  }
  function renderQuestionExamples(){
    const cat=category();const id=cat?.id||null;
    const examples=id?(state.questionBank[id]||[]):[
      '제 연차가 며칠 남았나요?',
      '그럼 3일 사용하면 얼마나 남나요?',
      '출장 중 휴가를 붙이면 숙박비도 지급되나요?',
      '연구개발 과제의 예산을 변경하려면 어떤 승인 절차가 필요한가요?'
    ];
    ['home','chat'].forEach(prefix=>{
      const area=$(prefix+'ExampleList');if(!area)return;empty(area);
      $(prefix+'ExampleCategory').textContent=cat?.name||'자동 선택';
      examples.forEach(question=>{const b=el('button','example-question',question);b.type='button';b.title='질문 입력창에 채우기';b.addEventListener('click',()=>{
        if(prefix==='home'||state.view==='home'){$('question').value=question;$('question').focus();}
        else {$('chatInput').value=question;$('chatInput').focus();}
      });area.append(b);});
    });
  }
  async function loadRegulations(){
    try{const r=await fetch('assets/regulations_catalog.json',{cache:'no-store'});if(!r.ok)throw Error('규정 목록 파일을 찾지 못했습니다.');const data=await r.json();state.regulationDocs=data.documents||[];state.documentCategories=data.categories||[];}
    catch(e){state.regulationDocs=[];toast('PDF 문서 목록을 불러오지 못했습니다.');}
    renderRulesCategoryTabs();renderCategoryList();
  }
  function renderRulesCategoryTabs(){
    const root=$('rulesCategoryTabs');empty(root);
    [{id:null,name:'전체 규정집'},...(state.documentCategories||[])].forEach(c=>{
      const b=el('button','library-tab'+(state.documentCategory===c.id?' active':''));b.type='button';
      add(b,'span','',c.name);add(b,'span','library-tab-count',String(state.regulationDocs.filter(d=>!c.id||d.category_id===c.id).length));
      b.addEventListener('click',()=>{state.documentCategory=c.id;renderRulesCategoryTabs();renderCategoryList();});root.append(b);
    });
  }
  function renderCategoryList(){
    const root=$('categoryGrid');empty(root);
    const search=$('categorySearch').value.trim().toLowerCase();
    const docs=state.regulationDocs.filter(d=>(!state.documentCategory||d.category_id===state.documentCategory)&&
      (d.title+' '+d.original_filename+' '+d.category_name+' '+d.revision).toLowerCase().includes(search));
    $('rulesDocCount').textContent=docs.length+'개 문서';show('categoryEmpty',!docs.length);
    docs.forEach(d=>{const item=el('article','document-row');const meta=el('div','document-meta');
      add(meta,'span','document-icon','PDF');const text=el('div','document-text');add(text,'strong','',d.title);
      add(text,'small','',d.category_name+' · '+(d.revision||'개정일 미확인')+(d.pages?' · '+d.pages+'쪽':''));
      add(text,'span','source-line','WONIT 전처리 문서 · 검증용');meta.append(text);item.append(meta);
      const b=add(item,'button','document-open','원문 열람');b.type='button';b.addEventListener('click',()=>openRegulation(d));root.append(item);
    });
  }
  function openRegulation(d){
    // 임의 URL을 iframe에 삽입하지 않고, 제공받은 로컬 PDF 목록만 허용합니다.
    if(!/^\/regulations\/wonit_preprocessed\/WONIT-\d{3}\.pdf$/.test(d.url)){toast('PDF 열람 주소가 올바르지 않습니다.');return;}
    $('pdfTitle').textContent=d.title;
    $('pdfInfo').textContent=[d.original_filename,d.revision,d.pages?d.pages+'쪽':''].filter(Boolean).join(' · ');
    $('pdfFrame').src=d.url+'#toolbar=1';$('pdfOpenTab').href=d.url;$('pdfDownload').href=d.url;$('pdfDownload').download=d.original_filename;
    show('pdfOverlay',true);$('closePdf').focus();document.body.classList.add('pdf-open');
  }
  function closeRegulation(){show('pdfOverlay',false);$('pdfFrame').removeAttribute('src');document.body.classList.remove('pdf-open');}
  function chatScrolledToBottom(){const n=$('chatMessages');return n.scrollHeight-n.scrollTop-n.clientHeight<110;}
  function onChatScroll(){state.stickToBottom=chatScrolledToBottom();show('jumpToLatest',!state.stickToBottom);}
  function scrollLatest(force=false){if(force||state.stickToBottom){const n=$('chatMessages');requestAnimationFrame(()=>n.scrollTo({top:n.scrollHeight,behavior:force?'instant':'smooth'}));}}
  function timestamp(dateString){const d=dateString?new Date(dateString):new Date();return (Number.isNaN(d.getTime())?new Date():d).toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit'});}
  function addBubble(role,content,cls=''){const row=el('div','chat-message '+role+(cls?' '+cls:''));const avatar=role==='user'?row.appendChild(profileAvatar(state.employee,'chat-avatar user-avatar')):add(row,'span','chat-avatar',role==='assistant'?'AI':'!');const bubble=el('div','chat-bubble');row.append(bubble);if(typeof content==='string')add(bubble,'div','chat-body',content);else if(content instanceof Node)bubble.append(content);$('chatMessages').append(row);scrollLatest();return {row,bubble,avatar};}
  function addPending(){const b=addBubble('assistant','');const dots=el('div','typing-dots');for(let i=0;i<3;i++)dots.append(el('span'));b.bubble.append(dots);return b;}
  function renderSources(container,sources){const d=el('details','sources-details');const summary=add(d,'summary','','관련 규정 출처 '+sources.length+'건');const list=el('div','source-list');sources.forEach((s,i)=>{const entry=el('div','source-entry');add(entry,'span','source-num',String(i+1).padStart(2,'0'));add(entry,'strong','',s.document||s.document_name||'문서명 미확인');const detail=[s.article,s.page?'PDF '+s.page+'쪽':'',s.version||s.effective_date].filter(Boolean).join(' · ');if(detail)add(entry,'small','',detail);if(s.text){const raw=el('details','source-original');add(raw,'summary','','검색 원문 보기');add(raw,'p','',s.text);entry.append(raw);}const url=safeResource(s.url||s.source_url);if(url){const a=add(entry,'a','','원문 열기');a.href=url;a.target='_blank';a.rel='noopener noreferrer';}list.append(entry);});d.append(list);container.append(d);}
  function renderSections(container,sections){sections.forEach((s,i)=>{const part=el('section','answer-section');add(part,'h4','',s.title||'확인 항목 '+(i+1));add(part,'p','',s.body||s.answer||'');if(Array.isArray(s.source_ids)&&s.source_ids.length)add(part,'small','','관련 근거 '+s.source_ids.map(x=>'['+x+']').join(', '));container.append(part);});}
  function renderCalculation(container,calc){if(!calc)return;const part=el('div','detail-block');add(part,'h4','','계산 내역'+(calc.title?' · '+calc.title:''));(Array.isArray(calc.items)?calc.items:[]).forEach(item=>{const line=el('div','calc-row');add(line,'span','',item.label||'');add(line,'strong','',String(item.value??''));part.append(line);});if(calc.note)add(part,'small','calc-note',calc.note);container.append(part);}
  function makeContactCard(p){
    const card=el('div','person-card'),avatar=el('div','avatar');const url=safeResource(p.image_url);
    if(url){const img=document.createElement('img');img.src=url;img.alt=(p.name||'담당자')+' 프로필';img.loading='lazy';img.onerror=()=>{if(!img.dataset.fallback&&url.includes('/api/users/')){img.dataset.fallback='1';img.src=url+'?fallback=true';}else avatar.textContent='HR';};avatar.append(img);}else avatar.textContent='HR';card.append(avatar);
    const meta=el('div','person-meta');add(meta,'strong','',p.name||'담당자');add(meta,'p','',[p.employee_id,p.department,p.position||p.job_title,p.grade].filter(Boolean).join(' · '));
    const extension=p.extension||p.extension_number;if(extension)add(meta,'span','','내선 '+extension);
    const email=p.email||p.work_email;if(email&&/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)){const link=add(meta,'a','',email);link.href='mailto:'+email;}
    if(p.work_location)add(meta,'span','',p.work_location);if(p.duty)add(meta,'small','contact-reason',p.duty);card.append(meta);return card;
  }
  function renderContact(container,data){if(!data||(Array.isArray(data)&&data.length===0))return;const block=el('div','contact-block');add(block,'h4','','관련 담당자');(Array.isArray(data)?data:[data]).filter(Boolean).forEach(p=>block.append(makeContactCard(p)));container.append(block);}
  function renderFollowup(container,result){if(result.status!=='needs_info')return;const block=el('div','followup');add(block,'h4','','추가 정보가 필요합니다');const form=el('form','followup-form');const fields=Array.isArray(result.follow_up?.fields)&&result.follow_up.fields.length?result.follow_up.fields:[{key:'details',label:'추가 정보',type:'text'}];fields.forEach(f=>{const label=el('label','field');add(label,'span','',f.label||f.key);let input;if(f.type==='select'&&Array.isArray(f.options)){input=el('select');input.append(el('option','','선택하세요'));input.firstChild.value='';f.options.forEach(opt=>{const v=typeof opt==='string'?opt:opt.value,l=typeof opt==='string'?opt:opt.label;const o=el('option','',l);o.value=v;input.append(o);});}else{input=el('input');input.type=['date','number','text'].includes(f.type)?f.type:'text';}input.name=String(f.key||'details');input.required=f.required!==false;label.append(input);form.append(label);});const btn=add(form,'button','primary-btn','추가 정보 보내기');btn.type='submit';form.addEventListener('submit',e=>{e.preventDefault();if(!form.reportValidity())return;const fields=Object.fromEntries(new FormData(form));sendChat(result.question,{input_data:fields,previous_request_id:result.request_id});});block.append(form);container.append(block);}
  function normalize(raw,question,employee){const outer=raw?.data||raw?.result||raw;const d=outer?.output&&typeof outer.output==='object'?outer.output:outer;if(!d||typeof d!=='object'||typeof d.answer!=='string'||!d.status||!d.request_id)throw Error('서버 응답에 request_id, status, answer가 필요합니다.');return {
    request_id:String(d.request_id),session_id:String(d.session_id||state.sessionId),question:d.question||question,employee_id:employee,answer:d.answer,status:String(d.status),employee:d.employee||null,
    sources:Array.isArray(d.sources)?d.sources:[],sections:Array.isArray(d.sections)?d.sections:[],calculation:d.calculation||null,contact:d.contact||null,follow_up:d.follow_up||d.followup||null,created_at:d.created_at||null,steps:d.steps||[],context:d.context||null,tool_results:d.tool_results||[],webhook_events:d.webhook_events||[],contact_notice:d.contact_notice||''
  };}
  function renderResult(result,pending){state.last=result;state.conversation.push({role:'assistant',content:result.answer,request_id:result.request_id});if(result.session_id&&result.session_id!==state.sessionId)state.sessionId=result.session_id;
    const {row,bubble}=pending;row.classList.remove('pending');empty(bubble);const body=add(bubble,'div','chat-body');for(const piece of result.answer.split(/(\*\*[^*]+\*\*)/g)){if(piece.startsWith('**')&&piece.endsWith('**')){const inner=piece.slice(2,-2),m=inner.match(/^\{(.+)\}$/);if(m)add(body,'strong','chat-heading','['+m[1]+']');else add(body,'strong','',inner);}else body.append(document.createTextNode(piece));}
    const status={answered:'답변 완료',needs_info:'추가 정보 필요',needs_review:'담당자 확인 필요',no_result:'관련 근거 없음',rag_unavailable:'규정 AI 연동 전',error:'처리 오류'};add(bubble,'span','chat-msg-status '+result.status,status[result.status]||'처리 상태 확인');
    renderSections(bubble,result.sections);renderCalculation(bubble,result.calculation);renderContact(bubble,result.contact);if(result.sources.length)renderSources(bubble,result.sources);renderFollowup(bubble,result);renderProcessing(bubble,result);if(result.contact_notice&&result.contact?.length)add(bubble,'small','contact-reason',result.contact_notice);if(result.webhook_events.some(x=>x.status==='failed'))add(bubble,'p','inline-notice','일부 기록을 n8n에 보내지 못했습니다. 대화는 로컬에 저장됩니다.');rememberSession({employee_id:result.employee_id,session_id:state.sessionId});state.sessionPersisted=true;
    const meta=el('div','chat-meta');if(result.request_id)add(meta,'span','','문의번호 '+result.request_id);add(meta,'span','',timestamp(result.created_at));bubble.append(meta);
    $('chatSessionCaption').textContent='대화 진행 중';$('openFeedback').disabled=!result.request_id||result.status==='error'||state.ratedIds.has(result.request_id);
    if(result.employee?.name&&state.confirmedId===result.employee_id){state.employee=result.employee;setBadge(result.employee);}scrollLatest();}
  function renderError(pending,message){if(pending){pending.row.classList.remove('assistant');pending.row.classList.add('system');empty(pending.bubble);add(pending.bubble,'div','chat-body',message);}else addBubble('system',message);scrollLatest();}
  async function sendChat(question,opts={}){const value=String(question||'').trim();if(!value){toast('질문을 입력해 주세요.');return false;}const startsNewChat=state.view==='home'||state.view==='form'||opts.newSession===true;if(state.busy)return false;if(state.closed&&!startsNewChat){toast('종료된 대화입니다. 새 대화를 시작해주세요.');return false;}
    let id;try{id=validateId();}catch(e){if(state.view==='home')warn('inputError',e.message);else toast(e.message);return false;}
    show('inputError',false);show('chatError',false);
    if(state.confirmedId!==id||!state.employee){const ok=await lookupEmployee();if(!ok){if(state.view==='answer')warn('chatError','먼저 직원 정보를 확인해야 합니다. 사번 조회 서버 연결을 확인하세요.');else warn('inputError','먼저 직원 정보를 확인해야 합니다. 사번 조회 서버 연결을 확인하세요.');return false;}}
    if(state.busy)return false;if(startsNewChat)clearSession();state.busy=true;$('openFeedback').disabled=true;$('anotherQuestion').disabled=true;const sentGeneration=state.sessionGeneration;const prev=startsNewChat?null:opts.previous_request_id||state.last?.request_id||null;const payload={employee_id:id,question:value,session_id:state.sessionId};if(state.selectedCategory)payload.category_id=state.selectedCategory;if(prev)payload.previous_request_id=prev;if(opts.input_data)payload.input_data=opts.input_data;
    // 백엔드가 대화 기록을 별도 요청한다면 config.js에서 true 지정 (기본: session_id 기반 관리)
    if(cfg.sendConversationHistory)payload.conversation_history=state.conversation.slice(-20).map(m=>({role:m.role,content:m.content}));
    nav('answer');show('chatEmpty',false);state.stickToBottom=true;addBubble('user',value);state.conversation.push({role:'user',content:value});const pending=addPending();pending.row.classList.add('pending');$('chatSend').disabled=true;$('chatInput').disabled=true;
    try{if(!state.sessionPersisted){const cv=await post('createSessionUrl',{employee_id:id});state.sessionId=cv.id;state.sessionPersisted=true;payload.session_id=cv.id;rememberSession({employee_id:id,session_id:cv.id});}const raw=(cfg.enableStreaming&&validUrl(cfg.chatStreamUrl))?await streamChat(payload,pending):await post('chatWebhookUrl',payload);if(sentGeneration!==state.sessionGeneration||employeeId()!==id){pending.row.remove();return false;}const result=normalize(raw,value,id);renderResult(result,pending);return true;}catch(e){if(sentGeneration===state.sessionGeneration)renderError(pending,getError(e));else pending.row.remove();return false;}finally{state.busy=false;$('anotherQuestion').disabled=false;$('openFeedback').disabled=state.closed||!state.last;$('chatSend').disabled=state.closed;$('chatInput').disabled=state.closed;if(!state.closed)$('chatInput').focus();scrollLatest();}}
  function showForm(which){try{validateId();}catch(e){warn('inputError',e.message);return;}nav('form');show('leaveForm',which==='leave');show('travelForm',which==='travel');$('formHeading').textContent=which==='leave'?'휴가 사용일 계산':'출장 여비 계산';$('formSubtitle').textContent='관련 직원 정보 및 규정 확인 후 예상 결과를 제공합니다.';}
  async function loadHistory(){
    let id;try{id=validateId();}catch(e){nav('home');warn('inputError',e.message);return;}
    if(!(await lookupEmployee())){nav('home');warn('inputError','직원 확인 후 채팅 이력을 조회할 수 있습니다.');return;}
    nav('history');$('historyList').textContent='채팅방 목록을 불러오는 중입니다.';
    try{const data=await post('historyWebhookUrl',{employee_id:id,search:$('historySearch').value.trim()});
      if(!Array.isArray(data?.conversations))throw Error('채팅 목록 API에서 conversations 배열을 받지 못했습니다.');
      state.records=data.conversations;renderHistory();
    }catch(e){$('historyList').textContent=getError(e);}
  }
  function localDate(s){if(!s)return '날짜 미확인';const d=new Date(s);return Number.isNaN(d.getTime())?'날짜 미확인':d.toLocaleString('ko-KR',{month:'long',day:'numeric',hour:'2-digit',minute:'2-digit'});}
  function renderHistory(){
    const root=$('historyList');empty(root);
    if(!state.records.length){add(root,'p','empty-hint','저장된 채팅이 없습니다. 새 대화를 시작해 보세요.');return;}
    state.records.forEach(cv=>{
      const b=el('button','history-entry chat-room-entry');b.type='button';
      const meta=el('div','history-meta');add(meta,'span','',localDate(cv.updated_at));
      add(meta,'span','',cv.turn_count+'회 질문 · '+cv.message_count+'개 메시지');
      const name=state.categories.find(x=>x.id===cv.category_id)?.name;
      if(name)add(meta,'span','',name);
      b.append(meta);add(b,'strong','history-room-title',cv.title||'새 채팅');
      add(b,'p','history-room-preview',cv.preview||'마지막 답변 없음');
      add(b,'span','history-room-action',cv.status==='closed'?'종료된 대화 보기 →':'대화 전체 보기 및 이어서 질문 →');
      b.addEventListener('click',()=>openConversation(cv.session_id));root.append(b);
    });
  }
  async function openConversation(sessionId){
    if(state.busy){toast('진행 중인 질문을 완료한 후 채팅을 열어 주세요.');return;}
    const id=employeeId();$('historyList').setAttribute('aria-busy','true');
    try{const data=await post('conversationWebhookUrl',{employee_id:id,session_id:sessionId});
      if(!data?.conversation||!Array.isArray(data.turns))throw Error('채팅 상세 응답에 conversation과 turns가 필요합니다.');
      if(data.conversation.session_id!==sessionId)throw Error('채팅방 번호가 일치하지 않습니다.');
      clearSession();state.sessionId=sessionId;state.sessionPersisted=true;rememberSession({employee_id:id,session_id:sessionId});state.selectedCategory=data.conversation.category_id||null;
      renderSidebarCategories();nav('answer');
      show('chatEmpty',false);
      for(const turn of data.turns){
        const q=String(turn.question||'');addBubble('user',q);state.conversation.push({role:'user',content:q});
        const result=normalize(turn,q,id);renderResult(result,addPending());
        if(turn.rating!==null&&turn.rating!==undefined)state.ratedIds.add(String(turn.request_id));
      }
      const last=data.turns.at(-1);state.last=last?normalize(last,last.question,id):null;
      if(state.last)$('openFeedback').disabled=state.ratedIds.has(state.last.request_id);
      $('chatSessionCaption').textContent=(data.conversation.title||'지난 채팅').slice(0,30);
      if(data.conversation.status==='closed')showEnded(data.conversation.end_result||{});scrollLatest(true);toast('저장된 채팅 '+data.turns.length+'회 질문을 모두 불러왔습니다.');
    }catch(e){toast(getError(e));}finally{$('historyList').removeAttribute('aria-busy');}
  }
  async function loadContacts(){const root=$('contactDirectory');root.textContent='담당자 정보를 조회하고 있습니다.';try{const id=validateId();if(!(await lookupEmployee()))throw Error('직원 정보 확인 후 조회할 수 있습니다.');const raw=await post('contactWebhookUrl',{employee_id:id,category_id:$('contactTopic').value});const people=Array.isArray(raw)?raw:raw.contacts||raw.contact||raw.data?.contacts||[];const list=Array.isArray(people)?people:[people];empty(root);if(!list.filter(Boolean).length){add(root,'p','empty-hint','담당자가 조회되지 않았습니다. 공통 인사팀 연락처를 확인하세요.');return;}list.filter(Boolean).forEach(p=>root.append(makeContactCard(p)));}catch(e){root.textContent=getError(e);}}
  function setRating(n){state.rating=n;document.querySelectorAll('#ratingButtons button').forEach(b=>{const v=Number(b.dataset.score),on=v<=n;b.classList.toggle('selected',on);b.setAttribute('aria-pressed',String(v===n));});}
  function openFeedback(){if(state.busy||(state.closed&&state.feedbackSaved))return;const result=state.last;if(!result?.request_id){toast('평가할 문의가 없습니다.');return;}if(state.ratedIds.has(result.request_id)){toast('이미 평가를 제출했습니다.');return;}setRating(0);$('feedbackForm').reset();show('feedbackError',false);show('feedbackOverlay',true);$('ratingButtons').querySelector('button').focus();}
  async function submitFeedback(e){e.preventDefault();if(state.busy)return;if(!state.rating){warn('feedbackError','별점을 선택해 주세요.');return;}const result=state.last;if(!result?.request_id)return;const payload={session_id:state.sessionId,request_id:result.request_id,employee_id:result.employee_id,rating:state.rating,error_type:$('feedbackIssue').value,comment:$('feedbackComment').value.trim(),submitted_at:new Date().toISOString()};state.busy=true;$('chatSend').disabled=true;$('sendFeedback').disabled=true;try{const res=await post('feedbackWebhookUrl',payload);if(res.success===false)throw Error('평가 저장에 실패했습니다.');state.ratedIds.add(payload.request_id);show('feedbackOverlay',false);$('openFeedback').disabled=true;showEnded(res);toast(res.webhook_status==='sent'?'평가 저장 및 n8n 전송을 완료했습니다.':'평가는 로컬에 저장했습니다. 아래 n8n 전송 상태를 확인해주세요.');}catch(err){warn('feedbackError',getError(err));}finally{state.busy=false;$('chatSend').disabled=state.closed;$('sendFeedback').disabled=false;}}
  const sessionKey='wonit-hr-active-session';
  function rememberSession(value){try{if(value)sessionStorage.setItem(sessionKey,JSON.stringify(value));else sessionStorage.removeItem(sessionKey);}catch{}}
  function readSession(){try{return JSON.parse(sessionStorage.getItem(sessionKey)||'null');}catch{return null;}}
  function renderProcessing(container,result){
    if(!result.steps.length&&!result.context)return;const detail=el('details','processing-details');add(detail,'summary','','처리 과정 · 호출한 도구 · 컨텍스트');
    for(const step of result.steps)add(detail,'p','',step.label+' · '+step.detail);
    for(const tool of result.tool_results)add(detail,'p','tool-label','도구: '+tool.tool_id+' · '+tool.status);
    if(result.context){const sub=el('details');add(sub,'summary','','질문에 사용한 컨텍스트');add(sub,'pre','context-json',JSON.stringify(result.context,null,2));detail.append(sub);}container.append(detail);
  }
  function showEnded(result){state.closed=true;state.feedbackSaved=result.score!=null||result.rating!=null||!!result.comment;$('chatSend').disabled=true;$('chatInput').disabled=true;$('openFeedback').disabled=true;$('chatSessionCaption').textContent='종료된 대화';const notice=$('endNotice');empty(notice);add(notice,'span','',result.message||'종료된 대화입니다. 새 대화를 시작해주세요.');show('endNotice',true);
    if(!state.feedbackSaved&&state.last){const review=add(notice,'button','outline-btn','만족도 평가 남기기');review.type='button';review.addEventListener('click',openFeedback);}
    if(['failed','pending','not_configured'].includes(result.webhook_status)){const retry=add(notice,'button','outline-btn','n8n 다시 전송');retry.type='button';retry.addEventListener('click',async()=>{retry.disabled=true;try{showEnded(await post('retryWebhookUrl',{employee_id:employeeId(),session_id:state.sessionId}));}catch(e){toast(getError(e));retry.disabled=false;}});}}
  async function directorySearch(append=false){
    const button=$('directorySearch');button.disabled=true;try{const offset=append?Number($('directoryMore').dataset.offset||0):0;const params=new URLSearchParams({query:$('directoryQuery').value,department_id:$('directoryDepartment').value,limit:'12',offset:String(offset)});if(!params.get('department_id'))params.delete('department_id');const response=await fetch('/api/employees?'+params);if(!response.ok)throw Error('사원 검색에 실패했습니다.');const data=await response.json();if(!append)empty($('directoryResults'));
      for(const profile of data.items){const card=makeContactCard(profile);const choose=add(card,'button','outline-btn','이 사번으로 새 대화');choose.type='button';choose.addEventListener('click',()=>{if(state.busy)return;clearSession();$('employeeId').value=profile.employee_id;onEmployeeInput();lookupEmployee();$('directoryDialog').close();nav('home');});$('directoryResults').append(card);}
      $('directoryCount').textContent=`총 ${data.total}명 · ${offset+data.items.length}명 표시`;$('directoryMore').dataset.offset=String(offset+data.items.length);show('directoryMore',offset+data.items.length<data.total);
    }catch(e){$('directoryCount').textContent=getError(e);}finally{button.disabled=false;}}
  function initDirectory(){
    $('openDirectory').addEventListener('click',async()=>{if(state.busy)return;show('directoryMore',false);empty($('directoryResults'));$('directoryQuery').value='';$('directoryCount').textContent='이름·사번·부서를 입력하고 검색하면 임직원 정보가 표시됩니다.';$('directoryDialog').showModal();try{const response=await fetch('/api/departments');if(!response.ok)throw Error('부서 조회에 실패했습니다.');const departments=await response.json();$('directoryDepartment').replaceChildren(new Option('전체 부서',''),...departments.map(d=>new Option(d.dept_name,d.dept_id)));}catch(e){$('directoryCount').textContent=getError(e);}});
    $('closeDirectory').addEventListener('click',()=>$('directoryDialog').close());$('directoryForm').addEventListener('submit',e=>{e.preventDefault();if(!$('directoryQuery').value.trim()&&!$('directoryDepartment').value){empty($('directoryResults'));show('directoryMore',false);$('directoryCount').textContent='검색어(이름·사번·부서)를 입력하거나 부서를 선택해 주세요.';return;}directorySearch();});$('directoryMore').addEventListener('click',()=>directorySearch(true));
  }
  function init(){
    document.body.classList.add('home-active');
    // 테스트 버전의 화면을 실제 API 모드로 전환할 경우 테스트용 안내는 숨깁니다.
    if(!cfg.testMode){
      document.querySelector('.test-header-chip')?.remove();
      document.querySelector('.test-check-panel')?.remove();
      const foot=document.querySelector('.chat-footer>span');
      if(foot)foot.textContent='AI 답변은 실제 사내 규정과 담당자 확인이 필요할 수 있습니다.';
    }
    if(cfg.testMode){document.querySelectorAll('[data-test-id]').forEach(b=>b.addEventListener('click',()=>{const id=b.dataset.testId;$('employeeId').value=id;onEmployeeInput();lookupEmployee();toast(id+' 가상 직원 조회를 요청했습니다.');}));}
    {const field=$('employeeId'),nativeValue=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value');Object.defineProperty(field,'value',{get(){return nativeValue.get.call(field);},set(v){nativeValue.set.call(field,String(v??'').toUpperCase().replace(/^(WON|KDN)/,'').replace(/\D/g,''));},configurable:true});field.addEventListener('input',()=>{field.value=nativeValue.get.call(field);});}
    $('employeeId').addEventListener('input',onEmployeeInput);$('employeeId').addEventListener('change',lookupEmployee);$('employeeId').addEventListener('blur',lookupEmployee);
    $('searchForm').addEventListener('submit',e=>{e.preventDefault();sendChat($('question').value);});
    $('categoryToggle').addEventListener('click',()=>{const open=$('categoryToggle').getAttribute('aria-expanded')==='true';$('categoryToggle').setAttribute('aria-expanded',String(!open));show('sidebarCategoryList',!open);});
    $('clearCategory').addEventListener('click',()=>setCategory(null));$('categorySearch').addEventListener('input',renderCategoryList);$('closePdf').addEventListener('click',closeRegulation);$('pdfOverlay').addEventListener('click',e=>{if(e.target===$('pdfOverlay'))closeRegulation();});
    $('sidebarBrand').addEventListener('click',()=>nav('home'));$('openRulesBtn').addEventListener('click',()=>nav('rules'));
    document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>{const v=b.dataset.view;if(v==='history')loadHistory();else nav(v);}));
    document.querySelectorAll('[data-query]').forEach(b=>b.addEventListener('click',()=>{const q=b.dataset.query;$('question').value=q;sendChat(q);}));
    document.querySelectorAll('[data-action]').forEach(b=>b.addEventListener('click',()=>{const v=b.dataset.action;if(v==='balance')sendChat('제 연차가 며칠 남았나요?');else if(v==='leave'||v==='travel')showForm(v);else if(v==='contact')nav('contacts');}));
    $('anotherQuestion').addEventListener('click',()=>{if(state.busy)return;clearSession(true);$('chatInput').focus();scrollLatest(true);});
    $('chatComposer').addEventListener('submit',e=>{e.preventDefault();const v=$('chatInput').value.trim();if(!v)return;sendChat(v).then(ok=>{if(ok)$('chatInput').value='';});});
    $('chatInput').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();$('chatComposer').requestSubmit();}});
    $('chatMessages').addEventListener('scroll',onChatScroll);$('jumpToLatest').addEventListener('click',()=>{state.stickToBottom=true;scrollLatest(true);show('jumpToLatest',false);});
    $('formBack').addEventListener('click',()=>nav('home'));
    $('leaveForm').addEventListener('submit',e=>{e.preventDefault();show('leaveError',false);const s=$('leaveStart').value,to=$('leaveEnd').value,days=Number($('leaveDays').value);if(!s||!to||to<s||!days||days<0||days>366){warn('leaveError','휴가 시작일과 종료일을 확인하세요.');return;}sendChat('선택한 기간에 연차 사용 시 예상 차감일수와 잔여 연차를 알려주세요.',{input_data:{task:'leave_period',start_date:s,end_date:to,requested_days:days}});});
    $('travelForm').addEventListener('submit',e=>{e.preventDefault();show('travelError',false);const dest=$('travelDestination').value.trim(),s=$('travelStart').value,to=$('travelEnd').value,transport=$('travelTransport').value,fare=$('travelFare').value;if(!dest||!s||!to||!transport||to<s){warn('travelError','출장지, 기간, 교통수단을 확인하세요.');return;}const info={task:'travel_estimate',trip_type:$('travelType').value,destination_city:dest,start_date:s,end_date:to,transport_mode:({train:'public_transport',bus:'public_transport',air:'public_transport',car:'private_car',company:'company_car',rental:'rental_car'})[transport]||'public_transport'};if(fare!=='')info.transport_cost_krw=Number(fare);const numeric={travelDistance:'distance_km',travelNights:'lodging_nights',travelMeals:'meal_days',travelLodging:'lodging_cost_per_night'};for(const [id,key] of Object.entries(numeric))if($(id).value!=='')info[key]=Number($(id).value);if($('travelSameCity').value!=='')info.same_city=$('travelSameCity').value==='true';if($('travelRegion').value)info.domestic_region_type=$('travelRegion').value;if($('travelCountry').value.trim())info.destination_country=$('travelCountry').value.trim();sendChat(dest+' 출장 예상 여비를 계산해 주세요.',{input_data:info});});
    $('refreshHistory').addEventListener('click',loadHistory);let searchTimer; $('historySearch').addEventListener('input',()=>{clearTimeout(searchTimer);searchTimer=setTimeout(loadHistory,300);});$('historyNewChat').addEventListener('click',()=>{clearSession(true);nav('answer');$('chatInput').focus();});$('findContact').addEventListener('click',loadContacts);
    $('openFeedback').addEventListener('click',openFeedback);$('closeFeedback').addEventListener('click',()=>{if(!state.busy)show('feedbackOverlay',false);});$('feedbackOverlay').addEventListener('click',e=>{if(e.target===$('feedbackOverlay'))show('feedbackOverlay',false);});
    document.querySelectorAll('#ratingButtons button').forEach(b=>b.addEventListener('click',()=>setRating(Number(b.dataset.score))));$('feedbackForm').addEventListener('submit',submitFeedback);
    $('mobileMenu').addEventListener('click',()=>{$('sidebar').classList.add('open');show('mobileShade',true);});$('mobileShade').addEventListener('click',closeMobile);
    window.addEventListener('keydown',e=>{if(e.key==='Escape'&&!state.busy){show('feedbackOverlay',false);closeRegulation();closeMobile();}if(e.key==='Tab'){const modal=!$('feedbackOverlay').classList.contains('hidden')?$('feedbackOverlay'):!$('pdfOverlay').classList.contains('hidden')?$('pdfOverlay'):null;if(modal){const nodes=[...modal.querySelectorAll('button:not(:disabled),a[href],input,select,textarea')];const first=nodes[0],last=nodes.at(-1);if(e.shiftKey&&document.activeElement===first){last?.focus();e.preventDefault();}else if(!e.shiftKey&&document.activeElement===last){first?.focus();e.preventDefault();}}}});
    const saved=readSession();let savedView=null;try{savedView=sessionStorage.getItem('wonit-hr-view');}catch{}const restoreView=()=>{if(['home','rules','history','contacts','help'].includes(savedView)){if(savedView==='history'){if(saved?.employee_id)loadHistory();}else nav(savedView);}};clearSession();Promise.all([loadCategories(),loadRegulations(),loadQuestionBank()]).then(async()=>{renderRulesCategoryTabs();renderQuestionExamples();if(saved?.employee_id&&saved?.session_id){$('employeeId').value=saved.employee_id;if(await lookupEmployee())await openConversation(saved.session_id);}else{$('employeeId').value='';onEmployeeInput();}restoreView();});setBadge(null);checkHealth();initDirectory();
  }
  document.addEventListener('DOMContentLoaded',init);
})();
