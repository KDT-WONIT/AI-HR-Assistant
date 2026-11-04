"""메시지 쌍을 외부 Tool이 기대하는 문의 이력 형식으로 변환합니다."""
import json


def inquiry_record(row):
    item = dict(row)
    tools = item.pop('tools_used',None) or []
    if isinstance(tools,str):
        tools=json.loads(tools)
    item['category'] = ', '.join(tools)
    item['status'] = 'recorded'
    return item


def matching_record(item, keyword):
    return keyword.casefold() in ' '.join(str(item.get(key) or '') for key in ('question','answer','category')).casefold()


INQUIRY_SELECT = '''
SELECT q.id AS inquiry_id,c.employee_id,q.content AS question,a.content AS answer,
       a.tools_used,q.created_at
FROM messages q JOIN conversations c ON c.id=q.conversation_id
JOIN messages a ON a.sequence_id=(SELECT MIN(m.sequence_id) FROM messages m
    WHERE m.conversation_id=q.conversation_id AND m.sequence_id>q.sequence_id)
WHERE q.role='user' AND a.role='assistant' AND c.employee_id={parameter}
  AND ({parameter}='' OR instr(lower(q.content),lower({parameter}))>0
       OR instr(lower(a.content),lower({parameter}))>0 OR instr(lower(COALESCE(a.tools_used,'')),lower({parameter}))>0)
ORDER BY q.created_at DESC,q.sequence_id DESC LIMIT {parameter}
'''
