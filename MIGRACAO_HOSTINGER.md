# Migração do Techá para a Hostinger

## Estado em 9 de setembro de 2026

O backend e os clientes web publicados estão usando a Hostinger. O serviço
`techa-backend`, o disco e o banco `techa-db` foram excluídos do Render.
O cartão foi removido do workspace. A cobrança projetada no painel caiu para
US$ 10,48, igual ao consumo já acumulado no mês; não há projeção adicional.

API provisória na Hostinger: `https://techa-api.2.25.189.129.nip.io`.
O domínio segue o padrão já utilizado pelo Transboes na VPS. Pode ser substituído
por um domínio próprio sem reinstalar a aplicação.

- Código local e API publicada: `c7bd84a`.
- API: `https://techa-backend.onrender.com`, serviço `srv-d7ut351j2pic73c826a0`, plano Starter.
- Disco da API: 10 GB. Preservar tiles e rasters antes da exclusão.
- PostgreSQL 15: `techa-db`, ID `dpg-d95v9enaqgkc73ejcnl0-a`, Basic-256mb, armazenamento de 15 GB.
- `techa-redis` já aparece como excluído na cobrança; verificar referências remanescentes nas variáveis.
- Pipeline automático desabilitado em produção. Manter esse comportamento na migração.
- Destino identificado no hPanel: `srv1964191.hstgr.cloud`, `2.25.189.129`, Ubuntu 24.04, 1 CPU, 4 GB RAM e 50 GB de disco.
- O servidor é compartilhado com outro projeto. Não substituir bancos, volumes, proxy ou configurações existentes.
- SSH: usuário `innovagro`, chave local `~/.ssh/transboes_hostinger`. O servidor bloqueia SSH como root (`PermitRootLogin no`); essa configuração foi preservada.

## Implantação e validações concluídas

- Código em `/opt/innovagro/apps/techa`; configurações privadas em `.env.production`, fora do Git e da imagem Docker.
- Containers `techa-api-1` e `techa-db-1`; volumes próprios `techa_api_data` e `techa_postgres_data`.
- PostgreSQL 15/PostGIS 3.4 no destino. As 9 tabelas da aplicação restauradas tiveram contagens e hashes iguais aos da origem (excluída a tabela de referência da extensão PostGIS).
- Dados conferidos: 3 usuários, 6 propriedades, 8 talhões, 499 análises, 13 anomalias e 8 inspeções.
- Os 75 arquivos de tiles/rasters foram copiados e validados com SHA-256. Aproximadamente 4,1 GB de dados.
- Backup inicial do banco em `~/Documents/Backups_Techa/2026-09-09/techa-db-inicial.dir.tar.gz` neste computador; cópia e backup do disco em `/home/innovagro/techa-migration/backups` na VPS. A cópia adicional do disco neste computador foi concluída em `techa-data-inicial.tar.gz`; os 75 arquivos foram conferidos com SHA-256.
- 55 testes unitários aprovados em container separado.
- Teste funcional autenticado: 3 usuários, 6 propriedades, 8 talhões, histórico/anomalias, 8 imagens PNG NDVI, PDF e autorização administrativa aprovados.
- `/ready` por HTTPS retorna `database=connected`; certificado validado pelo cliente HTTPS.
- Teste HTTPS de CORS, cadastro, login com senha e criação/remoção de propriedade e talhão aprovado. Conta temporária removida; os hashes do banco continuaram idênticos aos da origem após os testes.
- Transboes permaneceu saudável e seu endpoint HTTPS continuou respondendo.
- O pacote do macOS trouxe metadados `._*` que impediam o Alembic de iniciar. Removidos do pacote enviado e excluídos da imagem por `.dockerignore`.

Os segredos JWT originais foram preservados. A chave pública temporária
`techa-migration-2026-09-09` foi removida da conta Render depois da conferência
final dos dados.

## Operação na VPS

```sh
ssh -i ~/.ssh/transboes_hostinger innovagro@2.25.189.129
cd /opt/innovagro/apps/techa
docker compose --env-file .env.production -f deploy/compose.hostinger.yml -f deploy/compose.https.yml ps
```

Os mesmos arquivos Compose devem ser usados nas atualizações para preservar o
roteamento HTTPS. A porta `18010` está publicada somente em loopback para diagnóstico.
O volume de arquivos foi criado antes da primeira inicialização para restaurar os
dados; o aviso do Compose sobre volume preexistente é esperado nesta instalação.

