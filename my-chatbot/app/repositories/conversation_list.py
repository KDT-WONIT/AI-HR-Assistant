"""현재 사번 소유의 채팅방만 검색하고 표시용 제목·요약을 만듭니다."""
from app.integrations.sqlite import connection_scope as sqlite_scope


def list_conversations(repository,employee_id,query='',limit=50):
    if repository.storage_name=='memory':
        # 메모리 모드는 테스트/호환용이며, 공개 조회 메서드로만 이력을 구성합니다.
        with repository._lock:
            items=[item.model_copy(deep=True) for item in repository._items.values() if item.employee_id==employee_id]
    else:
        statement="""SELECT c.id FROM conversations c WHERE c.employee_id={p}
          AND ({p}='' OR EXISTS(SELECT 1 FROM messages m WHERE m.conversation_id=c.id AND instr(lower(m.content),lower({p}))>0))
          ORDER BY COALESCE((SELECT MAX(m.created_at) FROM messages m WHERE m.conversation_id=c.id),c.created_at) DESC LIMIT {p}"""
        if repository.storage_name=='mysql':
            from app.integrations.mysql import connection_scope
            with connection_scope() as connection,connection.cursor() as cursor:
                cursor.execute(statement.format(p='%s'),(employee_id,query,query,limit))
                ids=[row[0] for row in cursor.fetchall()]
        else:
            with sqlite_scope() as connection:
                ids=[row['id'] for row in connection.execute(statement.format(p='?'),(employee_id,query,query,limit)).fetchall()]
        items=[repository.get(identifier) for identifier in ids]
    result=[]
    for item in items:
        if item is None or item.employee_id!=employee_id:
            continue
        if query and not any(query.casefold() in message.content.casefold() for message in item.messages):
            continue
        questions=[message for message in item.messages if message.role=='user']
        last=next((message for message in reversed(item.messages) if message.role=='assistant'),None)
        result.append(dict(session_id=str(item.id),title=questions[0].content[:70] if questions else '새 대화',
            updated_at=(item.messages[-1].created_at if item.messages else item.created_at).isoformat(),
            turn_count=len(questions),message_count=len(item.messages),preview=last.content[:160] if last else '',
            category_id=last.tools_used[0] if last and last.tools_used else None,status=item.status))
    return sorted(result,key=lambda item:item['updated_at'],reverse=True)[:limit]
