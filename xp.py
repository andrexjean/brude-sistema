"""
BRUDE - Parser XP Investimentos
XP não tem fatura de cartão no mesmo formato que Nubank.
Este parser lida com:
1. Extrato de cartão XP (PDF ou CSV)
2. Posição de investimentos (XLSX/CSV)
"""
import re
import csv
import hashlib
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional

try:
    import pdfplumber
    HAS_PDF = True
except ImportError:
    HAS_PDF = False

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False


def _parse_valor_br(valor_str: str) -> float:
    v = str(valor_str).strip()
    v = re.sub(r'[R$\s]', '', v)
    v = v.replace('.', '').replace(',', '.')
    return float(v)


def _gerar_hash(data: str, descricao: str, valor: float, membro: str) -> str:
    chave = f"{data}|{descricao.upper().strip()}|{valor:.2f}|{membro}"
    return hashlib.sha256(chave.encode()).hexdigest()[:32]


def _detectar_parcela(descricao: str):
    pattern = re.compile(r'(\d{1,2})/(\d{1,2})')
    match = pattern.search(descricao)
    if match:
        atual = int(match.group(1))
        total = int(match.group(2))
        if 1 <= atual <= total <= 72 and total >= 2:
            return atual, total
    return None, None


def _normalizar_data(data_str: str) -> Optional[str]:
    formatos = ['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%d/%m/%y']
    for fmt in formatos:
        try:
            return datetime.strptime(data_str.strip(), fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return None


# ── Parser CSV de extrato XP ──────────────────────────────────
def parse_xp_csv(
    filepath: str,
    membro: str,
    mes_referencia: Optional[str] = None
) -> list[dict]:
    """
    Parseia CSV de extrato de cartão XP.
    XP exporta diferentes formatos dependendo do produto.
    Este parser é flexível para suportar variações.
    """
    transacoes = []
    filepath = Path(filepath)

    with open(filepath, encoding='utf-8-sig') as f:
        # Tenta detectar o delimitador
        sample = f.read(2048)
        f.seek(0)
        delimitador = ';' if sample.count(';') > sample.count(',') else ','

        reader = csv.DictReader(f, delimiter=delimitador)
        headers_raw = reader.fieldnames or []
        headers = [h.lower().strip() for h in headers_raw]

        for row in reader:
            row_lower = {k.lower().strip(): v.strip() for k, v in row.items()}

            try:
                # Detecta colunas flexivelmente
                data_raw = (
                    row_lower.get('data') or
                    row_lower.get('date') or
                    row_lower.get('data lançamento') or
                    row_lower.get('data lancamento') or ''
                )

                descricao = (
                    row_lower.get('descrição') or
                    row_lower.get('descricao') or
                    row_lower.get('description') or
                    row_lower.get('estabelecimento') or
                    row_lower.get('title') or ''
                )

                valor_raw = (
                    row_lower.get('valor') or
                    row_lower.get('amount') or
                    row_lower.get('value') or '0'
                )

                data = _normalizar_data(data_raw)
                if not data or not descricao:
                    continue

                valor = _parse_valor_br(valor_raw)
                if valor <= 0:
                    continue

                parcela_atual, parcela_total = _detectar_parcela(descricao)
                grupo_parcela = str(uuid.uuid4()) if parcela_total else None
                mes_ref = mes_referencia or f"{data[:4]}-{data[5:7]}"
                hash_id = _gerar_hash(data, descricao, valor, membro)

                transacoes.append({
                    'hash_dedup':         hash_id,
                    'fonte':              'xp',
                    'membro_id':          None,
                    'membro_nome':        membro,
                    'data':               data,
                    'descricao_original': descricao.strip(),
                    'descricao_norm':     None,
                    'valor':              round(valor, 2),
                    'categoria_id':       None,
                    'categoria_sugerida': None,
                    'confianca_norm':     0.0,
                    'classificacao_auto': 1,
                    'confianca':          0.0,
                    'parcela_atual':      parcela_atual,
                    'parcela_total':      parcela_total,
                    'grupo_parcela':      grupo_parcela,
                    'mes_referencia':     mes_ref,
                    'cartao':             'XP',
                })

            except (ValueError, KeyError) as e:
                print(f"  ⚠️  Linha XP ignorada: {e}")
                continue

    print(f"📄 XP CSV: {len(transacoes)} transações de {filepath.name}")
    return transacoes


# ── Parser XLSX (relatório de posição de investimentos) ────────
def parse_xp_investimentos(
    filepath: str,
    membro: str,
    mes: Optional[str] = None
) -> dict:
    """
    Parseia relatório de posição de investimentos da XP.
    Retorna dict com snapshot da posição para salvar na tabela investimentos.

    Retorna:
    {
        'mes': '2026-04',
        'membro_nome': 'André',
        'instituicao': 'XP',
        'saldo': 59730.0,
        'aporte_mes': 0,
        'proventos_mes': 143.92,
        'rendimento_pct': 0.0277,
        'por_tipo': {...}  # breakdown opcional
    }
    """
    filepath = Path(filepath)

    if not HAS_PANDAS:
        print("⚠️  pandas não instalado. Instale: pip install pandas openpyxl")
        return {}

    try:
        xl = pd.read_excel(filepath, sheet_name=None)
        resultado = {
            'mes': mes or datetime.now().strftime('%Y-%m'),
            'membro_nome': membro,
            'instituicao': 'XP',
            'saldo': 0.0,
            'aporte_mes': 0.0,
            'proventos_mes': 0.0,
            'rendimento_pct': 0.0,
            'por_tipo': {}
        }

        # Tenta encontrar totais no arquivo
        for sheet_name, df in xl.items():
            df.columns = [str(c).lower().strip() for c in df.columns]

            # Procura coluna de valor total
            for col in df.columns:
                if 'valor' in col or 'saldo' in col or 'total' in col:
                    valores = pd.to_numeric(
                        df[col].astype(str).str.replace('[R$.,\\s]', '', regex=True)
                        .str.replace(',', '.'),
                        errors='coerce'
                    ).dropna()
                    if len(valores) > 0:
                        resultado['saldo'] = float(valores.sum())
                        break

        print(f"📊 XP Investimentos: saldo R$ {resultado['saldo']:,.2f}")
        return resultado

    except Exception as e:
        print(f"❌ Erro ao ler investimentos XP: {e}")
        return {}


# ── Parser PDF XP ──────────────────────────────────────────────
def parse_xp_pdf(
    filepath: str,
    membro: str,
    mes_referencia: Optional[str] = None
) -> list[dict]:
    """
    Parseia PDF de fatura do cartão XP.
    XP Visa segue layout similar a bancos tradicionais.
    """
    if not HAS_PDF:
        print("⚠️  pdfplumber não instalado")
        return []

    transacoes = []
    filepath = Path(filepath)

    # Padrão XP: "07/04/2026  SHOPEE*PROD      R$ 123,45"
    _XP_LINHA = re.compile(
        r'(\d{2}/\d{2}/\d{4})\s+(.+?)\s+([\d\.]+,\d{2})$'
    )

    try:
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                texto = page.extract_text(x_tolerance=3, y_tolerance=3)
                if not texto:
                    continue

                for linha in texto.splitlines():
                    linha = linha.strip()
                    match = _XP_LINHA.match(linha)
                    if not match:
                        continue

                    data_raw, descricao, valor_str = match.groups()

                    if any(kw in descricao.upper() for kw in
                           ['TOTAL', 'PAGAMENTO', 'SALDO']):
                        continue

                    data = _normalizar_data(data_raw)
                    if not data:
                        continue

                    valor = _parse_valor_br(valor_str)
                    if valor <= 0:
                        continue

                    parcela_atual, parcela_total = _detectar_parcela(descricao)
                    grupo_parcela = str(uuid.uuid4()) if parcela_total else None
                    mes_ref = mes_referencia or f"{data[:4]}-{data[5:7]}"
                    hash_id = _gerar_hash(data, descricao, valor, membro)

                    transacoes.append({
                        'hash_dedup':         hash_id,
                        'fonte':              'xp',
                        'membro_id':          None,
                        'membro_nome':        membro,
                        'data':               data,
                        'descricao_original': descricao.strip(),
                        'descricao_norm':     None,
                        'valor':              round(valor, 2),
                        'categoria_id':       None,
                        'categoria_sugerida': None,
                        'confianca_norm':     0.0,
                        'classificacao_auto': 1,
                        'confianca':          0.0,
                        'parcela_atual':      parcela_atual,
                        'parcela_total':      parcela_total,
                        'grupo_parcela':      grupo_parcela,
                        'mes_referencia':     mes_ref,
                        'cartao':             'XP',
                    })

    except Exception as e:
        print(f"❌ Erro ao ler PDF XP {filepath.name}: {e}")

    print(f"📄 XP PDF: {len(transacoes)} transações de {filepath.name}")
    return transacoes


def parse_xp(
    filepath: str,
    membro: str,
    mes_referencia: Optional[str] = None
) -> list[dict]:
    """Entry point: detecta formato automaticamente."""
    ext = Path(filepath).suffix.lower()
    if ext == '.csv':
        return parse_xp_csv(filepath, membro, mes_referencia)
    elif ext == '.pdf':
        return parse_xp_pdf(filepath, membro, mes_referencia)
    elif ext in ('.xlsx', '.xls'):
        # XLSX pode ser extrato de cartão ou posição de investimentos
        # Tenta primeiro como extrato de cartão
        return parse_xp_csv(filepath, membro, mes_referencia)
    else:
        raise ValueError(f"Formato não suportado: {ext}")
