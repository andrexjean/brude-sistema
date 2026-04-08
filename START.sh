services:
  - type: web
    name: brude-financas
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
    envVars:
      - key: SECRET_KEY
        generateValue: true
      - key: APP_PASSWORD_HASH
        value: "Defina após o deploy via configurações"
    disk:
      name: brude-data
      mountPath: /opt/render/project/src/data
      sizeGB: 1