## Clientes que precisam ser atualizados

- `https://techa-mobile-web.vercel.app`: deployment `dpl_2MpqSV6xSwqdq7oAXgWKKTHZDERt`.
- `https://techa-admin-portal.vercel.app`: deployment `dpl_9rP74u6tNs1fuKk2Z5mqxnqsiF91`.
- Cliente antigo `https://mobile-dusky-alpha.vercel.app`: confirmar se ainda está em uso.

Os dois deployments mais recentes foram publicados manualmente a partir do commit
`a064151e2cae331d96177631ad4b679827cce391`, com alterações locais não commitadas,
em branches `feat/responsive-mobile-web` e `feat/admin-portal`.
O repositório `vorpageljeff/app_mobile_techa` contém apenas um README. Os 118 arquivos enviados nos três deployments foram recuperados da Vercel e preservados em `~/Documents/Backups_Techa/2026-09-09/frontend-source`. O app Expo atual está disponível em `../techa-mobile-recuperado`, com a API padrão e os perfis EAS apontando para a Hostinger. Essa cópia não tem histórico Git próprio; o backup preserva os arquivos originais.

A inspeção dos arquivos efetivamente publicados confirmou uma alternativa para
a migração: ambos usam `/api/v1` no próprio domínio da Vercel; o mobile verifica
também `/backend-ready`. É possível manter os deployments atuais e adicionar
regras de encaminhamento no projeto Vercel para a API Hostinger. A constante
antiga `DEFAULT_API_URL` no bundle mobile está exportada, mas não é consumida
nesse bundle. As regras foram promovidas nos dois projetos. Os endereços públicos
`/backend-ready` dos projetos mobile e administrativo responderam com o banco da
Hostinger conectado depois da exclusão do Render.

Regras planejadas nos projetos `techa-mobile-web` e `techa-admin-portal`:

| Origem | Destino |
| --- | --- |
| `/api/v1/:path*` | `https://techa-api.2.25.189.129.nip.io/api/v1/:path*` |
| `/backend-ready` | `https://techa-api.2.25.189.129.nip.io/ready` |

Confirmar qual cliente web é utilizado antes de alterar o projeto legado `mobile`.
Seu bundle `index-b2b0c83fb9070f5083d255262be376e3.js` chama o Render diretamente,
diferentemente dos dois projetos mais recentes. Uma regra `/api/v1` nesse projeto
não muda essas chamadas diretas. Será necessário atualizar o bundle/publicação
ou encaminhar seus visitantes ao cliente atual, conforme o uso confirmado.
As regras devem ser preparadas em staging e publicadas após a sincronização final
dos dados. Preservar a configuração anterior para rollback.

O workspace Render está no plano Hobby gratuito. Permanecem `viagem-jj-api`
(Free) e os recursos suspensos `maxicon-ai-portal-api` e
`maxicon-ai-portal-db`. Esses projetos não foram excluídos. Sem cartão cadastrado,
o Render informa que novos serviços pagos não podem ser criados até o próximo
ciclo.

## Sequência de execução

1. Restabelecer o acesso ao servidor e inventariar containers, volumes, redes, proxy, portas, recursos livres e backups existentes.
2. Exportar o banco e copiar o disco persistente do Render. Guardar cópias fora do Render e verificar integridade e restauração. A exportação inicial já foi baixada e restaurada; repetir a sincronização na troca definitiva.
3. Confirmar versão da extensão PostGIS e usar PostgreSQL/PostGIS compatíveis na restauração.
4. Implantar o Techá com nome de projeto Compose, banco e volumes próprios. O Compose local atual é de desenvolvimento e publica portas de banco; não o executar diretamente em produção.
5. Preservar segredos JWT, configurações e dados; adaptar apenas conexões e caminhos necessários. Não versionar credenciais nem backups.
6. Definir domínio HTTPS da API e integrar ao proxy existente após conferir a configuração efetiva do servidor.
7. Restaurar dados e arquivos em ambiente isolado. Validar banco conectado, autenticação, propriedades/talhões, mapas NDVI, relatórios e administração. `/health` sozinho não comprova integridade dos dados.
8. Atualizar os consumidores da API: `frontend/site/src/config.ts`, `mobile/App.js`, variáveis dos deployments e aplicações publicadas separadamente. Aplicativos já distribuídos com o endereço `onrender.com` precisam de atualização antes do desligamento.
9. Coordenar uma janela sem gravações no banco de origem, realizar a sincronização final, validar a nova produção e manter possibilidade de retorno até o aceite da migração.
10. Desativar o workflow `.github/workflows/keep-render-awake.yml` e a recriação automática por Blueprint. Somente depois excluir API, disco e banco do Render, dentro do escopo confirmado.
11. Conferir todos os workspaces, recursos ativos/suspensos e a cobrança final. Cobranças acumuladas antes do encerramento podem permanecer; excluir serviços não cancela consumo já realizado.

