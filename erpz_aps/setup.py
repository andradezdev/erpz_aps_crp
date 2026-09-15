# Copyright (c) 2026, ERPZ and contributors
# For license information, please see license.txt

import frappe
import json
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def setup_aps_custom_fields():
    custom_fields = {
        "Work Order": [
            {
                "fieldname": "custom_aps_ticket",
                "label": "Ticket APS/CRP",
                "fieldtype": "Link",
                "options": "APS Ticket",
                "insert_after": "custom_mrp_ticket",
                "read_only": 1
            }
        ],
        "Job Card": [
            {
                "fieldname": "custom_aps_ticket",
                "label": "Ticket APS/CRP",
                "fieldtype": "Link",
                "options": "APS Ticket",
                "insert_after": "naming_series",
                "read_only": 1
            },
            {
                "fieldname": "custom_mrp_ticket",
                "label": "Ticket MRP",
                "fieldtype": "Link",
                "options": "MRP Ticket",
                "insert_after": "custom_aps_ticket",
                "read_only": 1
            }
        ]
    }
    create_custom_fields(custom_fields, update=True)
    print("APS Custom fields registered in ERPNext!")

def setup_aps_desktop_and_sidebar():
    """Automatically ensures Desktop Icon and Workspace Sidebar are created and visible on /desk."""
    try:
        from frappe.desk.doctype.workspace_sidebar.workspace_sidebar import create_workspace_sidebar_for_workspaces
        from frappe.desk.doctype.desktop_icon.desktop_icon import create_desktop_icons
        create_workspace_sidebar_for_workspaces()
        create_desktop_icons()
    except Exception as e:
        print(f"Warning during auto icon generation: {e}")

    # 1. Desktop Icon for ERPZ APS
    icon_name = frappe.db.get_value("Desktop Icon", {"link_to": "ERPZ APS"}, "name")
    if not icon_name:
        icon_name = frappe.db.get_value("Desktop Icon", {"label": "ERPZ APS"}, "name")

    if icon_name:
        frappe.db.set_value("Desktop Icon", icon_name, {
            "label": "ERPZ APS",
            "icon": "getting-started",
            "icon_type": "Link",
            "link_type": "Workspace Sidebar",
            "link_to": "ERPZ APS",
            "parent_icon": "",
            "hidden": 0,
            "standard": 1,
            "app": "erpz_aps",
            "idx": 8
        })
    else:
        new_icon = frappe.new_doc("Desktop Icon")
        new_icon.name = "ERPZ APS"
        new_icon.label = "ERPZ APS"
        new_icon.icon = "getting-started"
        new_icon.icon_type = "Link"
        new_icon.link_type = "Workspace Sidebar"
        new_icon.link_to = "ERPZ APS"
        new_icon.parent_icon = ""
        new_icon.hidden = 0
        new_icon.standard = 1
        new_icon.app = "erpz_aps"
        new_icon.idx = 8
        new_icon.insert(ignore_permissions=True)

    # 2. Workspace Sidebar for ERPZ APS
    sb_items = [
        {"label": "Home", "link_to": "ERPZ APS", "link_type": "Workspace", "type": "Link", "icon": "home", "idx": 0},
        {"label": "Programação & Gantt (APS)", "link_to": "aps_workbench", "link_type": "Page", "type": "Link", "icon": "calendar-days", "idx": 1},
        {"label": "Tickets de Sequenciamento", "link_to": "APS Ticket", "link_type": "DocType", "type": "Link", "icon": "receipt-text", "idx": 2},
        {"label": "Capacidade e Operações", "type": "Section Break", "icon": "list-tree", "idx": 3},
        {"label": "Carga x Capacidade (CRP)", "link_to": "APS Capacity Load", "link_type": "DocType", "type": "Link", "child": 1, "icon": "chart", "idx": 4},
        {"label": "Operações Sequenciadas", "link_to": "APS Scheduled Operation", "link_type": "DocType", "type": "Link", "child": 1, "icon": "list-todo", "idx": 5},
        {"label": "Apontamentos da Produção", "link_to": "APS Execution Log", "link_type": "DocType", "type": "Link", "child": 1, "icon": "notepad-text", "idx": 6},
        {"label": "Histórico de Ajustes Gantt", "link_to": "APS Adjustment History", "link_type": "DocType", "type": "Link", "child": 1, "icon": "scroll-text", "idx": 7},
        {"label": "Cadastros e Parâmetros", "type": "Section Break", "icon": "settings", "idx": 8},
        {"label": "Parâmetros do APS", "link_to": "APS Settings", "link_type": "DocType", "type": "Link", "child": 1, "icon": "setting", "idx": 9},
        {"label": "Postos e Recursos Produtivos", "link_to": "APS Resource", "link_type": "DocType", "type": "Link", "child": 1, "icon": "factory", "idx": 10},
        {"label": "Bloqueios e Manutenções", "link_to": "APS Resource Block", "link_type": "DocType", "type": "Link", "child": 1, "icon": "tool", "idx": 11}
    ]

    if not frappe.db.exists("Workspace Sidebar", "ERPZ APS"):
        sb = frappe.new_doc("Workspace Sidebar")
        sb.title = "ERPZ APS"
        sb.header_icon = "getting-started"
        sb.app = "erpz_aps"
        sb.standard = 1
        for it in sb_items:
            sb.append("items", it)
        sb.insert(ignore_permissions=True)
    else:
        sb = frappe.get_doc("Workspace Sidebar", "ERPZ APS")
        sb.items = []
        for it in sb_items:
            sb.append("items", it)
        sb.app = "erpz_aps"
        sb.header_icon = "getting-started"
        sb.standard = 1
        sb.save(ignore_permissions=True)

    # 3. Workspace ERPZ APS
    content_blocks = [
        {"id": "h_shortcuts", "type": "header", "data": {"text": "<span class=\"h4\"><b>Atalhos Rápidos de Programação</b></span>", "col": 12}},
        {"id": "sc_workbench", "type": "shortcut", "data": {"shortcut_name": "Gantt Interativo", "col": 4}},
        {"id": "sc_ticket", "type": "shortcut", "data": {"shortcut_name": "Tickets APS", "col": 4}},
        {"id": "sc_crp", "type": "shortcut", "data": {"shortcut_name": "Carga x Capacidade", "col": 4}},
        {"id": "spacer_1", "type": "spacer", "data": {"col": 12}},
        {"id": "h_cards", "type": "header", "data": {"text": "<span class=\"h4\"><b>Módulos e Recursos</b></span>", "col": 12}},
        {"id": "card_ops", "type": "card", "data": {"card_name": "Programação e Execução", "col": 4}},
        {"id": "card_crp", "type": "card", "data": {"card_name": "Análise de Capacidade", "col": 4}},
        {"id": "card_setup", "type": "card", "data": {"card_name": "Recursos e Parâmetros", "col": 4}}
    ]

    if frappe.db.exists("Workspace", "ERPZ APS"):
        ws = frappe.get_doc("Workspace", "ERPZ APS")
        ws.type = "Workspace"
        ws.content = json.dumps(content_blocks)
        for l in ws.links:
            if l.type == "Card Break":
                l.link_type = ""
                l.link_to = ""
            elif l.link_to in ("aps_workbench", "aps-workbench"):
                l.link_to = "aps-workbench"
                l.link_type = "Page"
        ws.save(ignore_permissions=True)

    frappe.cache.delete_keys("desktop_icons")
    frappe.clear_cache()
    frappe.db.commit()
    print("Desktop Icon and Workspace Sidebar configured for ERPZ APS!")

def after_install():
    setup_aps_custom_fields()
    setup_aps_desktop_and_sidebar()

def after_migrate():
    setup_aps_custom_fields()
    setup_aps_desktop_and_sidebar()
