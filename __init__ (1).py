"""
BRUDE - Database Layer
SQLite com schema completo, preparado para migrar para Postgres no futuro.
"""
import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

DB_PATH = Path(__file__).parent.parent / "data" / "brude.db"

SCHEMA = """
-- Pessoas da família
CREATE TABLE IF NOT EXISTS membros (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nome        TEXT NOT NULL,
    cartoes     TEXT,           -- JSON: ["Nubank", "XP"]
    salario     REAL DEFAULT 0,
    criado_em   TEXT DEFAULT (datetime('now'))
);

-- Categorias de gasto (flexível, editável)
CREATE TABLE IF NOT EXISTS categorias (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nome        TEXT UNIQUE NOT NULL,
    tipo        TEXT NOT NULL,  -- 'essencial' | 'nao_essencial' | 'investimento' | 'receita'
    meta_mensal REAL DEFAULT 0,
    cor         TEXT DEFAULT '#4F8EF7'
);

-- Todas as transações (core do sistema)
CREATE TABLE IF NOT EXISTS transacoes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    -- Identificação
    hash_dedup          TEXT UNIQUE,        -- SHA256 para deduplicação
    fonte               TEXT NOT NULL,      -- 'nubank' | 'xp' | 'manual'
    membro_id           INTEGER REFERENCES membros(id),
    -- Dados da transação
    data                TEXT NOT NULL,      -- ISO 8601: 2026-04-07
    descricao_original  TEXT NOT NULL,      -- texto bruto da fatura
    descricao_norm      TEXT,               -- após normalização
    valor               REAL NOT NULL,      -- positivo=débito, negativo=crédito/estorno
    -- Classificação
    categoria_id        INTEGER REFERENCES categorias(id),
    classificacao_auto  INTEGER DEFAULT 1,  -- 1=automático, 0=corrigido manualmente
    confianca           REAL DEFAULT 1.0,   -- 0.0 a 1.0
    -- Parcelamento
    parcela_atual       INTEGER,            -- ex: 3
    parcela_total       INTEGER,            -- ex: 10
    grupo_parcela       TEXT,               -- UUID do grupo de parcelas
    -- Metadados
    mes_referencia      TEXT,               -- 'Abr/2026'
    cartao              TEXT,               -- 'Nubank' | 'XP'
    importado_em        TEXT DEFAULT (datetime('now')),
    obs                 TEXT
);

-- Índices para performance
CREATE INDEX IF NOT EXISTS idx_trans_data       ON transacoes(data);
CREATE INDEX IF NOT EXISTS idx_trans_membro     ON transacoes(membro_id);
CREATE INDEX IF NOT EXISTS idx_trans_categoria  ON transacoes(categoria_id);
CREATE INDEX IF NOT EXISTS idx_trans_mes        ON transacoes(mes_referencia);
CREATE INDEX IF NOT EXISTS idx_trans_hash       ON transacoes(hash_dedup);

-- Receitas mensais
CREATE TABLE IF NOT EXISTS receitas (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    membro_id   INTEGER REFERENCES membros(id),
    mes         TEXT NOT NULL,      -- '2026-04'
    tipo        TEXT NOT NULL,      -- 'salario' | 'comissao' | 'extra' | 'investimento'
    valor       REAL NOT NULL,
    descricao   TEXT,
    criado_em   TEXT DEFAULT (datetime('now'))
);

-- Investimentos (snapshot mensal)
CREATE TABLE IF NOT EXISTS investimentos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    mes             TEXT NOT NULL,      -- '2026-04'
    membro_id       INTEGER REFERENCES membros(id),
    instituicao     TEXT NOT NULL,      -- 'XP' | 'Nubank'
    saldo           REAL NOT NULL,
    aporte_mes      REAL DEFAULT 0,
    proventos_mes   REAL DEFAULT 0,
    rendimento_pct  REAL DEFAULT 0,
    criado_em       TEXT DEFAULT (datetime('now'))
);

-- Parcelas futuras projetadas (calculadas automaticamente)
CREATE TABLE IF NOT EXISTS parcelas_futuras (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    transacao_id    INTEGER REFERENCES transacoes(id),
    mes_projetado   TEXT NOT NULL,      -- '2026-05'
    valor           REAL NOT NULL,
    pago            INTEGER DEFAULT 0   -- 0=pendente, 1=confirmado na fatura
);

-- Dicionário de normalização (aprendizado)
CREATE TABLE IF NOT EXISTS dict_normalizacao (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    padrao      TEXT NOT NULL,      -- regex ou string a ser substituída
    nome_norm   TEXT NOT NULL,      -- nome limpo resultado
    categoria   TEXT,               -- categoria sugerida junto
    tipo        TEXT DEFAULT 'exato', -- 'exato' | 'regex' | 'fuzzy'
    usos        INTEGER DEFAULT 0,  -- quantas vezes foi aplicado
    criado_em   TEXT DEFAULT (datetime('now'))
);

-- Log de correções manuais (base para aprendizado futuro)
CREATE TABLE IF NOT EXISTS correcoes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    transacao_id    INTEGER REFERENCES transacoes(id),
    campo           TEXT NOT NULL,          -- 'categoria' | 'descricao'
    valor_antigo    TEXT,
    valor_novo      TEXT,
    corrigido_em    TEXT DEFAULT (datetime('now'))
);

-- Gastos fixos recorrentes detectados
CREATE TABLE IF NOT EXISTS recorrentes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    descricao_norm  TEXT NOT NULL,
    categoria_id    INTEGER REFERENCES categorias(id),
    valor_medio     REAL,
    dia_habitual    INTEGER,    -- dia do mês que costuma aparecer
    ativo           INTEGER DEFAULT 1,
    ultima_vez      TEXT
);

-- Score financeiro mensal (calculado)
CREATE TABLE IF NOT EXISTS scores_mensais (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    mes                 TEXT UNIQUE NOT NULL,
    total_receitas      REAL DEFAULT 0,
    total_gastos        REAL DEFAULT 0,
    total_fixos         REAL DEFAULT 0,
    total_variaveis     REAL DEFAULT 0,
    total_investido     REAL DEFAULT 0,
    taxa_poupanca       REAL DEFAULT 0,   -- (receitas - gastos) / receitas
    pct_essencial       REAL DEFAULT 0,   -- essencial / total_gastos
    score               REAL DEFAULT 0,   -- 0-100
    calculado_em        TEXT DEFAULT (datetime('now'))
);
"""

