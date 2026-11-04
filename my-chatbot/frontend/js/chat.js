import { api } from './api.js';

const $ = (id) => document.getElementById(id);
const state = { conversationId: null, selectedTool: null, tools: [], busy: false, closed: false, ready: false, answerProvider: 'demo' };
const storageKey = 'abc-hr-conversation';
let profileRequest = 0;
const directoryState = {offset:0,busy:false,total:0,pending:false};
const initialSteps = [
    ['receive', '질문 접수', 'FastAPI에서 입력 확인'],
    ['route', '도구 선택', '분야 자동 선택 또는 직접 지정'],
    ['tools', '도구 실행', '등록된 분야별 검색·업무 도구'],
    ['context', '컨텍스트 구성', '질문 · 이전 대화 · 도구 결과'],
    ['generate', 'Ollama 답변 생성', '검색 근거 기반 답변 생성'],
    ['return', '답변 출력', '답변과 문서 출처 표시'],
].map(([key, label, detail]) => ({ key, label, detail, status: 'waiting' }));

function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
}

// 답변 안의 **강조** 만 굵게 표시합니다(HTML은 해석하지 않고 DOM으로만 만듭니다).
function setRichText(node, text) {
    node.textContent = '';
    String(text).split(/(\*\*[^*\n]+\*\*)/).forEach((part) => {
        if (/^\*\*[^*\n]+\*\*$/.test(part)) node.append(element('strong', 'emphasis', part.slice(2, -2)));
        else if (part) node.append(document.createTextNode(part));
    });
}

function remember(id) {
    try {
        if (id) sessionStorage.setItem(storageKey, id);
        else sessionStorage.removeItem(storageKey);
    } catch { /* 저장이 차단되어도 현재 창에서 대화할 수 있습니다. */ }
}

function updateControls() {
    $('send-button').disabled = !state.ready || state.busy || state.closed;
    $('user-input').disabled = state.busy || state.closed || !state.ready;
    $('new-chat').disabled = state.busy;
    $('end-chat').disabled = !state.conversationId || state.busy || state.closed;
    $('employee-id').disabled = !!state.conversationId || state.busy;
    $('submit-feedback').disabled = state.busy;
    $('cancel-feedback').disabled = state.busy;
    $('open-directory').disabled = state.busy;
    document.querySelectorAll('.directory-select').forEach((button) => { button.disabled = state.busy; });
    $('send-button').querySelector('span').textContent = state.busy ? '처리 중' : '보내기';
    document.querySelectorAll('.domain-button, .suggestions button').forEach((button) => {
        button.disabled = state.busy || state.closed || !state.ready;
    });
}

function personCard(profile, selectable=false) {
    const card = element('div','person-card');
    const avatar = element('div','person-avatar');
    avatar.textContent = profile.name.slice(0,1);
    if (profile.image_url?.startsWith('/api/users/') && profile.image_url.endsWith('/photo')) {
        const image = document.createElement('img');
        image.src = profile.image_url;
        image.alt = profile.photo_alt || `${profile.name} 프로필`;
        image.title = profile.photo_alt || '';
        image.loading = 'lazy';
        image.referrerPolicy = 'no-referrer';
        image.addEventListener('error',() => {
            // 외부 사진을 불러오지 못하면 로컬 아이콘, 그것도 실패하면 이름 첫 글자를 보여줍니다.
            if (!image.dataset.fallback) {
                image.dataset.fallback = '1';
                image.src = `${profile.image_url}?fallback=true`;
                return;
            }
            avatar.textContent = profile.name.slice(0,1);
        });
        avatar.replaceChildren(image);
    }
    const information = element('div','person-information');
    information.append(element('strong','',`${profile.name} · ${profile.employee_id}`));
    information.append(element('p','',[profile.department,profile.job_title,profile.grade].filter(Boolean).join(' · ')));
    const contacts = [profile.work_email,profile.extension_number ? `내선 ${profile.extension_number}` : '',profile.work_location].filter(Boolean);
    if (contacts.length) information.append(element('p','person-contact',contacts.join(' · ')));
    if (profile.roles?.length) information.append(element('p','person-roles',`업무 역할: ${profile.roles.join(', ')}`));
    card.append(avatar,information);
    if (selectable) {
        const select = element('button','button-secondary directory-select','이 사번으로 새 대화');
        select.type = 'button';
        select.disabled = state.busy;
        select.addEventListener('click',() => {
            if (state.busy) return;
            $('new-chat').click();
            $('employee-id').value = profile.employee_id;
            $('employee-dialog').close();
            loadUserProfile(profile.employee_id);
        });
        card.append(select);
    }
    return card;
}

