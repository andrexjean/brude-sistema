<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BRUDE Finanças — Login</title>
<style>
:root{--bg:#0a0f1e;--surface:#111827;--surface2:#1a2235;--border:rgba(99,130,201,0.18);--accent:#6366f1;--accent2:#818cf8;--cyan:#22d3ee;--text:#e2e8f0;--muted:#94a3b8;--red:#ef4444}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;display:flex;align-items:center;justify-content:center}
.wrap{width:100%;max-width:360px;padding:2rem}
.logo{text-align:center;margin-bottom:2.5rem}
.logo-text{font-size:44px;font-weight:800;letter-spacing:-2px;background:linear-gradient(135deg,var(--accent2),var(--cyan));-webkit-background-clip:text;-webkit-text-fill-color:transparent;display:block}
.logo-sub{font-size:12px;letter-spacing:.2em;text-transform:uppercase;color:var(--muted);margin-top:4px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:28px;box-shadow:0 8px 48px rgba(0,0,0,.6)}
label{display:block;font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-bottom:8px}
input[type=password]{width:100%;background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:12px 14px;color:var(--text);font-size:14px;outline:none;transition:border .2s;margin-bottom:14px}
input[type=password]:focus{border-color:var(--accent)}
button{width:100%;background:var(--accent);color:#fff;border:none;border-radius:8px;padding:12px;font-size:14px;font-weight:700;cursor:pointer;transition:.15s;margin-top:4px}
button:hover{background:var(--accent2)}
.erro{background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.3);border-radius:8px;padding:10px 14px;font-size:13px;color:#fca5a5;margin-bottom:14px}
.hint{text-align:center;font-size:11px;color:var(--muted);margin-top:20px;line-height:1.6}
</style>
</head>
<body>
<div class="wrap">
  <div class="logo">
    <span class="logo-text">BRUDE</span>
    <div class="logo-sub">Família Oliveira · Sistema privado</div>
  </div>
  <div class="card">
    {% if erro %}
      <div class="erro">{{ erro }}</div>
    {% endif %}
    <form method="POST">
      <label>Senha de acesso</label>
      <input type="password" name="senha" placeholder="••••••••"
             autocomplete="current-password" autofocus required>
      <button type="submit">Entrar</button>
    </form>
    <div class="hint">
      Dados criptografados · Acesso familiar privado
    </div>
  </div>
</div>
</body>
</html>