CATEGORIAS_INICIAIS = [
    ("Compras Online",    "nao_essencial", 700,  "#EF4444"),
    ("Alimentação",       "nao_essencial", 900,  "#F59E0B"),
    ("Supermercado",      "essencial",     500,  "#22C55E"),
    ("Combustível",       "essencial",     600,  "#3B82F6"),
    ("Transporte",        "essencial",     300,  "#6366F1"),
    ("Saúde/Farmácia",    "essencial",     200,  "#10B981"),
    ("Saúde/Academia",    "essencial",     150,  "#14B8A6"),
    ("Assinaturas",       "nao_essencial", 250,  "#8B5CF6"),
    ("Serviços Pessoais", "nao_essencial", 300,  "#EC4899"),
    ("Bebidas",           "nao_essencial", 150,  "#F97316"),
    ("Restaurante",       "nao_essencial", 400,  "#EAB308"),
    ("Viagem",            "nao_essencial", 500,  "#06B6D4"),
    ("Roupas",            "nao_essencial", 300,  "#A78BFA"),
    ("Casa/Moradia",      "essencial",     300,  "#84CC16"),
    ("Educação",          "essencial",     200,  "#0EA5E9"),
    ("Seguros",           "essencial",     300,  "#64748B"),
    ("Impostos/Taxas",    "essencial",     200,  "#78716C"),
    ("Eletrodomésticos",  "nao_essencial", 0,    "#94A3B8"),
    ("Lazer",             "nao_essencial", 200,  "#F43F5E"),
    ("Manutenção",        "essencial",     150,  "#A3E635"),
    ("Outros",            "nao_essencial", 0,    "#CBD5E1"),
]

MEMBROS_INICIAIS = [
    ("André",  '["Nubank", "XP"]', 7000),
    ("Bruna",  '["Nubank"]',       8000),
]