## Pendências antes do desligamento

- Sincronização final de banco/arquivos antes da troca dos clientes.
- Inventário e atualização dos clientes web/mobile/admin.
- Validação dos clientes publicados utilizando a nova API.
- Decisão sobre os outros projetos no Render.

## App Expo recuperado

A configuração Expo, a checagem TypeScript e os 7 testes Jest passaram na cópia recuperada. A referência histórica a um APK estável foi preservada no documento original. Confirmar se há APK instalado em uso: atualizar o código não altera APKs já distribuídos. A validação real Android/iOS e a execução no Expo Go ainda estão pendentes.

A exportação web do app recuperado foi concluída com sucesso (`npm run build:web`).

Exportação dos bundles Android e iOS concluída (`expo export --platform android --platform ios`). Isso valida o empacotamento JavaScript; não constitui build APK/IPA nem teste em dispositivo ou simulador. Os 118 arquivos originais recuperados tiveram SHA-1 correspondente ao ID de conteúdo informado pela Vercel.

## Preparação adicional

- Usuário confirmou uso do APK instalado e reiterou encerramento do Render após a atualização. Novo APK Android versionCode 12 solicitado no EAS: `01008e4b-9d31-4635-9836-5da66049b165`, com assinatura original; aguarda conclusão e teste real.
- Cliente web legado recuperado em `../techa-web-legado-recuperado`; somente URL da API alterada. Exportação local aprovada. Preview Vercel `dpl_E5L1ZiSunu4CZyZTgUfNxB1ZMfNS`, `https://mobile-9oca1j38b-vorpageljeffs-projects.vercel.app`, pronto; navegador carregou formulário e chamou `/health` da Hostinger com HTTP 200. Ainda não promovido para produção.
- Backups locais na VPS: `/opt/innovagro/backups/techa`. Script `deploy/backup-hostinger.sh`: banco diário às 03:15 e arquivos aos domingos às 03:45, horário do servidor; retenção aproximada de 14 dias. Crontab do usuário innovagro, antes vazio. Primeiro dump passou na conferência do catálogo pg_restore. A rotina semanal de arquivos ainda não foi executada. Backups no mesmo servidor não substituem as cópias externas já guardadas neste computador.

### Acompanhamento do APK

O painel Expo informou fila gratuita estimada em ~66,8 minutos, antes da compilação. Monitor iniciado em `/tmp/techa-migration-session/watch-expo-build.py` (sessão de execução 49546), com até 180 consultas espaçadas em 60 segundos. Ao concluir, baixa e confere a integridade ZIP em `~/Documents/Backups_Techa/2026-09-09/apk/techa-hostinger-v12.apk`, registra SHA-256 e `build-result.json`. Não confundir a conclusão do build com validação da assinatura comparada ao APK anterior ou teste real no celular: essas verificações seguem pendentes. O APK antigo deixou de acessar o backend quando o serviço Render foi excluído; instalar a versão 12 assim que o build terminar.

### Encerramento no Render

- `techa-backend` retorna HTTP 404 e o banco Render deixou de aceitar conexões.
- Contagens e hashes do banco e SHA-256 dos 75 arquivos ainda coincidiam com a
  Hostinger imediatamente antes da exclusão.
- O painel mostra três recursos restantes, correspondentes ao serviço gratuito
  `viagem-jj-api` e aos dois recursos Maxicon suspensos.
- Workspace Hobby: US$ 0/mês. Cartão removido. Total do mês e projeção final:
  US$ 10,48. Esse valor já consumido ainda pode ser faturado; não é cobrança
  futura da Hostinger.
- O Blueprint `techa-backend` foi desconectado e deixou de aparecer na lista de
  Blueprints, impedindo a recriação automática dos recursos apagados.
- A chave SSH temporária `techa-migration-2026-09-09` foi excluída; a conta
  Render voltou a mostrar `No authorized SSH keys`.
