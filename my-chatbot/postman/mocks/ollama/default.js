// Local contract stand-in for Ollama POST /api/chat. No real model is run.
// Contract: https://github.com/ollama/ollama/blob/main/docs/api.md
const http = require('http');
let lastRequest = {};
async function readBody(req) {
    if (req.body !== undefined) return req.body;
    let raw = '';
    for await (const chunk of req) raw += chunk;
    try { return JSON.parse(raw); } catch { return null; }
}
const server = http.createServer(async (req, res) => {
    const send = (status, data) => {
        res.writeHead(status, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(data));
    };
    if (req.method === 'GET' && req.url === '/__test/last-request') {
        return send(200, lastRequest);
    }
    if (req.method !== 'POST' || req.url !== '/api/chat') {
        return send(501, { error: 'This local stand-in only models POST /api/chat' });
    }
    const body = await readBody(req);
    if (!body || typeof body.model !== 'string' || !body.model || body.stream !== false || !Array.isArray(body.messages)
        || body.messages.some(item => !['system', 'user', 'assistant'].includes(item.role) || typeof item.content !== 'string')) {
        return send(400, { error: 'Invalid chat contract' });
    }
    lastRequest = body;
    const question = body.messages[body.messages.length - 1].content;
    if (question.includes('__simulate_failure__')) return send(500, { error: 'Simulated model failure' });
    if (question.includes('__simulate_malformed__')) return send(200, { message: {} });
    if (question.includes('__simulate_delay__')) await new Promise(resolve => setTimeout(resolve, 250));
    if (body.format?.properties?.tool_id) {
        const choices = body.format.properties.tool_id.enum;
        const tool_id = choices.includes('work_labor') ? 'work_labor' : choices[0];
        return send(200, { message: { role: 'assistant', content: JSON.stringify({ tool_id, arguments: {} }) }, done: true });
    }
    if (body.format?.properties?.points) {
        return send(200, { message: { role: 'assistant', content: JSON.stringify({ coverage: 'direct', summary: '제공된 규정에 따른 안내입니다.', points: [{ text: '제공된 규정에 따른 안내입니다.', source_id: 'S1', evidence_id: 'E1' }] }) }, done: true });
    }
    return send(200, { model: body.model, message: { role: 'assistant', content: '모의 Ollama 답변입니다.' }, done: true });
});
server.listen(process.env.PORT || 14500, '127.0.0.1');