DICT_NORMALIZACAO_INICIAL = [
    # Compras Online
    ("MERCADOLIVRE", "Mercado Livre", "Compras Online", "regex"),
    ("MERCADO LIVRE", "Mercado Livre", "Compras Online", "exato"),
    ("ML ", "Mercado Livre", "Compras Online", "regex"),
    ("SHOPEE", "Shopee", "Compras Online", "regex"),
    ("SHEIN", "Shein", "Compras Online", "regex"),
    ("AMAZON", "Amazon", "Compras Online", "regex"),
    ("AMZN", "Amazon", "Compras Online", "regex"),
    ("ALIEXPRESS", "AliExpress", "Compras Online", "regex"),
    ("MAGALU", "Magazine Luiza", "Compras Online", "regex"),
    ("MAGAZINE LUIZA", "Magazine Luiza", "Compras Online", "exato"),
    ("AMERICANAS", "Americanas", "Compras Online", "regex"),
    ("NETSHOES", "Netshoes", "Compras Online", "regex"),
    ("KABUM", "KaBuM", "Compras Online", "regex"),
    # Alimentação/Restaurante
    ("SWEETCO", "Sweetco", "Alimentação", "exato"),
    ("IFOOD", "iFood", "Alimentação", "regex"),
    ("RAPPI", "Rappi", "Alimentação", "regex"),
    ("UBER EATS", "Uber Eats", "Alimentação", "regex"),
    ("MC DONALDS", "McDonald's", "Alimentação", "regex"),
    ("MCDONALDS", "McDonald's", "Alimentação", "regex"),
    ("BURGER KING", "Burger King", "Alimentação", "regex"),
    ("KFC", "KFC", "Alimentação", "exato"),
    ("SUBWAY", "Subway", "Alimentação", "regex"),
    ("HABIB", "Habib's", "Alimentação", "regex"),
    ("SUSHI", "Sushi", "Alimentação", "regex"),
    ("PIZZA", "Pizza", "Alimentação", "regex"),
    # Supermercado
    ("CARREFOUR", "Carrefour", "Supermercado", "regex"),
    ("EXTRA ", "Extra", "Supermercado", "regex"),
    ("ASSAI", "Assaí", "Supermercado", "regex"),
    ("ATACADAO", "Atacadão", "Supermercado", "regex"),
    ("ATACADÃO", "Atacadão", "Supermercado", "regex"),
    ("PAO DE ACUCAR", "Pão de Açúcar", "Supermercado", "regex"),
    ("PREZUNIC", "Prezunic", "Supermercado", "regex"),
    ("SUPER ", "Supermercado", "Supermercado", "regex"),
    ("GIGA ATACADO", "Giga Atacado", "Supermercado", "exato"),
    # Combustível
    ("POSTO ", "Posto de Combustível", "Combustível", "regex"),
    ("PETROBRAS", "Petrobras", "Combustível", "regex"),
    ("IPIRANGA", "Ipiranga", "Combustível", "regex"),
    ("SHELL", "Shell", "Combustível", "regex"),
    ("BR DIST", "BR Distribuidora", "Combustível", "regex"),
    # Transporte
    ("UBER", "Uber", "Transporte", "regex"),
    ("99APP", "99", "Transporte", "regex"),
    ("99 ", "99", "Transporte", "regex"),
    ("VELOE", "Veloe", "Transporte", "regex"),
    ("SEM PARAR", "Sem Parar", "Transporte", "regex"),
    ("LOCALIZA", "Localiza", "Transporte", "exato"),
    ("MOVIDA", "Movida", "Transporte", "regex"),
    # Assinaturas
    ("NETFLIX", "Netflix", "Assinaturas", "regex"),
    ("SPOTIFY", "Spotify", "Assinaturas", "regex"),
    ("AMAZON PRIME", "Amazon Prime", "Assinaturas", "regex"),
    ("DISNEY", "Disney+", "Assinaturas", "regex"),
    ("HBO", "HBO Max", "Assinaturas", "regex"),
    ("APPLE", "Apple", "Assinaturas", "regex"),
    ("GOOGLE", "Google", "Assinaturas", "regex"),
    ("CLAUDE", "Claude/Anthropic", "Assinaturas", "regex"),
    ("OPENAI", "OpenAI", "Assinaturas", "regex"),
    ("CHATGPT", "ChatGPT", "Assinaturas", "regex"),
    ("MICROSOFT", "Microsoft", "Assinaturas", "regex"),
    ("ADOBE", "Adobe", "Assinaturas", "regex"),
    ("TOTALPASS", "TotalPass", "Saúde/Academia", "regex"),
    # Saúde
    ("FARMACIA", "Farmácia", "Saúde/Farmácia", "regex"),
    ("DROGASIL", "Drogasil", "Saúde/Farmácia", "regex"),
    ("DROGA", "Farmácia", "Saúde/Farmácia", "regex"),
    ("ULTRAFARMA", "Ultrafarma", "Saúde/Farmácia", "regex"),
    ("CLINICA", "Clínica", "Saúde/Farmácia", "regex"),
    ("HOSPITAL", "Hospital", "Saúde/Farmácia", "regex"),
    # Seguros
    ("ALLIANZ", "Allianz Seguros", "Seguros", "regex"),
    ("HDI", "HDI Seguros", "Seguros", "regex"),
    ("BRADESCO SEG", "Bradesco Seguros", "Seguros", "regex"),
    ("PORTO SEG", "Porto Seguro", "Seguros", "regex"),
    # Educação
    ("ESCOLA", "Escola", "Educação", "regex"),
    ("COLEGIO", "Colégio", "Educação", "regex"),
    ("UDEMY", "Udemy", "Educação", "regex"),
    ("COURSERA", "Coursera", "Educação", "regex"),
    # Viagem
    ("AZUL", "Azul Linhas Aéreas", "Viagem", "regex"),
    ("LATAM", "LATAM", "Viagem", "regex"),
    ("GOL", "GOL", "Viagem", "regex"),
    ("AIRBNB", "Airbnb", "Viagem", "regex"),
    ("BOOKING", "Booking", "Viagem", "regex"),
    ("HOTEL", "Hotel", "Viagem", "regex"),
]


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db():
    """Inicializa o banco com schema e dados iniciais."""
    conn = get_connection()
    conn.executescript(SCHEMA)

    # Membros
    for nome, cartoes, salario in MEMBROS_INICIAIS:
        conn.execute("""
            INSERT OR IGNORE INTO membros (nome, cartoes, salario)
            VALUES (?, ?, ?)
        """, (nome, cartoes, salario))

    # Categorias
    for nome, tipo, meta, cor in CATEGORIAS_INICIAIS:
        conn.execute("""
            INSERT OR IGNORE INTO categorias (nome, tipo, meta_mensal, cor)
            VALUES (?, ?, ?, ?)
        """, (nome, tipo, meta, cor))

    # Dicionário de normalização
    for padrao, nome_norm, cat, tipo in DICT_NORMALIZACAO_INICIAL:
        conn.execute("""
            INSERT OR IGNORE INTO dict_normalizacao (padrao, nome_norm, categoria, tipo)
            VALUES (?, ?, ?, ?)
        """, (padrao, nome_norm, cat, tipo))

    conn.commit()
    conn.close()
    print(f"✅ Banco inicializado: {DB_PATH}")


