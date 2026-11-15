# Games Deals Crawler


- **php** [http://localhost:8081/](http://localhost:8081/)
- **php-myadmin** [http://localhost:8082/](http://localhost:8081/)

Projeto Python para coletar jogos gratuitos ativos da Epic Games Store e jogos em promoção na Steam (loja Brasil), persistindo os dados em MySQL.

## Funcionalidades

- Crawler Epic Games usando o endpoint público de promoções gratuitas.
- Crawler Steam usando a página de busca com `specials=1` e `hidef2p=1`.
- Paginação da Steam (`start` / `count`) e idioma/região brasileiros.
- Criação automática do banco e das tabelas antes da coleta.
- UPSERT para não duplicar lojas, jogos e ofertas.
- Histórico de preços Steam somente quando preço, preço original, moeda ou desconto mudam.
- Registro de execuções em `crawler_runs`.
- Execução individual ou conjunta dos crawlers.

> A coleta depende do HTML/API disponibilizados pelas lojas, que podem mudar sem aviso. Respeite os limites dos serviços e evite intervalos agressivos.

## Requisitos

### Execução Local
- Python 3.10+
- MySQL 8.0+ (o schema usa `utf8mb4_0900_ai_ci`)
- Usuário MySQL com permissão para criar o banco/tabelas e inserir/atualizar registros.

### Execução via Docker
- Docker e Docker Compose instalados.

## Configuração e Execução

Antes de iniciar em qualquer um dos ambientes, configure as variáveis de ambiente:

```bash
cp .env.example .env
```

Edite o `.env` com as credenciais do MySQL. O usuário precisa ter permissão `CREATE` no servidor para que o projeto recrie `games_deals` depois de um reset completo. Se o banco já existir, também precisa das permissões de leitura/escrita e criação/alteração de tabelas necessárias.

---

### Opção 1: Ambiente Local

#### Instalação

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

#### Execução

Na raiz do projeto:

```bash
# Os dois crawlers (padrão)
python -m app.main --crawler all --once

# Somente promoções da Steam
python -m app.main --crawler steam --once

# Somente jogos grátis ativos da Epic
python -m app.main --crawler epic --once

# Execução recorrente (padrão: 6 horas)
python -m app.main --crawler all --watch

# Execução recorrente a cada 3 horas
python -m app.main --crawler all --watch --interval 10800

# Teste limitado; não marca ofertas ausentes como indisponíveis
python -m app.main --crawler steam --max-items 20
```

---

### Opção 2: Ambiente Docker

Na raiz do projeto, utilize o Docker Compose para gerenciar os containers e executar coletas avulsas:

```bash
# Subir os serviços em segundo plano (com rebuild)
docker compose up -d --build

# Executar todos os crawlers uma única vez
docker compose run --rm crawler python -m app.main --once

# Teste rápido do insert (não espera todos os 100)
docker compose run --rm crawler python -c "from app.services.steam_deals_service import run_steam_crawler; print(run_steam_crawler(max_items=10))"

# Executar somente a Steam com logs detalhados (DEBUG)
docker compose run --rm crawler python -m app.main --crawler steam --once --log-level DEBUG

# Parar e remover os containers
docker compose down

# Parar os containers e remover os volumes (apaga os dados do banco)
docker compose down -v
```

## Estrutura

```text
app/
├── main.py
├── config.py
├── adapters/
│   ├── epic_games.py
│   └── steam.py
├── database/
│   ├── connection.py
│   └── schema.py
└── services/
    ├── free_games_service.py
    └── steam_deals_service.py
```

## Modelo de dados

O projeto utiliza as tabelas `stores`, `games`, `deals`, `price_history`, `editorial_items`, `crawler_runs`, `platforms` e `free_games`.

- Steam: `deals.external_id` recebe o Steam App ID, com unicidade por `(store_id, external_id)`.
- Epic: ofertas gratuitas são persistidas em `free_games`, com unicidade por `(store_id, external_id, starts_at)`.
- `games.canonical_key` identifica o jogo por origem (`steam:<app_id>` ou `epic:<id>`).

O DDL equivalente é criado em `app/database/schema.py`. Uma cópia SQL legível está em `sql/schema.sql`.

## Comportamento de segurança dos dados

- Um `--max-items` é considerado execução parcial.
- A Steam só marca promoções não encontradas como indisponíveis após uma coleta completa **e não vazia**. Isso evita desativar todas as ofertas em caso de resposta vazia/bloqueada.
- O histórico de preços é registrado na primeira observação e quando há alteração nos campos monitorados.
- Não há exclusão automática de jogos ou ofertas históricas.

## Limitações conhecidas

- A Steam pode alterar o HTML da busca; nesse caso, o parser precisará ser atualizado.
- A coleta Steam considera preços retornados para `cc=br` e grava moeda `BRL`. Itens sem preço numérico ou com preço zero são ignorados.
- O crawler Epic registra ofertas gratuitas ativas retornadas pelo endpoint; não é um catálogo histórico completo.
- A criação automática do banco depende de permissões MySQL adequadas.