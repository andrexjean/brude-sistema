"""
BRUDE - Normalizer
Normaliza descrições de fatura: limpeza → dicionário → fuzzy fallback.
Estrutura preparada para aprendizado com correções manuais.
"""
import re
import sqlite3
from typing import Optional
from rapidfuzz import fuzz, process


# ── Limpeza básica ────────────────────────────────────────────
_PREFIXOS = re.compile(
    r'^(COMPRA\s+|PARC\s+\d+/\d+\s+|PARCELA\s+\d+/\d+\s+|'
    r'PIX\s+|TED\s+|DOC\s+|DEBITO\s+|CREDITO\s+|'
    r'\*+|SP\s+\*+|RJ\s+\*+|MG\s+\*+|'
    r'EC\s+\*+|PAG\s+\*+)',
    re.IGNORECASE
)

_SUFIXOS = re.compile(
    r'(\s+\d{2}/\d{2}|\s+SAO PAULO|\s+SÃO PAULO|\s+SP|\s+RJ|\s+MG|'
    r'\s+BR|\s+BRL|\s+\d{10,}|\s+\*+\d+)$',
    re.IGNORECASE
)

_ESPACOS = re.compile(r'\s{2,}')
_NUMEROS_ISOLADOS = re.compile(r'\b\d{4,}\b')
_ESPECIAIS = re.compile(r'[^\w\s\-/]', re.UNICODE)


def limpar_descricao(texto: str) -> str:
    """
    Limpeza inicial: remove prefixos de banco, sufixos de localização,
    números isolados e caracteres especiais.
    """
    t = texto.strip().upper()
    # Remove prefixos de banco
    t = _PREFIXOS.sub('', t)
    # Remove sufixos de localização
    t = _SUFIXOS.sub('', t)
    # Remove números muito longos (IDs de transação)
    t = _NUMEROS_ISOLADOS.sub('', t)
    # Remove caracteres especiais exceto - e /
    t = _ESPECIAIS.sub(' ', t)
    # Normaliza espaços
    t = _ESPACOS.sub(' ', t).strip()
    return t


# ── Normalizer principal ──────────────────────────────────────
class Normalizer:
    """
    Normaliza descrições em 3 camadas:
    1. Limpeza de texto (regex)
    2. Dicionário do banco (exato e regex)
    3. Fuzzy matching como fallback
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._cache_dict: list[dict] = []
        self._cache_nomes: list[str] = []
        self._carregar_dicionario()

    def _carregar_dicionario(self):
        """Carrega dicionário de normalização do banco."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT padrao, nome_norm, categoria, tipo FROM dict_normalizacao"
            ).fetchall()
            conn.close()

            self._cache_dict = [dict(r) for r in rows]
            self._cache_nomes = [r['nome_norm'] for r in self._cache_dict]
        except Exception as e:
            print(f"⚠️  Erro carregando dicionário: {e}")
            self._cache_dict = []
            self._cache_nomes = []

    def normalizar(
        self, descricao_original: str
    ) -> tuple[str, Optional[str], float]:
        """
        Normaliza uma descrição.

        Retorna:
            (descricao_normalizada, categoria_sugerida, confianca)

        Confiança:
            1.0  = match exato no dicionário
            0.9  = match por regex no dicionário
            0.75 = fuzzy com score alto (>= 85)
            0.5  = fuzzy com score médio (>= 70)
            0.3  = sem match, apenas limpeza
        """
        texto_limpo = limpar_descricao(descricao_original)

        # Camada 1: match exato no dicionário
        for entry in self._cache_dict:
            if entry['tipo'] == 'exato':
                if texto_limpo == entry['padrao'].upper():
                    self._incrementar_uso(entry['padrao'])
                    return entry['nome_norm'], entry['categoria'], 1.0

        # Camada 2: match por regex/contains no dicionário
        for entry in self._cache_dict:
            if entry['tipo'] in ('regex', 'exato'):
                padrao = entry['padrao'].upper()
                if padrao in texto_limpo:
                    self._incrementar_uso(entry['padrao'])
                    return entry['nome_norm'], entry['categoria'], 0.9

        # Camada 3: fuzzy matching
        if self._cache_nomes:
            result = process.extractOne(
                texto_limpo,
                self._cache_nomes,
                scorer=fuzz.token_set_ratio,
                score_cutoff=70
            )
            if result:
                nome_match, score, idx = result
                confianca = 0.75 if score >= 85 else 0.5
                entry = self._cache_dict[idx]
                return nome_match, entry['categoria'], confianca

        # Sem match: retorna texto limpo capitalizado
        nome_capitalizado = texto_limpo.title()
        return nome_capitalizado, None, 0.3

    def _incrementar_uso(self, padrao: str):
        """Incrementa contador de uso no banco (async seria ideal em prod)."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "UPDATE dict_normalizacao SET usos = usos + 1 WHERE padrao = ?",
                (padrao,)
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    def aprender_correcao(
        self,
        descricao_original: str,
        nome_correto: str,
        categoria_correta: str
    ):
        """
        Registra uma correção manual no dicionário para aprendizado futuro.
        Essa é a base do feedback loop — quando o usuário corrigir uma
        classificação errada, o sistema aprende.
        """
        texto_limpo = limpar_descricao(descricao_original)
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
                INSERT OR REPLACE INTO dict_normalizacao
                    (padrao, nome_norm, categoria, tipo, usos)
                VALUES (?, ?, ?, 'exato', 1)
            """, (texto_limpo, nome_correto, categoria_correta))
            conn.commit()
            conn.close()
            # Recarrega cache
            self._carregar_dicionario()
            print(f"✅ Aprendido: '{texto_limpo}' → '{nome_correto}' [{categoria_correta}]")
        except Exception as e:
            print(f"❌ Erro ao aprender correção: {e}")

    def recarregar(self):
        """Recarrega dicionário do banco (após alterações manuais)."""
        self._carregar_dicionario()


