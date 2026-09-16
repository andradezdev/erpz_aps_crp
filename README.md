# ERPZ APS & CRP — Planejamento de Capacidade e Sequenciamento Avançado

Solução avançada de **APS (Advanced Planning and Scheduling)** e **CRP (Capacity Requirements Planning)** desenvolvida nativamente para o **Frappe Framework** e **ERPNext**, com sequenciamento por capacidade finita, Gantt interativo com drag-and-drop e propagação em cadeia, controle de cenários por Ticket e integração direta com as Ordens de Produção e Job Cards originados pelo MRP.

Desenvolvido com base nos conceitos técnicos de programação da produção e na especificação funcional de APS/CRP industrial.

---

## Sumário Executivo

Enquanto o MRP calcula **o que** e **quanto** produzir, o **ERPZ APS & CRP** resolve a programação real do chão de fábrica:
1. **Existe capacidade suficiente** nos postos de trabalho para atender as datas de entrega requeridas? (Análise CRP Carga x Capacidade).
2. **Onde e quando** cada operação deve ser executada? (Sequenciamento por Capacidade Finita no APS).
3. **Como resolver gargalos e sobrecargas?** Através de desvio automático para postos alternativos ou reprogramação interativa com arrastar e soltar (drag-and-drop).
4. **Como garantir a execução?** Sincronização direta dos horários programados nos campos de data das `Work Orders` e nos `Job Cards` do ERPNext.

---

## 1. Rastreabilidade Cruzada por Ticket (`MRP` $\leftrightarrow$ `APS` $\leftrightarrow$ `ERPNext`)

A ferramenta mantém o controle em toda a cadeia produtiva através de tickets de planejamento:

```
Demanda (Sales Order)
   └── Ticket MRP (Cálculo de Necessidades)
         └── Ordem de Produção (Work Order)
               └── Ticket APS/CRP (Sequenciamento Finito)
                     └── Operações Agendadas / Job Cards
                           └── Apontamentos Reais de Produção
```

- Cada documento gerado ou programado possui as referências:
  - `custom_mrp_ticket`: Identificador do cenário de materiais.
  - `custom_aps_ticket`: Identificador do cenário de capacidade e sequenciamento.

---

## 2. Arquitetura e Modelo de Dados

O módulo é composto pelos seguintes DocTypes nativos:

| DocType | Tipo | Finalidade |
| :--- | :--- | :--- |
| **`APS Ticket`** | Principal | Chave de controle e versionamento do cenário (`APS-.YYYY.-.#####`). Armazena horizonte, direção (*Forward/Backward*), regras de prioridade e métricas de desempenho. |
| **`APS Settings`** | Single | Parâmetros globais: ativação de capacidade finita, limiar de sobrecarga (%), tempos padrão de setup e transferência, e estratégia de recursos alternativos. |
| **`APS Product Routing`** | Cadastro | Roteiro produtivo consolidado por produto. Permite cadastrar na mesma tela a sequência completa de operações, métricas de lote, tempos e sobreposições em %. |
| **`APS Routing Operation Item`** | Tabela Filha | Linha da operação do roteiro contendo: código (`10 - Cortar`), nome, posto titular, lote de referência, tempo do lote, setup, % sobreposição e posto alternativo. |
| **`APS Resource`** | Cadastro | Configuração avançada da Estação de Trabalho (`Workstation`): eficiência efetiva (%), horas diárias de capacidade, calendário e alternativos da máquina. |
| **`APS Alternative Resource`**| Tabela Filha | Matriz de postos de trabalho alternativos com prioridade e fator de eficiência. |
| **`APS Resource Block`** | Cadastro | Bloqueios e indisponibilidades de postos: manutenções preventivas, corretivas, quebras, faltas de operador e finais de semana com cores personalizadas. |
| **`APS Scheduled Operation`**| Dados | Cada operação alocada no tempo, com data/hora início, término, duração, predecessora, postos e status (*Programada, Ajustada no Gantt, Atrasada, Concluída*). |
| **`APS Capacity Load`** | Dados | Análise diária de Carga x Capacidade (CRP) por posto: horas disponíveis, carga programada, saldo, % de utilização e flag de gargalo. |
| **`APS Adjustment History`** | Auditoria | Histórico detalhado de arrastar e soltar no Gantt registrando usuário, horários anteriores, novos horários e quantidade de operações recalculadas em cadeia. |
| **`APS Execution Log`** | Apontamento | Registro de apontamentos reais da fábrica (*Início, Pausa, Conclusão, Refugos*) com comparativo *Planejado vs. Realizado*. |