async function loadUserProfile(employeeId) {
    const sequence = ++profileRequest;
    const id = employeeId.trim();
    const target = $('user-card');
    if (!id) { target.hidden = true; return; }
    try {
        const result = await api.user(id);
        if (sequence !== profileRequest) return;
        target.replaceChildren(result.profile ? personCard(result.profile) : element('p','profile-note','등록된 사원 정보가 없습니다. 사번을 확인해주세요.'));
    } catch (error) {
        if (sequence !== profileRequest) return;
        target.replaceChildren(element('p','profile-note',error.message));
    }
    target.hidden = false;
}

async function searchEmployees(append=false) {
    if (directoryState.busy) { directoryState.pending = true; return; }
    directoryState.busy = true;
    $('directory-more').disabled = true;
    try {
        if (!append) directoryState.offset = 0;
        const result = await api.employees($('employee-query').value.trim(),$('employee-department').value,directoryState.offset);
        if (!append) $('employee-results').replaceChildren();
        result.items.forEach((profile) => $('employee-results').append(personCard(profile,true)));
        directoryState.offset += result.items.length;
        directoryState.total = result.total;
        $('directory-count').textContent = result.total ? `총 ${result.total}명 · ${directoryState.offset}명 표시` : '조건에 맞는 사원이 없습니다.';
        $('directory-more').hidden = directoryState.offset >= result.total;
    } catch (error) {
        $('directory-count').textContent = error.message;
    } finally {
        directoryState.busy = false;
        $('directory-more').disabled = false;
        if (directoryState.pending) { directoryState.pending = false; searchEmployees(); }
    }
}

$('employee-id').addEventListener('change',() => loadUserProfile($('employee-id').value));
$('open-directory').addEventListener('click',async () => {
    $('employee-dialog').showModal();
    $('directory-count').textContent = '사원 정보를 불러오고 있습니다…';
    try {
        const departments = await api.departments();
        const selected = $('employee-department').value;
        $('employee-department').replaceChildren(new Option('전체 부서',''),...departments.map((item) =>
            new Option(`${item.dept_name} · ${item.employee_count}명${item.location ? ' · '+item.location : ''}${item.main_extension ? ' · 내선 '+item.main_extension : ''}`,item.dept_id)));
        $('employee-department').value = selected;
        await searchEmployees();
    } catch (error) { $('directory-count').textContent = error.message; }
});
$('close-directory').addEventListener('click',() => $('employee-dialog').close());
$('employee-search-form').addEventListener('submit',(event) => { event.preventDefault(); searchEmployees(); });
$('employee-department').addEventListener('change',() => searchEmployees());
$('directory-more').addEventListener('click',() => searchEmployees(true));

function scrollToLatest() {
    $('chat-scroll').scrollTop = $('chat-scroll').scrollHeight;
}

function showWebhookWarning(events) {
    if (events?.some((item) => item.status === 'failed')) {
        const note = element('p','webhook-note','대화는 계속할 수 있지만 일부 기록을 n8n에 전송하지 못했습니다.');
        note.setAttribute('role','status');
        $('messages').append(note);
    }
}

