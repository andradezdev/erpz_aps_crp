# ERPZ APS & CRP — Planejamento de Capacidade e Sequenciamento Avançado

Solução completa de APS (Advanced Planning & Scheduling) e CRP (Capacity Requirements Planning) para o Frappe Framework / ERPNext, integrada nativamente às Ordens de Produção originadas pelo MRP.

---

## Principais Recursos

1. **Rastreabilidade Bidirecional Cruzada:**
   - Vinculação estrita via Tickets de Planejamento:
     `Demanda (Sales Order) ➔ Ticket MRP ➔ Work Orders ➔ Ticket APS/CRP ➔ Job Cards ➔ Apontamentos Reais`.
   - Vínculos gravados nos campos customizados `custom_mrp_ticket` e `custom_aps_ticket` do ERPNext.

2. **Sequenciamento por Capacidade Finita:**
   - Alocação cronológica minuto a minuto respeitando turnos de trabalho, intervalos de almoço e calendários operacionais (`Holiday List`).
   - Bloqueio automático de postos em períodos de manutenção preventiva ou corretiva (`APS Resource Block`).
   - Consideração real de tempos de setup e transferência entre operações sucessoras.

3. **Gantt Interativo com Arrastar e Soltar (Drag-and-Drop) e Propagação em Cadeia:**
   - Movimentação direta de operações na linha do tempo.
   - **Propagação em Cadeia Automática:** Ao deslocar uma operação, todas as operações sucessoras da mesma Ordem de Produção (e Ordens de Produção dependentes) são automaticamente recalculadas e reposicionadas.
   - Validação contínua de precedências e detecção visual de conflitos e atrasos.

4. **Análise de Carga x Capacidade (CRP):**
   - Comparativo diário de horas disponíveis versus carga programada por posto de trabalho.
   - Identificação automática de gargalos e sobrecargas críticas.

5. **Efetivação e Apontamentos Operacionais:**
   - Sincronização automática das datas e horários calculados diretamente nos campos `planned_start_date` e `expected_delivery_date` das `Work Orders` e nos horários dos `Job Cards` do ERPNext.
   - Registro de apontamentos reais com comparação contra o planejado.

---

## Licença
MIT © 2026 ERPZ