---

## 3. Roteiro Produtivo do Produto (`APS Product Routing`)

Permite cadastrar em uma **única tela consolidada** todas as operações sequenciais de um produto, sem necessidade de navegar entre múltiplas telas:

- **Linha 1:** Sequência `10`, Código: `10 - Cortar`, Recurso: `SERRA 001`, Qtd Referência: `5 peças`, Tempo: `15 min` ($\rightarrow$ Unitário: **`3,00 min/peça`**), Setup: `10 min`, Sobreposição: **`50%`**, Sobreposição entre OPs: **`20%`**, **Recurso Alternativo do Produto:** `Centro Usinagem 02`.
- **Linha 2:** Sequência `20`, Código: `20 - Dobrar`, Recurso: `Centro Usinagem 02`, Qtd Referência: `10 peças`, Tempo: `20 min` ($\rightarrow$ Unitário: **`2,00 min/peça`**), Setup: `15 min`, Sobreposição: **`30%`**, **Recurso Alternativo:** `Torno CNC 01`.
- **Linha 3:** Sequência `30`, Código: `30 - Embalar`, Recurso: `Torno CNC 01`, Qtd Referência: `20 peças`, Tempo: `20 min` ($\rightarrow$ Unitário: **`1,00 min/peça`**), Setup: `5 min`.

### Importação e Exportação em Massa via Excel
- Na própria tela de **Operações do Processo** (`APS Product Routing`), estão disponíveis os botões:
  - **`Importar Roteiro (Excel)`**: Modal com upload direto para criar ou atualizar todas as operações do produto em lote.
  - **`Baixar Modelo Excel (.xlsx)`**: Gera planilha pré-formatada com colunas para importação imediata.

---

## 4. Motor de Sequenciamento por Capacidade Finita

O motor (`erpz_aps.engine.aps_engine`) resolve o agendamento minuto a minuto:

### A. Enfileiramento Consecutivo Imediato (Sem Ociosidade Artificial)
- No sequenciamento para frente (*Forward*), as ordens são posicionadas consecutivamente.
- Assim que a operação da Ordem 1 termina em um posto, a operação da Ordem 2 inicia **no mesmo minuto**, sem gaps artificiais de semanas entre ordens no mesmo equipamento.

### B. Regra de Sobreposição (% Overlap)
- Se uma operação possui `overlap_pct = 50%`:
  A operação sucessora **não precisa esperar 100% do término do lote**. Ela inicia assim que metade do lote for processado na máquina anterior, reduzindo drasticamente o tempo total de produção (WIP).

### C. Alocação em Recursos Alternativos por Sobrecarga ou Atraso
- O planejador parametriza a estratégia:
  1. *Alternativo do Produto* (definido na linha do roteiro do item).
  2. *Alternativo da Estação* (definido no cadastro da máquina).
- Se o posto titular estiver ocupado ou provocar atraso na entrega, o motor busca o posto alternativo viável e aloca a operação lá, registrando `is_alternative_used = 1`.

---

## 5. Gantt Interativo com Arrastar e Soltar e Propagação em Cadeia

O painel central (`aps_workbench`) oferece uma experiência interativa rica:

### A. Arrastar e Soltar (Drag-and-Drop)
- O planejador pode mover qualquer barra de operação horizontalmente (mudando data/hora) ou verticalmente (mudando o posto alocado).

