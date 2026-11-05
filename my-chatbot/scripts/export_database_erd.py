"""실제 SQLite DB와 참고 DDL을 읽기 전용으로 조사해 ERD 원본을 내보냅니다."""

import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import PROJECT_ROOT, settings

WORKSPACE = PROJECT_ROOT.parent
OUTPUT = PROJECT_ROOT / "docs" / "erd"


def identifier(name):
    return '"' + name.replace('"', '""') + '"'


def inspect_connection(connection, *, count_rows):
    connection.row_factory = sqlite3.Row
    result = {"tables": {}, "views": {}}
    for row in connection.execute("SELECT type,name,sql FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        name = row["name"]
        item = {"name": name, "sql": row["sql"]}
        try:
            item["columns"] = [dict(column) for column in connection.execute(f"PRAGMA table_info({identifier(name)})")]
        except sqlite3.OperationalError:
            item["columns"] = []
        if row["type"] == "table":
            item["foreign_keys"] = [dict(key) for key in connection.execute(f"PRAGMA foreign_key_list({identifier(name)})")]
            item["unique_keys"] = []
            for index in connection.execute(f"PRAGMA index_list({identifier(name)})"):
                if index["unique"]:
                    item["unique_keys"].append([column["name"] for column in connection.execute(f"PRAGMA index_info({identifier(index['name'])})")])
            item["row_count"] = connection.execute(f"SELECT COUNT(*) FROM {identifier(name)}").fetchone()[0] if count_rows else None
            result["tables"][name] = item
        else:
            item["dependencies"] = sorted(set(re.findall(r"\b(?:FROM|JOIN)\s+[`\"]?([a-zA-Z_][a-zA-Z_0-9]*)", row["sql"], re.I)))
            result["views"][name] = item
    return result


def inspect_file(path):
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        return inspect_connection(connection, count_rows=True)


def inspect_ddl(path, *, mysql=False):
    sql = path.read_text(encoding="utf-8-sig")
    if mysql:
        blocks = re.findall(r"CREATE TABLE IF NOT EXISTS `[a-z_]+` \([\s\S]*?\) ENGINE[^;]+;", sql)
        blocks = [re.sub(r"\) ENGINE[^;]+;", ");", block) for block in blocks]
        blocks = [re.sub(r"UNIQUE KEY `[a-zA-Z_0-9]+`\s*\(", "UNIQUE (", block) for block in blocks]
    else:
        blocks = re.findall(r"CREATE TABLE(?: IF NOT EXISTS)?\s+[a-z_]+\s*\([\s\S]*?\);", sql, re.I)
    with closing(sqlite3.connect(":memory:")) as connection:
        for block in blocks:
            connection.execute(block)
        data = inspect_connection(connection, count_rows=False)
    if mysql:
        for name, body in re.findall(r"CREATE OR REPLACE VIEW `([a-z_]+)` AS([\s\S]*?);", sql):
            data["views"][name] = {"name": name, "sql": body, "columns": [],
                "dependencies": sorted(set(re.findall(r"\b(?:FROM|JOIN)\s+`?([a-z_]+)", body, re.I)))}
    return data


def mermaid_type(column):
    value = column["type"].upper()
    if "INT" in value:
        return "int"
    if any(term in value for term in ("REAL", "FLOAT", "DOUBLE", "DECIMAL", "NUMERIC")):
        return "decimal"
    if "BLOB" in value:
        return "blob"
    return "string"


def erd(data, *, prefix="", names=None, full=False):
    tables = {name: table for name, table in data["tables"].items() if names is None or name in names}
    lines = ["erDiagram", "    direction LR"]
    for name, table in tables.items():
        foreign = {key["from"] for key in table["foreign_keys"]}
        unique = {key[0] for key in table["unique_keys"] if len(key) == 1}
        lines.append(f"    {prefix}{name} {{")
        columns = table["columns"]
        if not full:
            priority = [column for column in columns if column["pk"] or column["name"] in foreign]
            priority += [column for column in columns if column not in priority][:max(0, 7-len(priority))]
            columns = priority
        for column in columns:
            keys = []
            if column["pk"]:
                keys.append("PK")
            if column["name"] in foreign:
                keys.append("FK")
            if column["name"] in unique and not column["pk"]:
                keys.append("UK")
            attributes = " " + ", ".join(keys) if keys else ""
            lines.append(f"        {mermaid_type(column)} {column['name']}{attributes}")
        lines.append("    }")
    for name, table in tables.items():
        groups = {}
        for key in table["foreign_keys"]:
            groups.setdefault(key["id"], []).append(key)
        for group in groups.values():
            parent = group[0]["table"]
            if parent not in tables:
                continue
            columns = [key["from"] for key in group]
            primary = [column["name"] for column in sorted(table["columns"],key=lambda column:column["pk"]) if column["pk"]]
            unique = any(set(columns) == set(key) for key in [primary,*table["unique_keys"]])
            required = all(column["notnull"] or column["pk"] for column in table["columns"] if column["name"] in columns)
            parent_end = "||" if required else "o|"
            child_end = "o|" if unique else "o{"
            lines.append(f"    {prefix}{parent} {parent_end}--{child_end} {prefix}{name} : \"{', '.join(columns)}\"")
    return "\n".join(lines) + "\n"


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    paths = {
        "app": settings.sqlite_path,
        "directory": settings.employee_directory_db,
        "chroma_active": settings.chroma_dir / "chroma.sqlite3",
        "chroma_legacy_copy": PROJECT_ROOT / "chroma_db/chroma.sqlite3",
        "chroma_tool_copy": WORKSPACE / "employee_tools_project/data/rag_data/chroma_db/chroma.sqlite3",
    }
    audit = {"captured_at": datetime.now(timezone(timedelta(hours=9))).isoformat(),
             "settings": {"storage_backend": settings.storage_backend, "user_data_source": settings.user_data_source,
                          "chroma_collection": settings.chroma_collection}, "databases": {}}
    for key, path in paths.items():
        if path.is_file():
            data = inspect_file(path)
            data.update(path=str(path), kind="live_sqlite", active=key in {"app","directory","chroma_active"})
            audit["databases"][key] = data
    if "chroma_active" in audit["databases"]:
        with closing(sqlite3.connect(paths["chroma_active"].resolve().as_uri()+"?mode=ro",uri=True)) as connection:
            audit["databases"]["chroma_active"]["source_count"] = connection.execute(
                "SELECT COUNT(DISTINCT string_value) FROM embedding_metadata WHERE key='source'").fetchone()[0]
            audit["databases"]["chroma_active"]["collection_names"] = [row[0] for row in connection.execute("SELECT name FROM collections")]
    references = {
        "enterprise_reference": (WORKSPACE / "data/KDN_Enterprise_AI_Dataset/KDN_Enterprise_AI_Dataset_Pexels/sql/01_create_schema.sql", True),
        "tool_example": (WORKSPACE / "employee_tools_project/employee_tools/schema.example.sql", False),
    }
    for key,(path,is_mysql) in references.items():
        data = inspect_ddl(path,mysql=is_mysql)
        data.update(path=str(path),kind="ddl_reference_only",active=False)
        audit["databases"][key] = data
    (OUTPUT / "schema-inventory.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    for key,data in audit["databases"].items():
        (OUTPUT / f"{key}-full.mmd").write_text(erd(data,full=True),encoding="utf-8")
    dictionary = ["# DB 컬럼 사전", "", f"조사 시각: {audit['captured_at']}", "",
                  "실제 DB의 PRAGMA 정보 및 참고 DDL에서 추출했습니다. 개인·대화 본문 데이터는 포함하지 않습니다.", ""]
    for key,data in audit["databases"].items():
        if key in {"chroma_legacy_copy","chroma_tool_copy"}:
            continue
        dictionary += [f"## {key}", "", f"원본: `{data['path']}`", ""]
        for name,table in data["tables"].items():
            foreign = {fk["from"]:f"{fk['table']}.{fk['to']}" for fk in table["foreign_keys"]}
            count = table["row_count"] if table["row_count"] is not None else "DDL만 확인"
            dictionary += [f"### {name}", "", f"행 수: {count}", "",
                           "| 컬럼 | 형식 | 키 | 필수 | 참조 |", "| --- | --- | --- | --- | --- |"]
            for column in table["columns"]:
                flags = []
                if column["pk"]:
                    flags.append("PK")
                if column["name"] in foreign:
                    flags.append("FK")
                if [column["name"]] in table["unique_keys"] and not column["pk"]:
                    flags.append("UK")
                dictionary.append(f"| {column['name']} | {column['type'] or 'untyped'} | {', '.join(flags)} | {'Y' if column['notnull'] or column['pk'] else 'N'} | {foreign.get(column['name'],'')} |")
            dictionary += ["", "복합/단일 유일 인덱스: " + (", ".join("("+", ".join(str(field) for field in fields)+")" for fields in table["unique_keys"]) or "없음"), ""]
        for name,view in data["views"].items():
            dictionary += [f"### VIEW: {name}", "", "참조: " + ", ".join(view["dependencies"]), ""]
    (OUTPUT / "data-dictionary.md").write_text("\n".join(dictionary)+"\n",encoding="utf-8")
    print(json.dumps({key:{"tables":len(value["tables"]),"views":len(value["views"]),
                          "counts":{name:table["row_count"] for name,table in value["tables"].items()} if key in {"app","directory"} else None}
                      for key,value in audit["databases"].items()},ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
