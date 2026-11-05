// WONIT Electronics v7 — 가상 백엔드 연결 테스트 전용
// mock_server.py가 http://127.0.0.1:5510 에서 실행되어야 합니다.
// 실제 운영에는 config.production.example.js에 팀원 URL을 입력하여 사용하세요.
window.WONIT_CONFIG = Object.freeze({
  employeeWebhookUrl: 'http://127.0.0.1:5510/api/hr/employee',
  chatWebhookUrl: 'http://127.0.0.1:5510/api/hr/question',
  chatStreamUrl: 'http://127.0.0.1:5510/api/hr/question/stream',
  enableStreaming: true,
  historyWebhookUrl: 'http://127.0.0.1:5510/api/hr/history',
  conversationWebhookUrl: 'http://127.0.0.1:5510/api/hr/conversation',
  feedbackWebhookUrl: 'http://127.0.0.1:5510/api/hr/feedback',
  contactWebhookUrl: 'http://127.0.0.1:5510/api/hr/contact',
  healthUrl: 'http://127.0.0.1:5510/api/health',
  sendConversationHistory: false,
  requestTimeoutMs: 45000,
  testMode: true
});
