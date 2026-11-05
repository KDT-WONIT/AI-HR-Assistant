/* Run after python -m scripts.export_database_erd. Uses local @viz-js/viz + sharp. */
const fs = require('node:fs');
const path = require('node:path');
const { instance } = require('@viz-js/viz');
const sharp = require('sharp');

const out = path.resolve(__dirname, '../docs/erd');
const audit = JSON.parse(fs.readFileSync(path.join(out, 'schema-inventory.json'), 'utf8'));
const sources = audit.databases;
const esc = value => String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const quote = value => JSON.stringify(String(value));
const palette = {directory:'#e8f2ed', app:'#e8eef8', chroma_active:'#f0ebf7', reference:'#f0f1f3'};

function node(id, table, key, full=false, fields=null) {
  const foreign = new Set(table.foreign_keys.map(item => item.from));
  let columns = table.columns;
  if (fields) columns = columns.filter(column => fields.includes(column.name));
  else if (!full) {
    const keys = columns.filter(column => column.pk || foreign.has(column.name));
    columns = [...keys, ...columns.filter(column => !keys.includes(column)).slice(0, Math.max(0, 6 - keys.length))];
  }
  const count = table.row_count === null ? 'DDL 정의' : `${table.row_count.toLocaleString()}행`;
  const fieldWidth = Math.max(170,...columns.map(column=>column.name.length * 8.8 + 24));
  let html = `<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="7" COLOR="#ccd5df">`;
  html += `<TR><TD COLSPAN="2" BGCOLOR="${palette[key] || palette.reference}"><B>${esc(table.name)}</B></TD></TR>`;
  html += `<TR><TD COLSPAN="2"><FONT POINT-SIZE="11">${count}</FONT></TD></TR>`;
  for (const column of columns) {
    const unique = table.unique_keys.some(item => item.length === 1 && item[0] === column.name);
    const flags = [column.pk ? 'PK' : '', foreign.has(column.name) ? 'FK' : '', unique && !column.pk ? 'UK' : ''].filter(Boolean).join('/');
    html += `<TR><TD WIDTH="${fieldWidth}" ALIGN="LEFT" PORT="${esc(column.name)}_in">${esc(column.name)}</TD><TD WIDTH="95" ALIGN="LEFT" PORT="${esc(column.name)}_out"><FONT COLOR="#53647a">${flags || esc(column.type || 'value')}</FONT></TD></TR>`;
  }
  html += '</TABLE>';
  return `${quote(id)} [label=<${html}>];`;
}

function relationships(prefix, tables) {
  const lines = [];
  for (const [name, table] of Object.entries(tables)) {
    const groups = new Map();
    for (const fk of table.foreign_keys) {
      if (!groups.has(fk.id)) groups.set(fk.id, []);
      groups.get(fk.id).push(fk);
    }
    for (const group of groups.values()) {
      const parent = group[0].table;
      if (!tables[parent]) continue;
      const fields = group.map(fk => fk.from);
      const primary = table.columns.filter(column => column.pk).map(column => column.name);
      const unique = [primary,...table.unique_keys].some(key => key.length === fields.length && key.every(field => fields.includes(field)));
      const required = table.columns.filter(column => fields.includes(column.name)).every(column => column.notnull || column.pk);
      const parentColumn = group[0].to || tables[parent].columns.find(column=>column.pk)?.name;
      lines.push(`${quote(prefix+parent)}:${quote(parentColumn+'_out')}:e -> ${quote(prefix+name)}:${quote(group[0].from+'_in')}:w [arrowtail=${quote(required ? 'teetee' : 'teeodot')}, arrowhead=${quote(unique ? 'teeodot' : 'crowodot')}, tooltip=${quote(fields.join(', '))}];`);
    }
  }
  return lines;
}

function begin(label) {
  return ['digraph ERD {',`graph [rankdir=LR, bgcolor="white", pad="0.8", nodesep="0.4", ranksep="0.65", splines=polyline, fontname="Malgun Gothic", fontsize=23, label=${quote(label)}, labelloc=t, labeljust=l];`,
    'node [shape=plain, fontname="Arial", fontsize=14];',
    'edge [dir=both, color="#7b8ba1", penwidth=1.15, arrowsize=0.75, fontname="Malgun Gothic", fontsize=11];'];
}

async function save(viz, name, lines) {
  const dot = [...lines,'}'].join('\n');
  fs.writeFileSync(path.join(out,name+'.dot'),dot);
  const svg = viz.renderString(dot,{format:'svg',engine:'dot'});
  fs.writeFileSync(path.join(out,name+'.svg'),svg);
  if (name === 'service-overview' || name === 'directory') {
    await sharp(Buffer.from(svg), {density:144}).resize({width:2600,withoutEnlargement:true}).png().toFile(path.join(out,name+'.png'));
  }
}