### B. Propagação em Cadeia Automática (`chain_propagation.py`)
- Ao mover uma operação para frente no tempo:
  1. O sistema recalcula e empurra **automaticamente todas as operações sucessoras** da mesma Ordem de Produção no tempo exato de precedência.
  2. Se a Ordem de Produção alimenta uma OP pai, a alteração é propagada para a OP seguinte.
  3. Elimina sobreposições de outras ordens no mesmo posto de trabalho (capacidade finita).
  4. Valida se a nova posição viola a conclusão de operações predecessoras e exibe alerta visual de conflito se necessário.

### C. Cores e Legenda por Apontamento em Tempo Real
O Gantt monitora a execução e colore as barras dinamicamente:
- 🟩 **Verde (`#38a169`):** Operação **Concluída / Totalmente Apontada**.
- 🟨 **Amarelo (`#ecc94b`):** Operação **Em Execução / Apontada Parcialmente**.
- 🟧 **Laranja (`#ed8936`):** Operação **Ajustada Manualmente no Gantt**.
- 🟥 **Vermelho (`#e53e3e`):** Operação **Em Atraso / Conflito**.
- 🟦 **Azul (`#2490ef`):** Operação **Programada** (aguardando início).

### D. Visualização Imediata de Bloqueios e Finais de Semana
- **Tarjas de Finais de Semana:** Se a estação não opera aos finais de semana (`allow_weekend_work == 0`), sábados e domingos são desenhados como faixas hachuradas cinzas (`Sáb (Indisponível)` e `Dom (Indisponível)`).
- **Bloqueios de Manutenção:** Manutenções preventivas, corretivas ou paradas cadastradas em `APS Resource Block` aparecem imediatamente no Gantt com cor destacada e legenda do motivo (ex: `⛔ [Manutenção Preventiva] - Reforma do Fuso`).
- **Extensão Automática de Operações:** Se uma operação atravessa um bloqueio de manutenção ou fim de semana, o motor **pausa o trabalho durante o bloqueio e estende o término da operação para após a liberação da máquina** (sem travamento ou loops infinitos).

---

## 6. Análise de Carga x Capacidade (CRP) e Exportação

- **Aba Carga x Capacidade:** Gráfico de linha e colunas comparando **Horas Disponíveis** versus **Carga Programada**, com identificação em vermelho dos dias em **Gargalo / Sobrecarga**.
- **Grade de Operações Ordenada pelo Gantt:** Lista todas as operações na **mesma ordem cronológica do Gantt** (`#1, #2, #3...`), com botões diretos para abrir a Ordem de Produção (`Abrir OP`) ou Job Card no ERPNext.
- **Exportação para Excel Formatado (`.xlsx`):**
  - **Aba 1 (Sequenciamento Gantt):** Relação cronológica completa das operações no tempo (Ordem `#1, #2...`, datas e horas, postos, OPs, durações, tempos de setup e atrasos).
  - **Aba 2 (Carga x Capacidade):** Tabela diária de capacidade, carga e taxa de utilização.

---

## 7. Efetivação no ERPNext

Ao clicar em **Efetivar Programação**, o sistema:
1. Atualiza `planned_start_date` e `expected_delivery_date` nas **Work Orders**.
2. Atualiza os horários e o posto de trabalho em todos os **Job Cards** do ERPNext.
3. Grava o vínculo `custom_aps_ticket` em todos os documentos.

---

## Instalação e Configuração

```bash
# No diretório do frappe-bench:
bench get-app erpz_aps https://github.com/andradezdev/erpz_aps.git
bench --site <seu-site> install-app erpz_aps
bench --site <seu-site> migrate
```

O ícone **ERPZ APS** é criado automaticamente no `/desk` do ambiente.

---

## Licença
Distribuído sob a licença MIT. Copyright © 2026 ERPZ.
