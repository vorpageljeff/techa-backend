# Producao estavel do MVP

Data do marco: 2026-05-29
Tag: `prod-stable-mvp-2026-05-29`
Commit base do backend Render: `71e58e5`
Commit base do app/monorepo: `fca9552`
Backend: https://techa-backend.onrender.com

Este commit marca a versao estavel do backend em producao.

Estado esperado:
- Backend online no Render Free.
- Banco conectado.
- API leve com `ENABLE_PIPELINE=false`.
- Login, cadastro e recuperacao revisados.
- NDVI protegido com fallback quando arquivo local some no Render Free.
- PDF corrigido com imagem/fallback, data da imagem e data de processamento.

Decisoes importantes:
- O plano pago e o disco persistente do Render ficaram para depois.
- O pipeline Sentinel automatico nao roda junto da API no plano Free.
- Para testar, acordar o Render acessando `/health` antes de usar o app.

Daqui para frente, novas mudancas devem partir deste marco e preservar estes fluxos antes de evoluir novas features.

## Evolucao de 2026-07-23

- Adicionado suporte ao portal administrativo publicado separadamente no Vercel.
- Criada a migracao `0003_admin_portal`, com ultimo login, troca obrigatoria de
  senha e trilha de auditoria administrativa.
- A conta inicial usa `admin@techa.com.py`, senha temporaria forte fora do Git e
  exige troca no primeiro acesso.
- O bootstrap antigo, que permitia autopromocao do primeiro usuario, foi
  substituido por um fluxo protegido e inoperante depois da criacao do admin.
- Android, iOS e web mobile continuam usando as mesmas rotas e o mesmo banco.
