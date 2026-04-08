{% extends "base.html" %}
{% block title %}Dashboard · BRUDE{% endblock %}
{% block topbar_title %}Dashboard{% endblock %}
{% block topbar_extra %}
<select onchange="location='/?mes='+this.value">
  {% for m in meses_disp %}
    <option value="{{ m }}" {% if m==mes %}selected{% endif %}>{{ m }}</option>
  {% endfor %}
  {% if not meses_disp %}
    <option value="{{ mes }}">{{ mes }}</option>
  {% endif %}
</select>
{% endblock %}

{% block content %}
<!-- KPIs -->
<div class="kpi-grid">
  <div class="kpi green">
    <div class="kpi-label">Entradas</div>
    <div class="kpi-val">{{ total_receitas|brl }}</div>
    <div class="kpi-sub">Salários + comissão</div>
  </div>
  <div class="kpi red">
    <div class="kpi-label">Gastos Cartão</div>
    <div class="kpi-val">{{ total_gastos|brl }}</div>
    <div class="kpi-sub">{{ total_trans }} transações</div>
  </div>
  <div class="kpi {% if saldo >= 0 %}cyan{% else %}red{% endif %}">
    <div class="kpi-label">Saldo do Mês</div>
    <div class="kpi-val">{{ saldo|brl }}</div>
    <div class="kpi-sub">Entradas − gastos</div>
  </div>
  <div class="kpi amber">
    <div class="kpi-label">Parcelas Prox. Mês</div>
    <div class="kpi-val">{{ parcelas_prox|brl }}</div>
    <div class="kpi-sub">Já comprometido</div>
  </div>
  <div class="kpi purple">
    <div class="kpi-label">Investido Total</div>
    <div class="kpi-val">{{ inv_total|brl }}</div>
    <div class="kpi-sub">Rend. {{ inv_rend }}% · Prov. {{ inv_proventos|brl }}</div>
  </div>
  <div class="kpi {% if score >= 70 %}green{% elif score >= 50 %}amber{% else %}red{% endif %}">
    <div class="kpi-label">Score Financeiro</div>
    <div class="kpi-val">{{ score }}/100</div>
    <div class="kpi-sub">Poupança: {{ taxa_poupanca }}%</div>
  </div>
</div>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
  <!-- Gastos por Categoria -->
  <div class="card" style="grid-column:1/-1">
    <div class="card-title">
      Gastos por Categoria
      <a href="/transacoes?mes={{ mes }}" style="color:var(--accent);font-size:11px;text-decoration:none">ver todas →</a>
    </div>
    {% for cat, v in cats_list %}
    <div class="bar-row">
      <div class="bar-hdr">
        <span style="font-size:12px;font-weight:500">{{ cat }}</span>
        <span style="font-size:12px">
          <strong style="color:{% if v.status=='critico' %}var(--red){% elif v.status=='atencao' %}var(--amber){% else %}var(--green){% endif %}">
            {{ v.total|brl }}
          </strong>
          {% if v.meta %} / meta {{ v.meta|brl }} {% endif %}
          <span class="badge badge-{{ v.status }}">
            {% if v.status=='ok' %}✓ OK{% elif v.status=='atencao' %}⚠ Atenção{% else %}✗ Acima{% endif %}
          </span>
        </span>
      </div>
      <div class="bar-track">
        <div class="bar-fill {{ v.status }}"
             style="width:{% if v.meta %}{{ [v.pct,100]|min }}{% else %}50{% endif %}%"></div>
      </div>
      <!-- Por membro -->
      <div style="display:flex;gap:12px;margin-top:3px">
        {% for membro, val in v.por_membro.items() %}
          <span style="font-size:10px;color:var(--muted)">
            {{ membro }}: <strong>{{ val|brl }}</strong>
          </span>
        {% endfor %}
      </div>
    </div>
    {% else %}
      <p style="color:var(--muted);font-size:13px">
        Nenhum dado para {{ mes }}.
        <a href="/importar" style="color:var(--accent)">Importar fatura →</a>
      </p>
    {% endfor %}
  </div>
</div>

<!-- Gráficos -->
<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:0">
  <div class="card">
    <div class="card-title">Gastos por Categoria (Top 10)</div>
    <canvas id="chartCats" height="260"></canvas>
  </div>
  <div class="card">
    <div class="card-title">Histórico de Gastos</div>
    <canvas id="chartHist" height="260"></canvas>
  </div>
</div>
{% endblock %}

{% block scripts %}
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
const MES = "{{ mes }}";
fetch(`/api/grafico/${MES}`)
  .then(r => r.json())
  .then(data => {
    const cfg = {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#94a3b8', font:{size:10} } },
        y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#94a3b8', font:{size:10},
             callback: v => 'R$' + Math.round(v/1000) + 'k' } }
      }
    };

    // Gráfico categorias
    new Chart(document.getElementById('chartCats'), {
      type: 'bar',
      data: {
        labels: data.categorias.map(c => c.nome),
        datasets: [{
          label: 'Gasto',
          data: data.categorias.map(c => c.total),
          backgroundColor: data.categorias.map(c =>
            c.meta && c.total > c.meta ? 'rgba(239,68,68,0.7)' :
            c.meta && c.total > c.meta*0.85 ? 'rgba(245,158,11,0.7)' :
            'rgba(99,102,241,0.7)'
          ),
          borderRadius: 6,
        }, {
          label: 'Meta',
          data: data.categorias.map(c => c.meta),
          backgroundColor: 'rgba(16,185,129,0.2)',
          borderColor: 'rgba(16,185,129,0.5)',
          borderWidth: 1,
          borderRadius: 6,
        }]
      },
      options: { ...cfg, indexAxis: 'y',
        scales: {
          ...cfg.scales,
          x: { ...cfg.scales.x, ticks: { ...cfg.scales.x.ticks, callback: v => 'R$' + Math.round(v/1000)+'k' }},
          y: { ...cfg.scales.y, ticks: { color: '#94a3b8', font:{size:10} }}
        }
      }
    });

    // Gráfico histórico
    new Chart(document.getElementById('chartHist'), {
      type: 'line',
      data: {
        labels: data.historico.map(h => h.mes),
        datasets: [{
          label: 'Gastos',
          data: data.historico.map(h => h.gastos),
          borderColor: '#6366f1',
          backgroundColor: 'rgba(99,102,241,0.15)',
          fill: true,
          tension: 0.4,
          pointBackgroundColor: '#6366f1',
          borderWidth: 2,
          pointRadius: 4,
        }]
      },
      options: cfg
    });
  });
</script>
{% endblock %}