function appendMessage(content, role, sources = [], escalation = null) {
    $('welcome').hidden = true;
    const row = element('article', `message ${role}`);
    row.append(element('div', 'message-label', role === 'user' ? '나' : role === 'error' ? '안내' : `ABC ASSISTANT · ${state.answerProvider.toUpperCase()}`));
    const body = element('div', 'message-content');
    if (role === 'assistant') setRichText(body, content); else body.textContent = content;
    row.append(body);
    if (sources.length) {
        const evidence = element('details', 'message-source');
        evidence.append(element('summary', '', `검색된 문서 근거 ${sources.length}개 보기`));
        const labels = [...new Set(sources.map(sourceLabel))];
        labels.forEach((label) => evidence.append(element('p', '', label)));
        row.append(evidence);
    }
    if (escalation && escalation.status !== 'not_needed') {
        const handoff = element('section','contact-escalation');
        handoff.setAttribute('aria-label','관련 업무 담당자');
        handoff.append(element('strong','contact-escalation-title','관련 업무 담당자'),element('p','contact-escalation-note',escalation.message));
        const contacts = element('div','contact-grid');
        (escalation.contacts || []).forEach((item) => {
            const contact = element('div','recommended-contact');
            contact.append(personCard(item.employee),element('p','contact-match-reason',item.reason));
            if (!item.employee.extension_number) {
                contact.append(element('p','contact-match-reason',item.employee.department_extension
                    ? `개인 내선 미등록 · 부서 대표 내선 ${item.employee.department_extension}` : '전화 정보가 등록되어 있지 않습니다.'));
            }
            contacts.append(contact);
        });
        handoff.append(contacts);
        row.append(handoff);
    }
    $('messages').append(row);
    scrollToLatest();
    return row;
}

function sourceLabel(source) {
    const pages = source.pages?.length ? source.pages.join(', ') : source.page;
    return `${source.document}${pages != null ? ` · p.${pages}` : ''}${source.section ? ` · ${source.section}` : ''}`;
}

function renderSteps(steps = initialSteps) {
    $('processing-steps').replaceChildren(...steps.map((step, index) => {
        const row = element('li');
        row.append(element('span', `step-number ${step.status}`, step.status === 'done' ? '✓' : String(index + 1).padStart(2, '0')));
        const text = element('div', 'step-text');
        text.append(element('strong', '', step.label), element('p', '', step.detail));
        row.append(text);
        return row;
    }));
}

function renderDetails(data) {
    renderSteps(data.steps);
    $('tool-count').textContent = data.tool_results.length;
    $('tool-results').replaceChildren(...data.tool_results.map((result) => {
        const item = element('div', 'tool-result');
        item.append(element('strong', '', state.tools.find((tool) => tool.id === result.tool_id)?.name || result.tool_id));
        item.append(element('span', '', ({ok: '검색·조회 완료', no_result: '관련 근거 없음', needs_input: '추가 정보 필요', error: '실행 오류'})[result.status] || result.status));
        return item;
    }));
    if (!data.tool_results.length) $('tool-results').append(element('p', 'empty-note', '선택된 도구가 없습니다. 분야를 직접 지정할 수 있습니다.'));
    $('source-list').replaceChildren(...data.sources.map((source) => {
        const item = element('details', 'source-item');
        item.append(element('summary', '', sourceLabel(source)), element('p', 'source-excerpt', source.text));
        return item;
    }));
    if (!data.sources.length) {
        const people = data.tool_results.some((item) => item.data?.employee || item.data?.hr_contacts?.length || item.data?.departments?.length);
        $('source-list').append(element('p', 'empty-note', people ? '연결된 사원·부서 정보로 답변했습니다.' : '검색 기준에 맞는 문서 근거가 없습니다.'));
    }
    $('context-output').textContent = JSON.stringify(data.context, null, 2);
}

function resetDetails() {
    renderSteps();
    $('tool-count').textContent = '0';
    $('tool-results').replaceChildren(element('p', 'empty-note', '질문을 보내면 선택된 분야가 표시됩니다.'));
    $('source-list').replaceChildren(element('p', 'empty-note', '아직 검색된 출처가 없습니다.'));
    $('context-output').textContent = '질문·이전 대화·도구 결과가 이곳에 모입니다.';
}

function selectDomain(id) {
    state.selectedTool = id;
    document.querySelectorAll('.domain-button').forEach((button) => {
        const active = button.dataset.toolId === (id || '');
        button.classList.toggle('active', active);
        button.setAttribute('aria-pressed', String(active));
    });
    const name = state.tools.find((tool) => tool.id === id)?.name;
    $('selected-domain').textContent = name ? `${name} · 직접 선택` : '분야 자동 선택 · Ollama';
}

