"""
BRUDE - Classifier
Classifica transações por categoria usando regras + confiança.
Preparado para receber modelo ML no futuro sem mudar a interface.
"""
import re
from typing import Optional


# ── Regras de classificação ───────────────────────────────────
# Formato: (regex_pattern, categoria, confianca)
# Ordenadas por especificidade (mais específica primeiro)
REGRAS: list[tuple[str, str, float]] = [
    # Saúde/Academia
    (r'TOTALPASS|ACADEMIA|SMARTFIT|BLUEFIT|BODYTECH', 'Saúde/Academia', 0.95),
    # Saúde/Farmácia
    (r'FARMACIA|DROGARIA|DROGA\w+|ULTRAFARMA|PANVEL|NISSEI', 'Saúde/Farmácia', 0.95),
    (r'CLINICA|HOSPITAL|LABORATORIO|EXAME|CONSULTA', 'Saúde/Farmácia', 0.90),
    # Seguros
    (r'ALLIANZ|HDI SEGUROS|PORTO SEGURO|BRADESCO SEG|TOKIO', 'Seguros', 0.98),
    # Educação
    (r'ESCOLA|COLEGIO|COLÉGIO|FACULDADE|UNIVERSIDADE|UDEMY|COURSERA', 'Educação', 0.95),
    # Assinaturas (streaming)
    (r'NETFLIX|SPOTIFY|DISNEY\+?|HBO\s*MAX|AMAZON\s*PRIME', 'Assinaturas', 0.99),
    (r'APPLE\.COM|GOOGLE\s*PLAY|MICROSOFT|ADOBE|OPENAI|CLAUDE|CHATGPT', 'Assinaturas', 0.95),
    (r'TOTALPASS', 'Assinaturas', 0.90),  # fallback
    # Supermercado
    (r'CARREFOUR|EXTRA\s|ASSAI|ATACADAO|ATACADÃO|PAO\s+DE\s+ACUCAR', 'Supermercado', 0.95),
    (r'PREZUNIC|GUANABARA|BISTEK|STMARCHE|SHIBATA|CONDOR', 'Supermercado', 0.95),
    (r'GIGA\s*ATACADO|SUPER\s*CITY|FRUTOS\s*DA\s*HORTA', 'Supermercado', 0.95),
    # Combustível
    (r'POSTO\s|PETROBRAS|IPIRANGA|SHELL|BR\s+DIST|ALE\s|RAIZEN', 'Combustível', 0.95),
    # Transporte
    (r'UBER(?!EATS)\b|UBER\*(?!EATS)', 'Transporte', 0.97),
    (r'99\s*APP|99\s*\*|TAXI|CABIFY', 'Transporte', 0.95),
    (r'VELOE|SEM\s+PARAR|GREENPASS|CONECTCAR', 'Transporte', 0.98),
    (r'LOCALIZA|MOVIDA|UNIDAS|HERTZ', 'Transporte', 0.95),
    # Alimentação (delivery e restaurantes)
    (r'IFOOD|RAPPI|UBER\s*EATS|JAMES\s*DELIVERY', 'Alimentação', 0.97),
    (r'MC\s*DONALDS|BURGER\s*KING|KFC\b|SUBWAY|HABIB|GIRAFFAS', 'Alimentação', 0.97),
    (r'SUSHI|PIZZA|RESTAURANTE|LANCHONETE|PADARIA|CHURRASCARIA', 'Alimentação', 0.90),
    (r'BAR\s|BOTECO|CAFE\s|CAFETERIA|CONFEITARIA|SORVETE', 'Alimentação', 0.85),
    (r'SWEETCO|FIFO\s|VELHO\s+BURGER|IMPERIAL\s+SUSHI', 'Alimentação', 0.95),
    # Compras Online
    (r'MERCADO\s*LIVRE|ML\s+\*|SHOPEE|SHEIN\b|AMAZON(?!PRIME)', 'Compras Online', 0.97),
    (r'ALIEXPRESS|AMERICANAS|NETSHOES|DAFITI|ZATTINI', 'Compras Online', 0.95),
    (r'KABUM|TERABYTE|PICHAU', 'Compras Online', 0.95),
    # Roupas
    (r'RENNER|RIACHUELO|C&A\b|CEA\b|MARISA\b|ZARA\b|H&M\b|HERING', 'Roupas', 0.95),
    (r'CENTAURO|DECATHLON|NETSHOES|DAFITI', 'Roupas', 0.85),
    # Viagem
    (r'AZUL\s+LINHAS|GOL\s+LINHAS|LATAM', 'Viagem', 0.99),
    (r'AIRBNB|BOOKING|DECOLAR|CVC\b|HOTEL|POUSADA', 'Viagem', 0.95),
    # Casa/Moradia
    (r'ENEL|CEMIG|COPEL|COELBA|ENERGISA', 'Casa/Moradia', 0.99),   # luz
    (r'SABESP|CEDAE|SANEPAR|EMBASA|CAEMA', 'Casa/Moradia', 0.99),   # água
    (r'VIVO|CLARO|TIM\b|OI\b|NET\b|SKY\b', 'Casa/Moradia', 0.95),  # telecom
    # Bebidas
    (r'AMBEV|HEINEKEN|SKOL|BRAHMA|CACHAÇA|ADEGA|BEERHOUSE', 'Bebidas', 0.90),
    # Manutenção
    (r'MECANICA|BORRACHARIA|OFICINA|LAVAGEM\s+AUTO', 'Manutenção', 0.90),
    # Eletrodomésticos
    (r'HAVAN|MAGAZINE\s+LUIZA|CASAS\s+BAHIA|PONTO\s+FRIO|FAST\s+SHOP', 'Eletrodomésticos', 0.85),
]

