{% extends "base.html" %}
{% block title %}Investimentos · BRUDE{% endblock %}
{% block topbar_title %}Investimentos{% endblock %}

{% block content %}
<div style="display:grid;grid-template-columns:340px 1fr;gap:16px;align-items:start">

  <!-- Formulário -->
  <div class="card">
    <div class="card-title">Lançar posição do mês</div>
    <p style="font-size:12px;color:var(--muted);margin-bottom:16px;line-height:1.6">
      Preencha saldo XP e Nubank todo mês. São apenas 2 números por banco.
    </p>
    <form method="POST">
      <div class="form-group">
        <label>Mês de referência</label>
        <input type="month" name="mes" value="{{ mes_atual }}" required>
      </div>
      <div class="form-group">
        <label>Titular</label>
        <select name="membro">
          {% for m in membros %}<option value="{{ m }}">{{ m }}</option>{% endfor %}
        </select>
      </div>
      <div class="form-group">
        <label>Instituição</label>
        <select name="instituicao">
          <option value="XP">XP Investimentos</option>
          <option value="Nubank">Nubank Caixinha</option>
        </select>
      </div>
      <div class="form-group">
        <label>Saldo atual (R$)</label>
        <input type="number" name="saldo" step="0.01" min="0" placeholder="59730.00" required>
      </div>
      <div class="form-group">
        <label>Aporte do mês (R$)</label>
        <input type="number" name="aporte" step="0.01" min="0" placeholder="1000.00" value="0">
      </div>
      <div class="form-group">
        <label>Proventos FII (R$)</label>
        <input type="number" name="proventos" step="0.01" min="0" placeholder="143.92" value="0">
      </div>
      <div class="form-group">
        <label>Rendimento do mês (%)</label>
        <input type="number" name="rendimento_pct" step="0.01" placeholder="2.77" value="0">
      </div>
      <button type="submit" class="btn btn-primary" style="width:100%;padding:12px">
        💾 Salvar posição
      </button>
    </form>
  </div>

  <!-- Histórico -->
  <div>
    <div class="card" style="padding:0">
      <div style="padding:16px 20px 0;font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)">
        Histórico de posições
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Mês</th>
              <th>Titular</th>
              <th>Instituição</th>
              <th style="text-align:right">Saldo</th>
              <th style="text-align:right">Aporte</th>
              <th style="text-align:right">Proventos</th>
              <th style="text-align:right">Rend.</th>
            </tr>
          </thead>
          <tbody>
            {% for h in historico %}
            <tr>
              <td style="font-size:12px;color:var(--muted)">{{ h.mes }}</td>
              <td>
                <span style="color:{% if h.membro_nome=='André' %}#60a5fa{% else %}#f9a8d4{% endif %};font-size:12px;font-weight:600">
                  {{ h.membro_nome }}
                </span>
              </td>
              <td style="font-size:12px">{{ h.instituicao }}</td>
              <td class="td-val td-green" style="text-align:right">{{ h.saldo|brl }}</td>
              <td class="td-val" style="text-align:right;color:var(--accent)">{{ h.aporte_mes|brl }}</td>
              <td class="td-val" style="text-align:right;color:var(--purple)">{{ h.proventos_mes|brl }}</td>
              <td style="text-align:right;font-size:12px;color:{% if h.rendimento_pct > 0 %}var(--green){% else %}var(--red){% endif %}">
                {{ "%.2f"|format(h.rendimento_pct*100) }}%
              </td>
            </tr>
            {% else %}
            <tr><td colspan="7" style="text-align:center;color:var(--muted);padding:32px">
              Nenhum dado ainda. Lance a posição do mês ao lado.
            </td></tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    </div>
  </div>
</div>
{% endblock %}
