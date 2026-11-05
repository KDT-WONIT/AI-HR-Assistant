// 연동 테스트가 끝난 뒤, 이 파일을 config.js로 덮어쓰고 실제 n8n URL로 수정하세요.
// 실제 직원 데이터 및 권한 처리는 백엔드 인증을 추가해야 합니다.
window.WONIT_CONFIG = Object.freeze({
  employeeWebhookUrl: '',
  chatWebhookUrl: '',
  chatStreamUrl: '',
  enableStreaming: false, // 팀 서버가 SSE streaming을 구현한 경우에만 true
  conversationWebhookUrl: '', // 채팅방 상세 + 전체 턴 반환 API
  historyWebhookUrl: '',
  feedbackWebhookUrl: '',
  contactWebhookUrl: '',
  healthUrl: '',
  sendConversationHistory: false,
  requestTimeoutMs: 45000,
  testMode: false
});