async function main() {
  const viz = await instance();
  const coreApp = ['conversations','messages','feedback','webhook_events'];
  const coreChroma = ['collections','segments','embeddings','embedding_metadata'];
  const selected = {directory:sources.directory.tables,
    app:Object.fromEntries(coreApp.map(name=>[name,sources.app.tables[name]])),
    chroma_active:Object.fromEntries(coreChroma.map(name=>[name,sources.chroma_active.tables[name]]))};
  const labels = {directory:'사원·조직 / 읽기 전용 디렉터리',app:'대화·평가 / app.sqlite3',chroma_active:'규정 검색 / ChromaDB'};
  const overviewFields = {
    employees:['employee_id','name','grade'],departments:['dept_id','dept_name','parent_dept_id'],
    duty_roles:['role_id','role_name'],employee_assignments:['assignment_id','employee_id','dept_id'],
    employee_roles:['employee_role_id','employee_id','role_id'],employee_contacts:['employee_id','work_email','photo_url'],
    conversations:['id','employee_id','status'],messages:['sequence_id','conversation_id','sources'],
    feedback:['id','conversation_id','rating'],webhook_events:['event_id','conversation_id','status'],
    collections:['id','name','dimension'],segments:['id','collection','scope'],
    embeddings:['id','segment_id','embedding_id'],embedding_metadata:['id','key','string_value']
  };
  const overview = begin('WONIT AI 업무 도우미 · 현재 서비스 ERD');
  for (const [key,tables] of Object.entries(selected)) {
    overview.push(`subgraph cluster_${key} { label=${quote(labels[key])}; color="#cbd4df"; margin=22; fontsize=19;`);
    for (const [name,table] of Object.entries(tables)) overview.push(node(key+'_'+name,table,key,false,overviewFields[name]));
    overview.push(...relationships(key+'_',tables),'}');
  }
  const logical = (from,fromColumn,to,toColumn,label) => overview.push(`${quote(from)}:${quote(fromColumn+'_out')}:e -> ${quote(to)}:${quote(toColumn+'_in')}:w [style=dashed, color="#9a6b25", arrowtail=none, arrowhead=vee, label=${quote(label)}, fontcolor="#805414"];`);
  logical('directory_employees','employee_id','app_conversations','employee_id','employee_id · 코드 연결');
  logical('chroma_active_collections','id','chroma_active_segments','collection','collection · 논리 연결');
  logical('chroma_active_segments','id','chroma_active_embeddings','segment_id','segment_id · 논리 연결');
  logical('app_messages','sources','chroma_active_embeddings','embedding_id','sources[].chunk_id · JSON 참조');
  overview.push('legend [shape=plaintext, fontsize=13, label="실선: DB 외래키 | 점선: 코드·JSON 연결 | PK: 기본키 · FK: 외래키 · UK: 단일 컬럼 유일키"];');
  await save(viz,'service-overview',overview);

  for (const [key,label] of [['directory','사원·조직 · 전체 6개 테이블'],['app','대화 DB · 전체 12개 테이블'],['chroma_active','ChromaDB · 전체 내부 21개 테이블'],['tool_example','제공 Tool · 예시 스키마 5개 테이블']]) {
    const lines = begin(label);
    for (const [name,table] of Object.entries(sources[key].tables)) lines.push(node(name,table,key,true));
    lines.push(...relationships('',sources[key].tables));
    await save(viz,key,lines);
  }
  const groups = {
    'reference-people':['departments','employees','employee_assignments','employee_contacts','duty_roles','employee_roles','duty_delegations','personnel_actions','performance_reviews','training_history','absences','attendance_records'],
    'reference-leave-pay':['employees','departments','leave_types','leave_balances','leave_adjustments','leave_transactions','payroll_monthly','benefit_programs','benefit_applications'],
    'reference-regulations':['regulations','regulation_versions','regulation_articles','regulation_chunks','business_topics','topic_keywords','topic_ownerships','topic_regulations','employees','departments'],
    'reference-support':['employees','departments','business_topics','chat_sessions','chat_messages','routing_logs','support_tickets','ticket_events','satisfaction_surveys','access_audit_logs'],
    'reference-business':['employees','departments','asset_registry','asset_assignments','expense_claims','travel_requests','procurement_contracts','rd_projects','ip_records','compliance_cases','safety_incidents']
  };
  const covered = new Set();
  for (const [name,names] of Object.entries(groups)) {
    const tables = Object.fromEntries(names.map(key => {covered.add(key);return [key,sources.enterprise_reference.tables[key]];}));
    const lines=begin('원본 전사 DB · '+name.replace('reference-',''));
    for (const [key,table] of Object.entries(tables)) lines.push(node(key,table,'reference',true));
    lines.push(...relationships('',tables));
    await save(viz,name,lines);
  }
  if (covered.size !== Object.keys(sources.enterprise_reference.tables).length) throw new Error('원본 테이블의 도메인별 누락');
  console.log(JSON.stringify({diagrams:10,referenceTablesCovered:covered.size,overview:'service-overview.png'}));
}
main().catch(error=>{console.error(error);process.exitCode=1;});