function renderDomains() {
    const icons = ['↗', '◷', '◇', '▤', '◎', '⌘', '▦', '✧', '➤'];
    const items = [{ id: '', name: '분야 자동 선택' }, ...state.tools];
    $('domain-list').replaceChildren(...items.map((tool, index) => {
        const button = element('button', 'domain-button');
        button.type = 'button';
        button.dataset.toolId = tool.id;
        button.append(element('span', 'domain-icon', index === 0 ? '✳' : icons[(index - 1) % icons.length]), element('span', '', tool.name));
        button.addEventListener('click', () => selectDomain(tool.id || null));
        return button;
    }));
    selectDomain(null);
}

function showClosed(result) {
    state.closed = true;
    $('session-label').textContent = '종료된 대화';
    $('closed-notice').hidden = false;
    $('closed-notice').textContent = result?.message || '종료된 대화입니다. 새 대화를 시작해주세요.';
    if (['failed', 'pending', 'not_configured'].includes(result?.webhook_status)) {
        const retry = element('button', 'button-secondary', 'n8n 다시 전송');
        retry.type = 'button';
        retry.addEventListener('click', async () => {
            if (state.busy) return;
            state.busy = true;
            retry.disabled = true;
            updateControls();
            try { showClosed(await api.retryWebhook(state.conversationId)); }
            catch (error) { retry.disabled = false; appendMessage(error.message, 'error'); }
            finally { state.busy = false; updateControls(); }
        });
        $('closed-notice').append(document.createElement('br'), retry);
    }
    updateControls();
}

$('new-chat').addEventListener('click', () => {
    state.conversationId = null;
    state.closed = false;
    remember(null);
    $('messages').replaceChildren();
    $('welcome').hidden = false;
    $('closed-notice').hidden = true;
    $('session-label').textContent = '새 대화';
    $('user-input').value = '';
    selectDomain(null);
    resetDetails();
    updateControls();
    $('user-input').focus();
    loadUserProfile($('employee-id').value);
});

document.querySelectorAll('[data-question]').forEach((button) => {
    button.addEventListener('click', () => {
        selectDomain(null);
        $('user-input').value = button.dataset.question;
        $('user-input').focus();
    });
});

$('user-input').addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && event.keyCode !== 229) {
        event.preventDefault();
        if (!state.busy && !state.closed && state.ready) $('chat-form').requestSubmit();
    }
});

$('chat-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const message = $('user-input').value.trim();
    const employeeId = $('employee-id').value.trim();
    if (!state.ready || !message || state.busy || state.closed) return;
    if (!employeeId) { $('employee-id').focus(); return; }
    state.busy = true;
    updateControls();
    const userRow = appendMessage(message, 'user');
    $('user-input').value = '';
    const pending = element('p', 'pending', '관련 규정을 검색하고 답변을 준비하고 있습니다…');
    $('messages').append(pending);
    scrollToLatest();
    let streamRow = null;
    try {
        if (!state.conversationId) {
            const conversation = await api.createConversation(employeeId);
            state.conversationId = conversation.id;
            remember(conversation.id);
            showWebhookWarning(conversation.webhook_events);
        }
        const data = await api.chatStream({
            message, employee_id: employeeId,
            conversation_id: state.conversationId, tool_id: state.selectedTool,
        }, {
            status: (text) => { pending.textContent = text; },
            delta: (text) => {
                // 미리보기: 생성되는 문장을 바로 보여주고, 끝나면 검증된 최종 답변으로 교체합니다.
                if (!streamRow) {
                    pending.hidden = true;
                    streamRow = appendMessage('', 'assistant');
                    streamRow.classList.add('streaming');
                }
                setRichText(streamRow.querySelector('.message-content'), text);
                scrollToLatest();
            },
        });
        streamRow?.remove();
        streamRow = null;
        $('session-label').textContent = `대화 ${data.conversation_id.slice(0, 8)}`;
        appendMessage(data.answer, 'assistant', data.sources, data.contact_escalation);
        renderDetails(data);
        showWebhookWarning(data.webhook_events);
    } catch (error) {
        streamRow?.remove();
        userRow.remove();
        $('user-input').value = message;
        appendMessage(error.message, 'error');
        if (error.status === 404) {
            state.conversationId = null;
            remember(null);
            $('session-label').textContent = '다시 전송하면 새 대화를 시작합니다';
        } else if (error.status === 409 && error.code !== 'conversation_conflict') {
            showClosed({ message: `${error.message} 새 대화를 시작해주세요.` });
        }
    } finally {
        pending.remove();
        state.busy = false;
        updateControls();
        $('user-input').focus();
        scrollToLatest();
    }
});