def get_categorias() -> dict:
    """Retorna dict {nome: id} de categorias."""
    conn = get_connection()
    rows = conn.execute("SELECT id, nome FROM categorias").fetchall()
    conn.close()
    return {r['nome']: r['id'] for r in rows}


def get_membro_id(nome: str) -> Optional[int]:
    conn = get_connection()
    row = conn.execute("SELECT id FROM membros WHERE nome = ?", (nome,)).fetchone()
    conn.close()
    return row['id'] if row else None


def inserir_transacoes(transacoes: list[dict]) -> tuple[int, int]:
    """
    Insere lista de transações. Retorna (inseridas, duplicatas).
    Usa hash_dedup para evitar duplicatas.
    """
    conn = get_connection()
    inseridas = 0
    duplicatas = 0

    for t in transacoes:
        try:
            conn.execute("""
                INSERT INTO transacoes (
                    hash_dedup, fonte, membro_id, data, descricao_original,
                    descricao_norm, valor, categoria_id, classificacao_auto,
                    confianca, parcela_atual, parcela_total, grupo_parcela,
                    mes_referencia, cartao
                ) VALUES (
                    :hash_dedup, :fonte, :membro_id, :data, :descricao_original,
                    :descricao_norm, :valor, :categoria_id, :classificacao_auto,
                    :confianca, :parcela_atual, :parcela_total, :grupo_parcela,
                    :mes_referencia, :cartao
                )
            """, t)
            inseridas += 1
        except sqlite3.IntegrityError:
            duplicatas += 1

    # Projetar parcelas futuras
    _projetar_parcelas(conn, transacoes)

    conn.commit()
    conn.close()
    return inseridas, duplicatas


