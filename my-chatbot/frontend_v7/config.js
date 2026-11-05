// 실제 FastAPI 서비스와 같은 출처에서만 통신합니다. 외부 n8n 주소는 서버 .env에서 관리합니다.
window.WONIT_CONFIG=Object.freeze({
  createSessionUrl:new URL('/api/conversations',location.origin).href,
  retryWebhookUrl:new URL('/api/hr/retry',location.origin).href,
  employeeWebhookUrl:new URL('/api/hr/employee',location.origin).href,
  chatWebhookUrl:new URL('/api/hr/question',location.origin).href,
  chatStreamUrl:new URL('/api/hr/question/stream',location.origin).href,
  historyWebhookUrl:new URL('/api/hr/history',location.origin).href,
  conversationWebhookUrl:new URL('/api/hr/conversation',location.origin).href,
  feedbackWebhookUrl:new URL('/api/hr/feedback',location.origin).href,
  contactWebhookUrl:new URL('/api/hr/contact',location.origin).href,
  healthUrl:new URL('/api/health',location.origin).href,
  enableStreaming:true,sendConversationHistory:false,requestTimeoutMs:300000,testMode:false
});