$('end-chat').addEventListener('click', () => {
    $('feedback-form').reset();
    $('feedback-error').textContent = '';
    $('feedback-dialog').showModal();
});
$('cancel-feedback').addEventListener('click', () => $('feedback-dialog').close());
$('feedback-dialog').addEventListener('cancel', (event) => { if (state.busy) event.preventDefault(); });
$('feedback-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (state.busy || !state.conversationId || state.closed) return;
    state.busy = true;
    updateControls();
    $('feedback-error').textContent = '';
    try {
        const data = new FormData($('feedback-form'));
        const result = await api.endConversation(state.conversationId, {
            rating: data.get('rating') || null, comment: $('feedback-comment').value.trim(),
        });
        showClosed(result);
        $('feedback-dialog').close();
        $('new-chat').focus();
    } catch (error) {
        $('feedback-error').textContent = error.message;
    } finally {
        state.busy = false;
        updateControls();
        if (state.closed) $('new-chat').focus();
    }
});

async function initialize() {
    renderSteps();
    try {
        const [health, tools] = await Promise.all([api.health(), api.tools()]);
        state.answerProvider = health.answer_provider;
        $('mode-badge').textContent = health.answer_provider.toUpperCase();
        const persistent = ['sqlite', 'mysql'].includes(health.storage);
        $('storage-label').textContent = health.storage === 'sqlite' ? 'SQLite · 연결됨' : health.storage === 'mysql' ? 'MySQL · 연결됨' : '메모리 · 테스트용';
        $('storage-description').textContent = persistent
            ? `대화를 보관하고 연결된 사원 정보를 조회합니다. 답변에는 최근 메시지 ${health.history_message_limit}개를 사용합니다.`
            : '현재 메모리 모드입니다. 서버 재시작 시 대화 기록이 사라집니다.';
        $('feedback-storage-note').textContent = health.integrations.n8n === 'configured'
            ? '제출하면 평가·기본 사용자 정보·최근 대화를 n8n으로 전송합니다.'
            : '평가를 저장합니다. n8n 주소가 비어 있어 외부로 전송하지 않습니다.';
        $('mode-notice').textContent = 'Ollama 도구 선택 → MCP 도구 호출 → ChromaDB 검색 → 사용자 정보·최근 대화 기반 답변';
        if (health.integrations.n8n === 'configured') {
            $('mode-notice').textContent += ' · 대화 시작·질문·답변·만족도를 n8n에 기록합니다.';
        }
        $('tool-total').textContent = `${tools.length} TOOLS`;
        state.tools = tools;
        renderDomains();
        $('connection').textContent = '로컬 API 연결됨';
        $('connection').classList.add('online');
        state.ready = health.chat_available;
        if (!state.ready) throw new Error('저장소 연결 또는 모델 설정을 확인해주세요.');
        let savedId;
        try { savedId = sessionStorage.getItem(storageKey); } catch { /* 선택적 복원 */ }
        if (savedId) {
            try {
                const conversation = await api.getConversation(savedId);
                state.conversationId = conversation.id;
                $('employee-id').value = conversation.employee_id;
                $('session-label').textContent = `대화 ${conversation.id.slice(0, 8)}`;
                conversation.messages.forEach((item) => appendMessage(item.content, item.role, item.sources, item.contact_escalation));
                if (conversation.status === 'closed') showClosed(conversation.end_result);
            } catch (error) {
                remember(null);
                if (error.status !== 404 && error.status !== 422) throw error;
            }
        }
        await loadUserProfile($('employee-id').value);
    } catch (error) {
        state.ready = false;
        $('connection').textContent = '연결 확인 필요';
        $('connection').classList.remove('online');
        appendMessage(`${error.message} 서버 실행 상태를 확인한 뒤 새로고침해주세요.`, 'error');
    } finally {
        updateControls();
    }
}

initialize();