def _projetar_parcelas(conn: sqlite3.Connection, transacoes: list[dict]):
    """Para cada transação parcelada, projeta as parcelas futuras."""
    from datetime import datetime, timedelta
    import calendar

    for t in transacoes:
        if not t.get('parcela_atual') or not t.get('parcela_total'):
            continue

        parcela_atual = t['parcela_atual']
        parcela_total = t['parcela_total']
        restantes = parcela_total - parcela_atual

        if restantes <= 0:
            continue

        trans_row = conn.execute(
            "SELECT id FROM transacoes WHERE hash_dedup = ?",
            (t['hash_dedup'],)
        ).fetchone()

        if not trans_row:
            continue

        trans_id = trans_row['id']
        data_base = datetime.fromisoformat(t['data'])

        for i in range(1, restantes + 1):
            # Avança i meses
            mes = data_base.month + i
            ano = data_base.year + (mes - 1) // 12
            mes = ((mes - 1) % 12) + 1
            mes_str = f"{ano}-{mes:02d}"

            try:
                conn.execute("""
                    INSERT OR IGNORE INTO parcelas_futuras
                        (transacao_id, mes_projetado, valor)
                    VALUES (?, ?, ?)
                """, (trans_id, mes_str, t['valor']))
            except Exception:
                pass


def consolidado_mensal(mes: str) -> dict:
    """
    Retorna consolidado do mês no formato: {categoria: {total, meta, pct_meta}}
    mes: '2026-04'
    """
    conn = get_connection()
    rows = conn.execute("""
        SELECT
            c.nome      AS categoria,
            c.tipo      AS tipo,
            c.meta_mensal AS meta,
            SUM(t.valor) AS total,
            m.nome      AS membro
        FROM transacoes t
        JOIN categorias c ON t.categoria_id = c.id
        JOIN membros m    ON t.membro_id = m.id
        WHERE strftime('%Y-%m', t.data) = ?
          AND t.valor > 0
        GROUP BY c.nome, m.nome
        ORDER BY total DESC
    """, (mes,)).fetchall()

    resultado = {}
    for r in rows:
        cat = r['categoria']
        if cat not in resultado:
            resultado[cat] = {
                'total': 0, 'meta': r['meta'],
                'tipo': r['tipo'], 'por_membro': {}
            }
        resultado[cat]['total'] += r['total']
        resultado[cat]['por_membro'][r['membro']] = r['total']

    for cat in resultado:
        meta = resultado[cat]['meta']
        total = resultado[cat]['total']
        resultado[cat]['pct_meta'] = (total / meta * 100) if meta else None
        resultado[cat]['status'] = (
            'ok' if not meta or total <= meta else
            'atencao' if total <= meta * 1.2 else 'critico'
        )

    conn.close()
    return resultado


def parcelas_projetadas(mes: str) -> list[dict]:
    """Retorna parcelas projetadas para um mês futuro."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT
            pf.mes_projetado,
            pf.valor,
            t.descricao_norm,
            t.parcela_atual,
            t.parcela_total,
            m.nome AS membro
        FROM parcelas_futuras pf
        JOIN transacoes t ON pf.transacao_id = t.id
        JOIN membros m    ON t.membro_id = m.id
        WHERE pf.mes_projetado = ?
        ORDER BY m.nome, t.descricao_norm
    """, (mes,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    init_db()