# ── Detecção de parcelamentos ─────────────────────────────────
_PARCELA_PATTERNS = [
    re.compile(r'(\d{1,2})/(\d{1,2})'),           # "3/10" ou "03/10"
    re.compile(r'PARC\w*\s+(\d{1,2})\s*/\s*(\d{1,2})', re.IGNORECASE),
    re.compile(r'(\d{1,2})\s+DE\s+(\d{1,2})',      re.IGNORECASE),
    re.compile(r'PARCELA\s+(\d{1,2})',              re.IGNORECASE),
]


def detectar_parcela(texto: str) -> tuple[Optional[int], Optional[int]]:
    """
    Detecta parcelamento no texto da fatura.

    Retorna: (parcela_atual, parcela_total)
    Ex: "SHOPEE 3/10" → (3, 10)
    Ex: "AMAZON 5/12" → (5, 12)
    """
    for pattern in _PARCELA_PATTERNS:
        match = pattern.search(texto)
        if match:
            groups = match.groups()
            if len(groups) >= 2:
                try:
                    atual = int(groups[0])
                    total = int(groups[1])
                    # Sanidade: parcela_atual <= total, total >= 2, total <= 72
                    if 1 <= atual <= total <= 72:
                        return atual, total
                except ValueError:
                    continue
    return None, None


def extrair_mes_referencia(texto: str) -> Optional[str]:
    """
    Detecta mês de referência em texto de fatura.
    Ex: "Fatura Abril/2026" → "2026-04"
    """
    meses = {
        'janeiro': '01', 'fevereiro': '02', 'março': '03', 'marco': '03',
        'abril': '04', 'maio': '05', 'junho': '06', 'julho': '07',
        'agosto': '08', 'setembro': '09', 'outubro': '10',
        'novembro': '11', 'dezembro': '12'
    }

    pattern = re.compile(
        r'(' + '|'.join(meses.keys()) + r')[/\s]+(\d{4})',
        re.IGNORECASE
    )
    match = pattern.search(texto)
    if match:
        mes_nome = match.group(1).lower()
        ano = match.group(2)
        return f"{ano}-{meses[mes_nome]}"

    # Tenta formato MM/AAAA ou MM-AAAA
    pattern2 = re.compile(r'(\d{2})[/\-](\d{4})')
    match2 = pattern2.search(texto)
    if match2:
        return f"{match2.group(2)}-{match2.group(1)}"

    return None
