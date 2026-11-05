// FastAPI와 통신하는 코드는 이 파일에서 관리합니다.
async function request(path, options = {}) {
    let response;
    try {
        response = await fetch(`/api${path}`, {
            ...options,
            headers: { 'Content-Type': 'application/json', ...options.headers },
            signal: AbortSignal.timeout(path === '/chat' ? 300000 : 30000),
        });
    } catch {
        throw new Error('서버 연결을 확인해주세요. 요청이 처리되었는지 확인한 뒤 다시 시도해주세요.');
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        const detail = typeof data.detail === 'string' ? data.detail : '입력값 또는 서버 상태를 확인해주세요.';
        const error = new Error(detail);
        error.status = response.status;
        error.code = data.code;
        throw error;
    }
    return data;
}

// 답변을 만드는 동안 진행 문구(status)와 미리보기(delta)를 받고, 마지막에 검증된 최종 응답(final)을 돌려줍니다.
async function streamChat(payload, handlers = {}) {
    let response;
    try {
        response = await fetch('/api/chat/stream', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
            signal: AbortSignal.timeout(300000),
        });
    } catch {
        throw new Error('서버 연결을 확인해주세요. 요청이 처리되었는지 확인한 뒤 다시 시도해주세요.');
    }
    if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        const error = new Error(typeof data.detail === 'string' ? data.detail : '입력값 또는 서버 상태를 확인해주세요.');
        error.status = response.status;
        error.code = data.code;
        throw error;
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let final = null;
    const handle = (block) => {
        const lines = block.split('\n');
        const event = lines.find((line) => line.startsWith('event: '))?.slice(7);
        const dataLine = lines.find((line) => line.startsWith('data: '))?.slice(6);
        if (!event || dataLine === undefined) return;
        const data = JSON.parse(dataLine);
        if (event === 'final') final = data;
        else if (event === 'error') {
            const error = new Error(data.detail || '답변을 만들지 못했습니다.');
            error.status = data.status;
            throw error;
        } else handlers[event]?.(data);
    };
    try {
        for (;;) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            let index;
            while ((index = buffer.indexOf('\n\n')) >= 0) {
                handle(buffer.slice(0, index));
                buffer = buffer.slice(index + 2);
            }
        }
    } catch (error) {
        if (error.status !== undefined) throw error;
        throw new Error('응답을 받는 중 연결이 끊겼습니다. 대화 기록을 확인한 뒤 다시 시도해주세요.');
    }
    if (!final) throw new Error('응답이 중간에 끊겼습니다. 다시 시도해주세요.');
    return final;
}

export const api = {
    health: () => request('/health'),
    tools: () => request('/tools'),
    user: (id) => request(`/users/${encodeURIComponent(id)}`),
    employees: (query='',departmentId='',offset=0) => request('/employees?' + new URLSearchParams({
        query, ...(departmentId ? {department_id:departmentId} : {}), offset:String(offset),limit:'12',
    })),
    departments: () => request('/departments'),
    createConversation: (employeeId) => request('/conversations', {
        method: 'POST', body: JSON.stringify({ employee_id: employeeId }),
    }),
    getConversation: (id) => request(`/conversations/${encodeURIComponent(id)}`),
    chat: (payload) => request('/chat', { method: 'POST', body: JSON.stringify(payload) }),
    chatStream: streamChat,
    endConversation: (id, payload) => request(`/conversations/${encodeURIComponent(id)}/end`, {
        method: 'POST', body: JSON.stringify(payload),
    }),
    retryWebhook: (id) => request(`/conversations/${encodeURIComponent(id)}/webhook/retry`, {method:'POST'}),
};