# Compiladas uma vez
_REGRAS_COMPILADAS = [
    (re.compile(pattern, re.IGNORECASE), categoria, confianca)
    for pattern, categoria, confianca in REGRAS
]


class Classifier:
    """
    Classificador baseado em regras com pontuação de confiança.
    Interface preparada para receber modelo ML sem quebrar código existente.
    """

    def __init__(self, categorias_db: dict):
        """
        categorias_db: dict {nome_categoria: id} vindo do banco.
        """
        self.categorias = categorias_db

    def classificar(
        self,
        descricao_norm: str,
        descricao_original: str,
        categoria_sugerida_normalizer: Optional[str] = None,
        confianca_normalizer: float = 0.0
    ) -> tuple[Optional[int], float]:
        """
        Classifica uma transação.

        Retorna: (categoria_id, confianca)

        Estratégia:
        1. Regras por regex (mais confiável, específico)
        2. Sugestão do normalizer (vem do dicionário de normalização)
        3. Fallback para 'Outros'
        """

        # Texto para matching: usa ambos original e normalizado
        texto = f"{descricao_original} {descricao_norm}".upper()

        melhor_cat = None
        melhor_conf = 0.0

        # Camada 1: regras por regex
        for pattern, categoria, confianca in _REGRAS_COMPILADAS:
            if pattern.search(texto):
                if confianca > melhor_conf:
                    melhor_conf = confianca
                    melhor_cat = categoria
                    if confianca >= 0.97:
                        break  # match de alta confiança, para aqui

        # Camada 2: sugestão do normalizer (se mais confiável)
        if (categoria_sugerida_normalizer and
                confianca_normalizer > melhor_conf and
                categoria_sugerida_normalizer in self.categorias):
            melhor_cat = categoria_sugerida_normalizer
            melhor_conf = confianca_normalizer

        # Resolve para ID
        if melhor_cat and melhor_cat in self.categorias:
            return self.categorias[melhor_cat], melhor_conf

        # Fallback: 'Outros'
        outros_id = self.categorias.get('Outros')
        return outros_id, 0.1

    def classificar_lote(
        self, transacoes: list[dict]
    ) -> list[dict]:
        """
        Classifica uma lista de transações.
        Cada transação deve ter: descricao_norm, descricao_original,
        categoria_sugerida (opcional), confianca_norm (opcional).
        """
        resultado = []
        for t in transacoes:
            cat_id, conf = self.classificar(
                descricao_norm=t.get('descricao_norm', ''),
                descricao_original=t.get('descricao_original', ''),
                categoria_sugerida_normalizer=t.get('categoria_sugerida'),
                confianca_normalizer=t.get('confianca_norm', 0.0)
            )
            t['categoria_id'] = cat_id
            t['confianca'] = conf
            t['classificacao_auto'] = 1
            resultado.append(t)
        return resultado

    def itens_baixa_confianca(
        self, transacoes: list[dict], threshold: float = 0.5
    ) -> list[dict]:
        """
        Retorna transações com confiança abaixo do threshold.
        Esses itens devem ser apresentados para revisão manual.
        """
        return [t for t in transacoes if t.get('confianca', 0) < threshold]
